"""Backups that do not depend on mysqldump or Docker: every table is written to one JSON file
with a checksum. Restoring is ATOMIC (all-or-nothing) and takes a safety backup first.

    python backup.py             -> make a manual backup now
    python backup.py list        -> list backups
    python backup.py restore FILE
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import config as cfg
import db

FORMAT = 1


class BackupError(Exception):
    pass


def _tables(cur) -> list[str]:
    cur.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'", (cfg.DB_NAME,))
    names = [r[0] for r in cur.fetchall()]
    cur.execute("""SELECT TABLE_NAME, REFERENCED_TABLE_NAME FROM information_schema.KEY_COLUMN_USAGE
                   WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME IS NOT NULL""", (cfg.DB_NAME,))
    deps: dict[str, set[str]] = {n: set() for n in names}
    for t, ref in cur.fetchall():
        if t != ref and t in deps:
            deps[t].add(ref)
    ordered: list[str] = []
    while deps:                                   # parents before children
        ready = sorted(n for n, d in deps.items() if not (d - set(ordered)))
        if not ready:
            raise BackupError("Circular foreign keys - cannot order tables.")
        for n in ready:
            ordered.append(n); deps.pop(n)
    return ordered


def _columns(cur, table) -> list[str]:
    cur.execute("""SELECT COLUMN_NAME FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND EXTRA NOT LIKE '%%GENERATED%%'
                   ORDER BY ORDINAL_POSITION""", (cfg.DB_NAME, table))
    return [r[0] for r in cur.fetchall()]


def _jsonable(v):
    if v is None or isinstance(v, (int, float, str)):
        return v
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", "replace")
    return str(v)                                  # datetime, date, Decimal -> MySQL accepts the string form


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def make_backup(kind: str = "manual", reason: str = "") -> Path:
    cfg.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    conn = db.connect()
    try:
        cur = conn.cursor()
        cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
        data, counts = {}, {}
        for t in _tables(cur):
            cols = _columns(cur, t)
            cur.execute(f"SELECT {', '.join('`'+c+'`' for c in cols)} FROM `{t}`")
            rows = [[_jsonable(v) for v in r] for r in cur.fetchall()]
            data[t] = {"columns": cols, "rows": rows}
            counts[t] = len(rows)
        cur.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations")
        schema_version = cur.fetchone()[0]
        conn.rollback()
    finally:
        conn.close()
    doc = {"format": FORMAT, "created": datetime.now().isoformat(timespec="seconds"), "kind": kind,
           "reason": reason, "schema_version": schema_version, "counts": counts, "data": data}
    doc["sha256"] = _digest({k: doc[k] for k in ("format", "schema_version", "counts", "data")})
    name = f"{kind}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}.json"
    path = cfg.BACKUP_DIR / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)                              # atomic rename: never leaves a half-written backup
    verify(path)
    if cfg.BACKUP_MIRROR_DIR:
        try:
            Path(cfg.BACKUP_MIRROR_DIR).mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, Path(cfg.BACKUP_MIRROR_DIR) / name)
        except OSError:
            pass                                   # mirror is best-effort; the primary copy exists
    _rotate()
    return path


def verify(path: Path | str) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        ok = doc["sha256"] == _digest({k: doc[k] for k in ("format", "schema_version", "counts", "data")})
    except (OSError, ValueError, KeyError) as e:
        raise BackupError(f"Not a valid backup file: {e}") from e
    if not ok:
        raise BackupError("Backup file is corrupted (checksum mismatch). It was NOT used.")
    return doc


def _rotate():
    autos = sorted(cfg.BACKUP_DIR.glob("auto_*.json"))
    for old in autos[: max(0, len(autos) - cfg.KEEP_AUTO_BACKUPS)]:
        old.unlink(missing_ok=True)


def list_backups() -> list[dict]:
    out = []
    for p in sorted(cfg.BACKUP_DIR.glob("*.json"), reverse=True) if cfg.BACKUP_DIR.exists() else []:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"path": p, "created": d.get("created", ""), "kind": d.get("kind", ""), "reason": d.get("reason", ""),
                        "students": d.get("counts", {}).get("students", 0), "size": p.stat().st_size})
        except (OSError, ValueError):
            out.append({"path": p, "created": "?", "kind": "unreadable", "reason": "", "students": 0, "size": 0})
    return out


def auto_backup(reason: str = "", min_minutes: int = 0) -> Path | None:
    """Safety copy. min_minutes>0 skips if an automatic backup is already that recent."""
    if min_minutes:
        autos = sorted(cfg.BACKUP_DIR.glob("auto_*.json")) if cfg.BACKUP_DIR.exists() else []
        if autos and (datetime.now().timestamp() - autos[-1].stat().st_mtime) < min_minutes * 60:
            return None
    try:
        return make_backup("auto", reason)
    except Exception:
        return None                                # never block the user because a backup failed


def restore(path: Path | str) -> None:
    doc = verify(path)
    if doc["schema_version"] > _current_version():
        raise BackupError("This backup is from a NEWER version of the program. Update the program first.")
    auto_backup("before restore")
    conn = db.connect()
    try:
        cur = conn.cursor()
        order = _tables(cur)                       # parents first; foreign keys stay ENFORCED so bad data cannot get in
        for t in reversed(order):
            cur.execute(f"DELETE FROM `{t}`")
        for t in order:
            part = doc["data"].get(t)
            if part and part["rows"]:
                cols = ", ".join(f"`{c}`" for c in part["columns"])
                marks = ", ".join(["%s"] * len(part["columns"]))
                cur.executemany(f"INSERT INTO `{t}` ({cols}) VALUES ({marks})", [tuple(r) for r in part["rows"]])
        conn.commit()
    except Exception as e:
        conn.rollback()                            # all-or-nothing: the live data is untouched on any error
        raise BackupError(f"Restore failed and was rolled back; nothing changed.\n{e}") from e
    finally:
        conn.close()


def _current_version() -> int:
    rows = db.query("SELECT COALESCE(MAX(version),0) v FROM schema_migrations")
    return rows[0]["v"]


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("created", make_backup("manual", "command line"))
    elif args[0] == "list":
        for b in list_backups():
            print(b["created"], b["kind"], b["students"], "students", b["path"].name)
    elif args[0] == "restore" and len(args) == 2:
        restore(args[1]); print("restored")
    else:
        print(__doc__)
