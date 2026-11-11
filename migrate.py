"""Schema + first-run data, applied automatically at program start (python main.py).

Why: running a big SQL script by hand (with DROP TABLE at the top) can wipe real student data.
Here every change is a numbered migration recorded in `schema_migrations`; a migration runs ONCE,
never drops tables, and the app refuses to touch a database it does not recognise.

    migration 1  tables, keys, constraints   <- read from  Capstone_Database.sql  (same folder as this file)
    migration 2  catalog, programs, prerequisites, program requirements   <- seed_data.py
    migration 3  university CORE curriculum                                <- seed_data.py
"""
from __future__ import annotations

import re
import mysql.connector

import config as cfg
import seed_data

SCHEMA_FILE = cfg.RESOURCE_DIR / "Capstone_Database.sql"          # bundled inside the executable when frozen

# Prerequisite rows that were in your own SQL file but not in seed_data.py (kept so nothing changes silently).
# The department's prerequisite map shows CYBER 260 <- CMSCI 125 and CYBER 354 <- CYBER 260 only.
# If the map is right, delete these two lines.
YOUR_EXTRA_PREREQS = [("CYBER 260", "CMSCI 120", 1), ("CYBER 354", "CMSCI 355", 2)]

# Statements that must NEVER run from a schema file: they can erase data.
UNSAFE = re.compile(r"^\s*(DROP\s+(TABLE|DATABASE|SCHEMA|VIEW)|TRUNCATE|DELETE\s+FROM|SET\s+FOREIGN_KEY_CHECKS)", re.I)
SKIPPED = re.compile(r"^\s*(USE\s|CREATE\s+(SCHEMA|DATABASE))", re.I)       # the connection already selects the database


class MigrationError(Exception):
    pass


class LegacyDatabase(MigrationError):
    """Tables exist but there is no migration log: the database was built by something other than this
    program (a SQL file mounted into Docker's docker-entrypoint-initdb.d, a script run by hand, an old version).
    student_rows tells the caller whether anything valuable is inside."""

    def __init__(self, message: str, student_rows: int):
        super().__init__(message)
        self.message = message
        self.student_rows = student_rows


def split_sql(text: str) -> list[str]:
    """Split a script on ';' while respecting quotes; strips  -- ...  # ...  and  /* ... */  comments."""
    out, buf, i, n, quote = [], [], 0, len(text), None
    while i < n:
        c = text[i]
        if quote:
            buf.append(c)
            if c == "\\" and i + 1 < n:
                buf.append(text[i + 1]); i += 2; continue
            if c == quote:
                if i + 1 < n and text[i + 1] == quote:                  # doubled quote:  'it''s'
                    buf.append(text[i + 1]); i += 2; continue
                quote = None
            i += 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if (text.startswith("--", i) and (i + 2 >= n or text[i + 2] in " \t\r\n")) or c == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c in ("'", '"', "`"):
            quote = c; buf.append(c); i += 1
            continue
        if c == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []; i += 1
            continue
        buf.append(c); i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _raw(database: str | None):
    kw = dict(host=cfg.DB_HOST, port=cfg.DB_PORT, user=cfg.DB_USER, password=cfg.DB_PASSWORD, connection_timeout=5, **cfg.DB_EXTRA)
    if database:
        kw["database"] = database
    return mysql.connector.connect(**kw)


# ---------------------------------------------------------------- migrations
def _m1_schema(cur):
    if not SCHEMA_FILE.exists():
        raise MigrationError(f"Cannot find the schema file:\n  {SCHEMA_FILE}\n"
                             "Put Capstone_Database.sql in the SAME folder as migrate.py (the folder you start main.py from).")
    for stmt in split_sql(SCHEMA_FILE.read_text(encoding="utf-8")):
        if SKIPPED.match(stmt):
            continue
        if UNSAFE.match(stmt):                                          # never execute anything that can delete data
            continue
        cur.execute(stmt)


def _m2_seed_catalog(cur):
    seed_data.validate()
    cur.executemany("INSERT IGNORE INTO catalog_years (label,start_year,is_current) VALUES (%s,%s,%s)", seed_data.CATALOG_YEARS)
    cur.executemany("INSERT IGNORE INTO classes (code,name,credits,when_offered,notes) VALUES (%s,%s,%s,%s,%s)", seed_data.COURSES)
    cur.executemany("INSERT IGNORE INTO programs (code,name,type,credits_required) VALUES (%s,%s,%s,%s)", seed_data.PROGRAMS)
    cur.executemany("INSERT IGNORE INTO prerequisites (course_code,prereq_course_code,group_no) VALUES (%s,%s,%s)",
                    list(seed_data.PREREQS) + YOUR_EXTRA_PREREQS)
    cur.execute("SELECT id FROM catalog_years")
    years = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT id, code FROM programs")
    pid = {code: i for i, code in cur.fetchall()}
    for prog, (core, pool, n) in seed_data.REQUIREMENTS.items():
        for y in years:
            cur.executemany("INSERT IGNORE INTO program_requirements VALUES (%s,%s,%s,%s)",
                            [(y, pid[prog], c, "Core") for c in core] + [(y, pid[prog], c, "Elective") for c in pool])
            cur.execute("INSERT INTO program_rules (catalog_year_id, program_id, electives_needed) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE electives_needed=VALUES(electives_needed)", (y, pid[prog], n))


def _m3_seed_core(cur):
    cur.execute("SELECT id FROM catalog_years")
    for (y,) in cur.fetchall():
        for order, (name, take, off, cr, man, notes, opts) in enumerate(seed_data.CORE, start=1):
            cur.execute("""INSERT INTO core_requirements (catalog_year_id,name,take_as,offered,credits,manual_only,notes,sort_order)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                           ON DUPLICATE KEY UPDATE credits=VALUES(credits), notes=VALUES(notes)""", (y, name, take, off, cr, man, notes, order))
            cur.execute("SELECT id FROM core_requirements WHERE catalog_year_id=%s AND name=%s", (y, name))
            res = cur.fetchone()
            if res:
                cur.executemany("INSERT IGNORE INTO core_options (core_id,pattern) VALUES (%s,%s)", [(res[0], o) for o in opts])

def _m4_sections(cur):
    """Semester course offerings (one row per class SECTION meeting, e.g. the Fall 2026 schedule).
    A new table only: nothing existing is changed, so a database that already holds students upgrades safely."""
    cur.execute("""CREATE TABLE IF NOT EXISTS course_sections (
        id INT AUTO_INCREMENT PRIMARY KEY,
        term ENUM('Fall','Spring','Summer') NOT NULL,
        year INT NOT NULL,
        course_code VARCHAR(50) NOT NULL,
        section VARCHAR(10) NOT NULL,
        component ENUM('Lecture','Lab','Recitation') NOT NULL DEFAULT 'Lecture',
        subterm VARCHAR(30) NULL,
        title VARCHAR(200) NOT NULL,
        credits TINYINT NOT NULL DEFAULT 0,
        delivery VARCHAR(40) NULL,
        capacity INT NULL,
        enrollment INT NULL,
        location VARCHAR(40) NULL,
        room VARCHAR(40) NULL,
        professor VARCHAR(100) NULL,
        days VARCHAR(12) NULL,
        start_time TIME NULL,
        end_time TIME NULL,
        start_date DATE NULL,
        end_date DATE NULL,
        KEY ix_sections_term (year, term, course_code),
        FOREIGN KEY (course_code) REFERENCES classes(code) ON UPDATE CASCADE ON DELETE CASCADE
    )""")

def _m5_transfer(cur):
    """Transfer-credit evaluation. Adds two columns (what the transcript printed) and one table (decisions).
    Guarded so it is safe to re-run; nothing existing is changed or removed."""
    for col, ddl in (("source_title", "VARCHAR(200) NULL"), ("source_credits", "DECIMAL(4,1) NULL")):
        cur.execute("""SELECT COUNT(*) FROM information_schema.columns
                       WHERE table_schema = DATABASE() AND table_name = 'student_courses' AND column_name = %s""", (col,))
        if cur.fetchone()[0] == 0:
            cur.execute(f"ALTER TABLE student_courses ADD COLUMN {col} {ddl}")
    cur.execute("""CREATE TABLE IF NOT EXISTS transfer_equivalencies (
        transfer_code VARCHAR(50) NOT NULL PRIMARY KEY,
        msmu_code     VARCHAR(50) NULL,
        notes         VARCHAR(255) NULL,
        decided_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (msmu_code) REFERENCES classes(code) ON UPDATE CASCADE ON DELETE SET NULL
    )""")


MIGRATIONS = [(1, "base schema from Capstone_Database.sql", _m1_schema),
              (2, "MSMU catalog, programs, prerequisites", _m2_seed_catalog),
              (3, "university CORE curriculum", _m3_seed_core),
              (4, "semester course offerings (course_sections)", _m4_sections),
              (5, "transfer credit equivalencies", _m5_transfer)]


def _count_students(cur) -> int:
    cur.execute("SHOW TABLES LIKE 'students'")
    if cur.fetchone() is None:
        return 0
    cur.execute("SELECT COUNT(*) FROM students")
    return cur.fetchone()[0]


def rebuild_unused_legacy() -> list[str]:
    """Drop and rebuild a half-built database that holds NO student records (e.g. a failed Docker init script).
    Refuses if even one student exists. A backup is attempted first (best effort)."""
    c = _raw(cfg.DB_NAME)
    try:
        n = _count_students(c.cursor())
    finally:
        c.close()
    if n:
        raise MigrationError(f"Refusing to rebuild: the database holds {n} student record(s).")
    try:
        import backup
        backup.make_backup("auto", "before rebuilding a half-built database")
    except Exception:
        pass
    c = _raw(None)
    try:
        c.cursor().execute(f"DROP DATABASE IF EXISTS `{cfg.DB_NAME}`")
        c.commit()
    finally:
        c.close()
    return run()


def current_version() -> int:
    try:
        c = _raw(cfg.DB_NAME)
    except mysql.connector.Error:
        return 0
    try:
        cur = c.cursor()
        cur.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations")
        return cur.fetchone()[0]
    except mysql.connector.Error:
        return 0
    finally:
        c.close()


def run() -> list[str]:
    """Create / upgrade the database. Returns a list of human-readable actions performed."""
    done: list[str] = []
    try:
        c = _raw(None)
    except mysql.connector.Error as e:
        raise MigrationError(f"Cannot reach MySQL at {cfg.DB_HOST}:{cfg.DB_PORT}.\n"
                             f"Start it with:  docker compose up -d\n"
                             f"(If this program runs INSIDE a container, set DB_HOST to the database container's name.)\n\n{e}") from e
    try:
        cur = c.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{cfg.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        c.database = cfg.DB_NAME
        cur.execute("SHOW TABLES LIKE 'schema_migrations'")
        has_log = cur.fetchone() is not None
        if not has_log:
            cur.execute("SHOW TABLES LIKE 'classes'")
            if cur.fetchone() is not None:
                n = _count_students(cur)
                raise LegacyDatabase(
                    "The database already contains tables but has no migration log, so this program did not build it\n"
                    "(typically a SQL file mounted into Docker, or an older version of the project).\n"
                    + ("It holds NO student records." if n == 0 else
                       f"It holds {n} student record(s), so the program will NOT change it.\n"
                       "Run  python backup.py  first, then ask for help migrating it."), n)
            cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                             version INT PRIMARY KEY, description VARCHAR(200) NOT NULL,
                             applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            c.commit()
        cur.execute("SELECT version FROM schema_migrations")
        applied = {r[0] for r in cur.fetchall()}
        for version, desc, fn in MIGRATIONS:
            if version in applied:
                continue
            try:
                fn(cur)
                cur.execute("INSERT INTO schema_migrations (version, description) VALUES (%s,%s)", (version, desc))
                c.commit()
            except MigrationError:
                c.rollback()
                raise
            except Exception as e:
                c.rollback()
                raise MigrationError(f"Migration {version} ({desc}) failed and was rolled back:\n{e}") from e
            done.append(f"applied migration {version}: {desc}")
        return done
    finally:
        c.close()


if __name__ == "__main__":
    for line in run() or ["database already up to date"]:
        print(line)