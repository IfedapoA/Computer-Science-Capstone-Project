"""All database access (single 'capstone' database). Every query is parameterised and every
function returns plain dicts, so the UI and importers never disagree about row types."""
from __future__ import annotations

from contextlib import contextmanager

import mysql.connector

import config as cfg
from audit import (Catalog, Course, CoreReq, Program, ProgramReqs, StudentRecord, TakenCourse)


class DBError(Exception):
    pass


def connect():
    try:
        return mysql.connector.connect(host=cfg.DB_HOST, port=cfg.DB_PORT, user=cfg.DB_USER, password=cfg.DB_PASSWORD,
                                       database=cfg.DB_NAME, autocommit=False, connection_timeout=5, **cfg.DB_EXTRA)
    except mysql.connector.Error as e:
        raise DBError(f"Cannot reach MySQL at {cfg.DB_HOST}:{cfg.DB_PORT}.\nStart it with:  docker compose up -d\n\n{e}") from e


def _friendly(e) -> str:
    n = getattr(e, "errno", None)
    if n == 1062:
        return "That record already exists (duplicate)."
    if n in (1451,):
        return "That item is still in use by other records (students, requirements...), so it cannot be deleted."
    if n == 1452:
        return "A course, program or student referenced here does not exist yet."
    if n == 3819:
        return "A value is outside the allowed range."
    return str(e)


def query(sql: str, params: tuple = ()) -> list[dict]:
    conn = connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    except mysql.connector.Error as e:
        raise DBError(_friendly(e)) from e
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> int:
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.lastrowid or cur.rowcount
    except mysql.connector.Error as e:
        conn.rollback()
        raise DBError(_friendly(e)) from e
    finally:
        conn.close()


@contextmanager
def tx():
    """with tx() as cur: ...  -> one transaction; rolled back on ANY error, committed on success."""
    conn = connect()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except mysql.connector.Error as e:
        conn.rollback()
        raise DBError(_friendly(e)) from e
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_many(statements: list[tuple[str, tuple]]) -> None:
    with tx() as cur:
        for sql, params in statements:
            cur.execute(sql, params)


# =========================================================================== advisors (sign-in)
def find_advisor(email: str) -> dict | None:
    rows = query("SELECT id AS advisor_id, email_address, first_name, last_name FROM advisors WHERE LOWER(email_address)=LOWER(%s)",
                 (email.strip(),))
    if rows:
        rows[0]["role"] = "Advisor"
    return rows[0] if rows else None


def list_advisors() -> list[dict]:
    return query("SELECT * FROM advisors ORDER BY last_name, first_name")


def add_advisor(first: str, last: str, email: str) -> int:
    return execute("INSERT INTO advisors (first_name,last_name,email_address) VALUES (%s,%s,%s)",
                   (first.strip(), last.strip(), email.strip().lower()))


# =========================================================================== catalog years
def catalog_years() -> list[dict]:
    return query("SELECT * FROM catalog_years ORDER BY start_year")


def add_catalog_year(label: str, start_year: int, copy_from_id: int | None) -> int:
    """New year = independent copy of an old year's requirements and CORE (old years stay untouched)."""
    with tx() as cur:
        cur.execute("INSERT INTO catalog_years (label,start_year,is_current) VALUES (%s,%s,FALSE)", (label, start_year))
        new = cur.lastrowid
        if copy_from_id:
            cur.execute("""INSERT INTO program_requirements (catalog_year_id,program_id,course_code,requirement_type)
                           SELECT %s,program_id,course_code,requirement_type FROM program_requirements WHERE catalog_year_id=%s""",
                        (new, copy_from_id))
            cur.execute("""INSERT INTO program_rules (catalog_year_id,program_id,electives_needed)
                           SELECT %s,program_id,electives_needed FROM program_rules WHERE catalog_year_id=%s""", (new, copy_from_id))
            cur.execute("SELECT id,name,take_as,offered,credits,manual_only,notes,sort_order FROM core_requirements WHERE catalog_year_id=%s",
                        (copy_from_id,))
            for oid, *vals in cur.fetchall():
                cur.execute("""INSERT INTO core_requirements (catalog_year_id,name,take_as,offered,credits,manual_only,notes,sort_order)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", (new, *vals))
                nid = cur.lastrowid
                cur.execute("INSERT INTO core_options (core_id,pattern) SELECT %s,pattern FROM core_options WHERE core_id=%s", (nid, oid))
        return new


def set_current_catalog_year(cy_id: int) -> None:
    execute("UPDATE catalog_years SET is_current = (id = %s)", (cy_id,))


# =========================================================================== courses (the "classes" table)
def all_courses(department: str | None = None) -> list[dict]:
    if department:
        return query("SELECT * FROM classes WHERE department=%s ORDER BY code", (department,))
    return query("SELECT * FROM classes ORDER BY code")


def get_course(code: str) -> dict | None:
    rows = query("SELECT * FROM classes WHERE code=%s", (code,))
    return rows[0] if rows else None


def departments() -> list[dict]:
    """Department = the letters before the number in the course code (CMSCI 120 -> CMSCI)."""
    rows = query("SELECT department AS prefix, COUNT(*) AS courses FROM classes GROUP BY department ORDER BY department")
    for r in rows:
        r["name"] = cfg.DEPARTMENT_NAMES.get(r["prefix"], r["prefix"])
    return rows


def save_course(code, name, credits, when_offered, notes, course_id=None) -> int:
    wo = when_offered or None
    if course_id:
        execute("UPDATE classes SET code=%s,name=%s,credits=%s,when_offered=%s,notes=%s WHERE id=%s",
                (code, name, credits, wo, notes or None, course_id))
        return course_id
    return execute("INSERT INTO classes (code,name,credits,when_offered,notes) VALUES (%s,%s,%s,%s,%s)",
                   (code, name, credits, wo, notes or None))


def ensure_course(code: str, name: str = "", credits: int = 3) -> None:
    """Add a course to the catalog if it is not there yet (used by imports and 'new course' buttons)."""
    execute("INSERT IGNORE INTO classes (code,name,credits) VALUES (%s,%s,%s)", (code, name or code, credits))


def delete_course(course_id: int) -> None:
    execute("DELETE FROM classes WHERE id=%s", (course_id,))


def course_objects() -> dict[str, Course]:
    return {r["code"]: Course(r["code"], r["name"], r["credits"], r["when_offered"], r["notes"] or "") for r in all_courses()}


# =========================================================================== prerequisites
def prereq_rows() -> list[dict]:
    return query("SELECT * FROM prerequisites ORDER BY course_code, group_no, prereq_course_code")


def add_prereq(course, prereq, group_no) -> None:
    execute("INSERT INTO prerequisites (course_code,prereq_course_code,group_no) VALUES (%s,%s,%s)", (course, prereq, group_no))


def delete_prereq(course, prereq) -> None:
    execute("DELETE FROM prerequisites WHERE course_code=%s AND prereq_course_code=%s", (course, prereq))


# =========================================================================== programs (majors / minors, incl. outside the department)
def all_programs(base_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM programs" + (" WHERE type <> 'Double Major'" if base_only else "")
    return query(sql + " ORDER BY is_custom, FIELD(type,'Major','Double Major','Minor'), code")


def save_program(code, name, ptype, credits_required, department=None, is_custom=True, program_id=None) -> int:
    if program_id:
        execute("UPDATE programs SET code=%s,name=%s,type=%s,credits_required=%s,department=%s WHERE id=%s",
                (code, name, ptype, credits_required, department or None, program_id))
        return program_id
    return execute("INSERT INTO programs (code,name,type,credits_required,department,is_custom) VALUES (%s,%s,%s,%s,%s,%s)",
                   (code, name, ptype, credits_required, department or None, is_custom))


def delete_program(program_id: int) -> None:
    used = query("SELECT COUNT(*) n FROM student_programs WHERE program_id=%s", (program_id,))[0]["n"]
    if used:
        raise DBError(f"{used} student(s) still have this program. Remove it from them first.")
    execute("DELETE FROM programs WHERE id=%s", (program_id,))


def requirement_rows(cy: int, program_id: int) -> list[dict]:
    return query("""SELECT r.course_code, r.requirement_type, c.name, c.credits FROM program_requirements r
                    JOIN classes c ON c.code=r.course_code WHERE r.catalog_year_id=%s AND r.program_id=%s
                    ORDER BY r.requirement_type, r.course_code""", (cy, program_id))


def electives_needed(cy: int, program_id: int) -> int:
    rows = query("SELECT electives_needed FROM program_rules WHERE catalog_year_id=%s AND program_id=%s", (cy, program_id))
    return rows[0]["electives_needed"] if rows else 0


def add_requirement(cy, program_id, code, rtype) -> None:
    execute("""INSERT INTO program_requirements (catalog_year_id,program_id,course_code,requirement_type) VALUES (%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE requirement_type=VALUES(requirement_type)""", (cy, program_id, code, rtype))


def delete_requirement(cy, program_id, code) -> None:
    execute("DELETE FROM program_requirements WHERE catalog_year_id=%s AND program_id=%s AND course_code=%s", (cy, program_id, code))


def set_electives_needed(cy, program_id, n) -> None:
    execute("""INSERT INTO program_rules (catalog_year_id,program_id,electives_needed) VALUES (%s,%s,%s)
               ON DUPLICATE KEY UPDATE electives_needed=VALUES(electives_needed)""", (cy, program_id, n))


def copy_requirements_to_all_years(program_id: int, from_cy: int) -> None:
    """After building a custom program for one catalog year, make it available in every other year too."""
    with tx() as cur:
        cur.execute("""INSERT IGNORE INTO program_requirements (catalog_year_id,program_id,course_code,requirement_type)
                       SELECT y.id,r.program_id,r.course_code,r.requirement_type FROM program_requirements r
                       CROSS JOIN catalog_years y WHERE r.catalog_year_id=%s AND r.program_id=%s AND y.id<>%s""",
                    (from_cy, program_id, from_cy))
        cur.execute("""INSERT IGNORE INTO program_rules (catalog_year_id,program_id,electives_needed)
                       SELECT y.id,r.program_id,r.electives_needed FROM program_rules r
                       CROSS JOIN catalog_years y WHERE r.catalog_year_id=%s AND r.program_id=%s AND y.id<>%s""",
                    (from_cy, program_id, from_cy))


def overlap_report(cy: int) -> list[dict]:
    return query("SELECT course_code, program_count, programs FROM course_overlap WHERE catalog_year_id=%s "
                 "ORDER BY program_count DESC, course_code", (cy,))


# =========================================================================== CORE curriculum
def core_rows(cy: int) -> list[dict]:
    rows = query("SELECT * FROM core_requirements WHERE catalog_year_id=%s ORDER BY sort_order, id", (cy,))
    opts = query("SELECT core_id, pattern FROM core_options WHERE core_id IN (SELECT id FROM core_requirements WHERE catalog_year_id=%s) ORDER BY pattern", (cy,))
    by: dict[int, list[str]] = {}
    for o in opts:
        by.setdefault(o["core_id"], []).append(o["pattern"])
    for r in rows:
        r["options"] = by.get(r["id"], [])
    return rows


def save_core(cy, name, take_as, offered, credits, manual_only, notes, options: list[str], core_id=None) -> int:
    options = [o.strip() for o in options if o.strip()]
    with tx() as cur:
        if core_id:
            cur.execute("""UPDATE core_requirements SET name=%s,take_as=%s,offered=%s,credits=%s,manual_only=%s,notes=%s WHERE id=%s""",
                        (name, take_as, offered, credits, manual_only, notes or None, core_id))
            cur.execute("DELETE FROM core_options WHERE core_id=%s", (core_id,))
        else:
            cur.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM core_requirements WHERE catalog_year_id=%s", (cy,))
            order = cur.fetchone()[0]
            cur.execute("""INSERT INTO core_requirements (catalog_year_id,name,take_as,offered,credits,manual_only,notes,sort_order)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", (cy, name, take_as, offered, credits, manual_only, notes or None, order))
            core_id = cur.lastrowid
        cur.executemany("INSERT IGNORE INTO core_options (core_id,pattern) VALUES (%s,%s)", [(core_id, o) for o in options])
    return core_id


def delete_core(core_id: int) -> None:
    execute("DELETE FROM core_requirements WHERE id=%s", (core_id,))


def set_core_override(student_id, core_id, course_code, note) -> None:
    execute("""INSERT INTO student_core_overrides (student_id,core_id,course_code,note) VALUES (%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE course_code=VALUES(course_code), note=VALUES(note)""",
            (student_id, core_id, course_code or None, note or None))


def clear_core_override(student_id, core_id) -> None:
    execute("DELETE FROM student_core_overrides WHERE student_id=%s AND core_id=%s", (student_id, core_id))


# =========================================================================== load everything the audit engine needs
def load_catalog(cy: int) -> Catalog:
    prereqs: dict[str, dict[int, set[str]]] = {}
    for r in prereq_rows():
        prereqs.setdefault(r["course_code"], {}).setdefault(r["group_no"], set()).add(r["prereq_course_code"])
    programs = {r["id"]: Program(r["id"], r["code"], r["name"], r["type"], r["credits_required"], bool(r["is_custom"]))
                for r in all_programs()}
    reqs: dict[int, ProgramReqs] = {pid: ProgramReqs() for pid in programs}
    for r in query("SELECT program_id,course_code,requirement_type FROM program_requirements WHERE catalog_year_id=%s ORDER BY course_code", (cy,)):
        pr = reqs.setdefault(r["program_id"], ProgramReqs())
        (pr.core if r["requirement_type"] == "Core" else pr.electives).append(r["course_code"])
    for r in query("SELECT program_id,electives_needed FROM program_rules WHERE catalog_year_id=%s", (cy,)):
        reqs.setdefault(r["program_id"], ProgramReqs()).electives_needed = r["electives_needed"]
    core = [CoreReq(r["id"], r["name"], r["take_as"], r["offered"], r["credits"], bool(r["manual_only"]), r["notes"] or "",
                    tuple(r["options"])) for r in core_rows(cy)]
    return Catalog(course_objects(), prereqs, programs, reqs, core, offerings_map())


# =========================================================================== students
def list_students(advisor_id: int | None = None) -> list[dict]:
    sql = """SELECT s.id, s.first_name, s.last_name, s.email_address, s.catalog_year_id, cy.label AS catalog_year, s.advisor_id,
                    CONCAT(a.first_name,' ',a.last_name) AS advisor_name,
                    (SELECT GROUP_CONCAT(p.code ORDER BY p.code SEPARATOR ', ') FROM student_programs sp
                       JOIN programs p ON p.id=sp.program_id WHERE sp.student_id=s.id) AS programs
             FROM students s JOIN catalog_years cy ON cy.id=s.catalog_year_id LEFT JOIN advisors a ON a.id=s.advisor_id"""
    params: tuple = ()
    if advisor_id is not None:
        sql += " WHERE s.advisor_id=%s"
        params = (advisor_id,)
    return query(sql + " ORDER BY s.last_name, s.first_name", params)


def get_student_row(student_id: int) -> dict | None:
    rows = query("SELECT s.*, cy.label AS catalog_year FROM students s JOIN catalog_years cy ON cy.id=s.catalog_year_id WHERE s.id=%s",
                 (student_id,))
    return rows[0] if rows else None


def load_student(student_id: int) -> StudentRecord:
    row = get_student_row(student_id)
    if not row:
        raise DBError("Student not found.")
    pids = [r["program_id"] for r in query("SELECT program_id FROM student_programs WHERE student_id=%s", (student_id,))]
    courses = [TakenCourse(r["course_code"], r["term"], r["year"], r["status"], r["grade"], bool(r["is_transfer"]))
               for r in query("SELECT * FROM student_courses WHERE student_id=%s", (student_id,))]
    subs = {r["required_course_code"]: r["substitute_course_code"]
            for r in query("SELECT required_course_code,substitute_course_code FROM substitutions WHERE student_id=%s", (student_id,))}
    ov = {r["core_id"]: (r["course_code"], r["note"] or "")
          for r in query("SELECT core_id,course_code,note FROM student_core_overrides WHERE student_id=%s", (student_id,))}
    return StudentRecord(student_id, f"{row['first_name']} {row['last_name']}", row["catalog_year"], pids, courses, subs, ov,
                         transfer_map=transfer_map())


def add_student(first, last, email, catalog_year_id, advisor_id, program_ids) -> int:
    with tx() as cur:
        cur.execute("INSERT INTO students (first_name,last_name,email_address,catalog_year_id,advisor_id) VALUES (%s,%s,%s,%s,%s)",
                    (first.strip(), last.strip(), email.strip().lower(), catalog_year_id, advisor_id))
        sid = cur.lastrowid
        cur.executemany("INSERT INTO student_programs VALUES (%s,%s)", [(sid, p) for p in program_ids])
        return sid


def update_student(student_id, catalog_year_id, advisor_id, program_ids) -> None:
    with tx() as cur:
        cur.execute("UPDATE students SET catalog_year_id=%s, advisor_id=%s WHERE id=%s", (catalog_year_id, advisor_id, student_id))
        cur.execute("DELETE FROM student_programs WHERE student_id=%s", (student_id,))
        cur.executemany("INSERT INTO student_programs VALUES (%s,%s)", [(student_id, p) for p in program_ids])


def delete_student(student_id: int) -> None:
    execute("DELETE FROM students WHERE id=%s", (student_id,))


def student_course_rows(student_id: int) -> list[dict]:
    return query("""SELECT sc.*, c.name, c.credits FROM student_courses sc JOIN classes c ON c.code=sc.course_code
                    WHERE sc.student_id=%s ORDER BY sc.year, FIELD(sc.term,'Spring','Summer','Fall'), sc.course_code""", (student_id,))


def save_student_course(student_id, code, term, year, status, grade, is_transfer=False, row_id=None) -> None:
    grade = (grade or "").strip().upper() or None
    if status != "Completed":
        grade = None                                  # a grade only means something once the course is completed
    if row_id:
        execute("UPDATE student_courses SET course_code=%s,term=%s,year=%s,status=%s,grade=%s,is_transfer=%s WHERE id=%s AND student_id=%s",
                (code, term, year, status, grade, is_transfer, row_id, student_id))
    else:
        execute("INSERT INTO student_courses (student_id,course_code,term,year,status,grade,is_transfer) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (student_id, code, term, year, status, grade, is_transfer))


def delete_student_course(row_id: int) -> None:
    execute("DELETE FROM student_courses WHERE id=%s", (row_id,))


# =========================================================================== substitutions
def list_substitutions(student_id: int) -> list[dict]:
    return query("SELECT * FROM substitutions WHERE student_id=%s ORDER BY created_at DESC", (student_id,))


def add_substitution(student_id, required, substitute, note="") -> None:
    execute("INSERT INTO substitutions (student_id,required_course_code,substitute_course_code,note) VALUES (%s,%s,%s,%s)",
            (student_id, required, substitute, note))


def delete_substitution(sub_id: int) -> None:
    execute("DELETE FROM substitutions WHERE id=%s", (sub_id,))

# =========================================================================== semester offerings (the schedule of classes)
def offerings_map() -> dict[tuple[int, str], set[str]]:
    """{(year, term): {course codes offered}} for every semester that has been imported."""
    out: dict[tuple[int, str], set[str]] = {}
    for r in query("SELECT DISTINCT year, term, course_code FROM course_sections"):
        out.setdefault((r["year"], r["term"]), set()).add(r["course_code"])
    return out


def offering_terms() -> list[dict]:
    return query("""SELECT term, year, COUNT(DISTINCT course_code) AS courses, COUNT(*) AS meetings,
                           COUNT(DISTINCT CONCAT(course_code,'|',section)) AS sections
                    FROM course_sections GROUP BY year, term
                    ORDER BY year DESC, FIELD(term,'Fall','Summer','Spring')""")


def offered_courses(term: str, year: int, department: str | None = None, search: str = "") -> list[dict]:
    sql = """SELECT s.course_code, c.name, c.credits, c.department,
                    COUNT(DISTINCT s.section) AS sections,
                    GROUP_CONCAT(DISTINCT NULLIF(s.professor,'') ORDER BY s.professor SEPARATOR '; ') AS professors,
                    GROUP_CONCAT(DISTINCT s.delivery ORDER BY s.delivery SEPARATOR ', ') AS delivery
             FROM course_sections s JOIN classes c ON c.code = s.course_code
             WHERE s.term=%s AND s.year=%s"""
    params: list = [term, year]
    if department:
        sql += " AND c.department=%s"; params.append(department)
    if search.strip():
        sql += " AND (s.course_code LIKE %s OR c.name LIKE %s OR s.title LIKE %s)"
        like = f"%{search.strip()}%"; params += [like, like, like]
    return query(sql + " GROUP BY s.course_code, c.name, c.credits, c.department ORDER BY s.course_code", tuple(params))


def sections_of(term: str, year: int, course_code: str) -> list[dict]:
    return query("""SELECT * FROM course_sections WHERE term=%s AND year=%s AND course_code=%s
                    ORDER BY section, FIELD(component,'Lecture','Lab','Recitation'), start_time""", (term, year, course_code))


def offering_departments(term: str, year: int) -> list[dict]:
    rows = query("""SELECT c.department AS prefix, COUNT(DISTINCT s.course_code) AS courses FROM course_sections s
                    JOIN classes c ON c.code=s.course_code WHERE s.term=%s AND s.year=%s GROUP BY c.department ORDER BY c.department""",
                 (term, year))
    for r in rows:
        r["name"] = cfg.DEPARTMENT_NAMES.get(r["prefix"], r["prefix"])
    return rows


def delete_term_offerings(term: str, year: int) -> int:
    return execute("DELETE FROM course_sections WHERE term=%s AND year=%s", (term, year))

# =========================================================================== transfer credit equivalencies
def transfer_map() -> dict[str, str | None]:
    """{transfer course code: MSMU code, or None = reviewed, elective credit only}"""
    return {r["transfer_code"]: r["msmu_code"] for r in query("SELECT transfer_code, msmu_code FROM transfer_equivalencies")}


def transfer_equivalencies() -> list[dict]:
    return query("""SELECT te.transfer_code, te.msmu_code, te.notes, te.decided_at, c.name AS msmu_title,
                           (SELECT COUNT(DISTINCT sc.student_id) FROM student_courses sc
                             WHERE sc.is_transfer AND sc.course_code = te.transfer_code) AS students
                    FROM transfer_equivalencies te LEFT JOIN classes c ON c.code = te.msmu_code ORDER BY te.transfer_code""")


def set_transfer_equivalency(transfer_code: str, msmu_code: str | None, notes: str = "") -> None:
    """msmu_code=None records 'reviewed: elective credit only'. Applies to every student with that transfer course."""
    execute("""INSERT INTO transfer_equivalencies (transfer_code, msmu_code, notes) VALUES (%s,%s,%s)
               ON DUPLICATE KEY UPDATE msmu_code=VALUES(msmu_code), notes=VALUES(notes), decided_at=CURRENT_TIMESTAMP""",
            (transfer_code, msmu_code or None, (notes or "").strip() or None))


def delete_transfer_equivalency(transfer_code: str) -> None:
    execute("DELETE FROM transfer_equivalencies WHERE transfer_code=%s", (transfer_code,))


def msmu_course_candidates() -> list[dict]:
    """Courses that are really MSMU's (rules known, in a program, or in an imported schedule): the pool for suggestions.
    Foreign transfer courses that were auto-added to the catalog are not in this pool."""
    return query("""SELECT c.code, c.name, c.credits FROM classes c
                    WHERE c.when_offered IS NOT NULL
                       OR EXISTS (SELECT 1 FROM program_requirements r WHERE r.course_code = c.code)
                       OR EXISTS (SELECT 1 FROM course_sections s WHERE s.course_code = c.code)
                    ORDER BY c.code""")
