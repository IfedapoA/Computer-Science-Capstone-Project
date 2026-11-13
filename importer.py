"""CSV batch import: student rosters, transcripts, and outside majors/minors.
Two-step design: parse_* validates and returns a PREVIEW (nothing is written);
commit_* writes only valid rows in one transaction."""
from __future__ import annotations

import csv
import re
from collections import Counter
from datetime import datetime
from dataclasses import dataclass, field

import backup
import db
from audit import Course, is_offered

TRANSCRIPT_COLUMNS = ["student_email", "course_code", "term", "year", "status", "grade", "transfer", "title", "credits"]
ROSTER_COLUMNS = ["first_name", "last_name", "email", "catalog_year", "programs", "advisor_email"]
PROGRAM_COLUMNS = ["program_code", "program_name", "type", "credits_required", "department", "course_code",
                   "requirement_type", "electives_needed", "catalog_year", "course_title", "course_credits"]

_STATUS = {"completed": "Completed", "complete": "Completed", "done": "Completed", "c": "Completed",
           "in progress": "In Progress", "in-progress": "In Progress", "inprogress": "In Progress", "ip": "In Progress",
           "current": "In Progress", "planned": "Planned", "plan": "Planned", "p": "Planned"}
_TERM = {"fall": "Fall", "fa": "Fall", "f": "Fall", "spring": "Spring", "sp": "Spring", "s": "Spring",
         "summer": "Summer", "su": "Summer"}
_ALIASES = {"course": "code", "course_code": "code", "course code": "code", "code": "code",
            "course_title": "title", "course title": "title", "title": "title", "name": "title", "course name": "title",
            "credit": "credits", "credits": "credits", "credit hours": "credits", "hours": "credits", "course_credits": "credits"}
CODE_RX = re.compile(r"^[A-Z]{2,6} \d{3}[A-Z]?$")
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class Preview:
    kind: str
    valid: list[dict] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)
    total_rows: int = 0
    new_courses: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    title_updates: list[tuple] = field(default_factory=list)


def normalize_code(raw: str) -> str:
    """'cmsci120', 'CMSCI  120' -> 'CMSCI 120'"""
    s = re.sub(r"\s+", " ", (raw or "").strip().upper().replace("-", " "))
    m = re.match(r"^([A-Z]{2,6})\s*(\d{3}[A-Z]?)$", s)
    return f"{m.group(1)} {m.group(2)}" if m else s


def _credits(raw, default=3):
    try:
        v = float(str(raw).strip())
        return int(round(v)) if 0 <= v <= 12 else default
    except ValueError:
        return default


def _read(path, required: list[str]):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        if not rd.fieldnames:
            raise ValueError("The file is empty.")
        header = {}
        for h in rd.fieldnames:
            k = h.strip().lower()
            header[_ALIASES.get(k, k)] = h
        if "code" in required and "code" not in header and "subject" in header and "number" in header:
            pass
        missing = [c for c in required if c not in header and not (c == "code" and "subject" in header and "number" in header)]
        if missing:
            raise ValueError("Missing column(s): " + ", ".join(missing) + "\nExpected header: " + ",".join(required))
        rows = []
        for r in rd:
            d = {k: (r.get(h) or "").strip() for k, h in header.items()}
            if "code" not in d and "subject" in d:
                d["code"] = f"{d['subject']} {d['number']}"
            rows.append(d)
    return rows


# ------------------------------------------------------------------ Transcripts
def parse_transcript(path, add_missing: bool = False, allowed_advisor_id: int | None = None) -> Preview:
    rows = _read(path, ["student_email", "code", "term", "year", "status"])
    pv = Preview("transcript", total_rows=len(rows))
    courses = {c["code"] for c in db.all_courses()}
    students = {s["email_address"].lower(): s for s in db.list_students()}
    seen, new = set(), {}
    for i, r in enumerate(rows, start=2):
        email = r["student_email"].lower()
        code = normalize_code(r["code"])
        term = _TERM.get(r["term"].lower())
        status = _STATUS.get(r["status"].lower())
        err = None
        if email not in students:
            err = f"Unknown student '{r['student_email']}'"
        elif allowed_advisor_id is not None and students[email]["advisor_id"] != allowed_advisor_id:
            err = f"'{r['student_email']}' is not one of your advisees"
        elif code not in courses and not (add_missing and CODE_RX.match(code)):
            err = f"Course '{r['code']}' is not in the catalog"
        elif not term:
            err = f"Invalid term '{r['term']}' (use Fall, Spring, or Summer)"
        elif not r["year"].isdigit() or not (1990 <= int(r["year"]) <= 2100):
            err = f"Invalid year '{r['year']}'"
        elif not status:
            err = f"Invalid status '{r['status']}'"
        elif status == "Completed" and not r.get("grade", ""):
            err = "Completed courses need a grade"
        if not err:
            key = (email, code, term, r["year"])
            if key in seen:
                err = "Duplicate row in this file"
            seen.add(key)
        if err:
            pv.errors.append((i, err))
            continue
        if code not in courses and code not in new:
            new[code] = {"code": code, "name": r.get("title") or code, "credits": _credits(r.get("credits", ""))}
        pv.valid.append({"student_id": students[email]["id"], "email": email, "course_code": code, "term": term,
                         "year": int(r["year"]), "status": status, "grade": (r.get("grade", "").upper() or None) if status == "Completed" else None,
                         "is_transfer": r.get("transfer", "").lower() in ("1", "y", "yes", "true", "t"),
                         "source_title": (r.get("title") or "")[:200] or None,
                         "source_credits": float(r["credits"]) if re.match(r"^\d+(\.\d+)?$", r.get("credits", "")) else None})
    pv.new_courses = list(new.values())
    return pv


def commit_transcript(pv: Preview) -> int:
    backup.auto_backup("before transcript import")
    with db.tx() as cur:
        if pv.new_courses:
            cur.executemany("INSERT IGNORE INTO classes (code, name, credits) VALUES (%s, %s, %s)",
                            [(c["code"], c["name"], c["credits"]) for c in pv.new_courses])
        cur.executemany("""INSERT INTO student_courses (student_id, course_code, term, year, status, grade, is_transfer, source_title, source_credits)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON DUPLICATE KEY UPDATE status=VALUES(status), grade=VALUES(grade), is_transfer=VALUES(is_transfer),
                                                   source_title=VALUES(source_title), source_credits=VALUES(source_credits)""",
                        [(r["student_id"], r["course_code"], r["term"], r["year"], r["status"], r["grade"], r["is_transfer"],
                          r.get("source_title"), r.get("source_credits")) for r in pv.valid])
    return len(pv.valid)


# ------------------------------------------------------------------ Roster
def parse_roster(path) -> Preview:
    rows = _read(path, ["first_name", "last_name", "email", "catalog_year", "programs"])
    pv = Preview("roster", total_rows=len(rows))
    years = {y["label"]: y["id"] for y in db.catalog_years()}
    progs = {p["code"].lower(): p["id"] for p in db.all_programs(base_only=True)}
    advisors = {a["email_address"].lower(): a["id"] for a in db.list_advisors()}
    existing = {s["email_address"].lower() for s in db.list_students()}
    seen = set()
    for i, r in enumerate(rows, start=2):
        email = r["email"].lower()
        err, pids = None, []
        if not r["first_name"] or not r["last_name"]:
            err = "First and last name are required"
        elif not EMAIL_RX.match(email):
            err = f"Invalid e-mail '{r['email']}'"
        elif email in existing:
            err = "Student already exists"
        elif email in seen:
            err = "Duplicate e-mail in this file"
        elif r["catalog_year"] not in years:
            err = f"Unknown catalog year '{r['catalog_year']}'"
        else:
            for code in [c.strip() for c in re.split(r"[;|]", r["programs"]) if c.strip()]:
                if code.lower() not in progs:
                    err = f"Unknown program '{code}'"
                    break
                pids.append(progs[code.lower()])
            adv = r.get("advisor_email", "").lower()
            if not err and adv and adv not in advisors:
                err = f"Unknown advisor '{r.get('advisor_email')}'"
        seen.add(email)
        if err:
            pv.errors.append((i, err))
        else:
            pv.valid.append({"first": r["first_name"], "last": r["last_name"], "email": email,
                             "catalog_year_id": years[r["catalog_year"]], "program_ids": pids,
                             "advisor_id": advisors.get(r.get("advisor_email", "").lower())})
    return pv


def commit_roster(pv: Preview) -> int:
    backup.auto_backup("before roster import")
    with db.tx() as cur:
        for r in pv.valid:
            cur.execute("INSERT INTO students (first_name, last_name, email_address, catalog_year_id, advisor_id) VALUES (%s, %s, %s, %s, %s)",
                        (r["first"], r["last"], r["email"], r["catalog_year_id"], r["advisor_id"]))
            sid = cur.lastrowid
            if r["program_ids"]:
                cur.executemany("INSERT INTO student_programs VALUES (%s, %s)", [(sid, p) for p in r["program_ids"]])
    return len(pv.valid)


# ------------------------------------------------------------------ Outside Majors / Minors
def parse_programs(path) -> Preview:
    rows = _read(path, ["program_code", "program_name", "type", "code"])
    pv = Preview("programs", total_rows=len(rows))
    courses = {c["code"] for c in db.all_courses()}
    years = {y["label"]: y["id"] for y in db.catalog_years()}
    existing = {p["code"].lower(): p for p in db.all_programs()}
    progs: dict[str, dict] = {}
    new = {}
    for i, r in enumerate(rows, start=2):
        pcode = r["program_code"].strip()
        ptype = {"major": "Major", "minor": "Minor"}.get(r["type"].lower())
        code = normalize_code(r["code"]) if r["code"] else ""
        rtype = {"core": "Core", "required": "Core", "": "Core", "elective": "Elective"}.get(r.get("requirement_type", "").lower())
        err = None
        if not pcode or not r["program_name"]:
            err = "program_code and program_name are required"
        elif not ptype:
            err = f"type must be Major or Minor (got '{r['type']}')"
        elif pcode.lower() in existing and not existing[pcode.lower()]["is_custom"]:
            err = f"'{pcode}' is a built-in program and cannot be overwritten"
        elif r.get("catalog_year") and r["catalog_year"] not in years:
            err = f"Unknown catalog year '{r['catalog_year']}'"
        elif code and code not in courses and not CODE_RX.match(code):
            err = f"Invalid course code '{r['code']}'"
        elif rtype is None:
            err = "requirement_type must be Core or Elective"
        if err:
            pv.errors.append((i, err))
            continue
        p = progs.setdefault(pcode, {"code": pcode, "name": r["program_name"], "type": ptype, "department": r.get("department", ""),
                                     "credits_required": 0, "electives_needed": 0, "reqs": []})
        if r.get("credits_required", "").isdigit():
            p["credits_required"] = int(r["credits_required"])
        if r.get("electives_needed", "").isdigit():
            p["electives_needed"] = int(r["electives_needed"])
        if code:
            p["reqs"].append((code, rtype, years.get(r.get("catalog_year", ""))))
            if code not in courses and code not in new:
                new[code] = {"code": code, "name": r.get("title") or code, "credits": _credits(r.get("credits", ""))}
    pv.valid = list(progs.values())
    pv.new_courses = list(new.values())
    pv.notes = [f"{len(p['reqs'])} requirement course(s) for {p['code']}" for p in pv.valid]
    return pv


def commit_programs(pv: Preview) -> int:
    backup.auto_backup("before programs import")
    year_ids = [y["id"] for y in db.catalog_years()]
    with db.tx() as cur:
        if pv.new_courses:
            cur.executemany("INSERT IGNORE INTO classes (code, name, credits) VALUES (%s, %s, %s)",
                            [(c["code"], c["name"], c["credits"]) for c in pv.new_courses])
        for p in pv.valid:
            cur.execute("""INSERT INTO programs (code, name, type, credits_required, department, is_custom) VALUES (%s, %s, %s, %s, %s, TRUE)
                           ON DUPLICATE KEY UPDATE name=VALUES(name), type=VALUES(type), credits_required=VALUES(credits_required),
                                                   department=VALUES(department)""",
                        (p["code"], p["name"], p["type"], p["credits_required"], p["department"] or None))
            cur.execute("SELECT id FROM programs WHERE code=%s", (p["code"],))
            pid = cur.fetchone()[0]
            for code, rtype, y in p["reqs"]:
                for yid in ([y] if y else year_ids):
                    cur.execute("""INSERT INTO program_requirements VALUES (%s, %s, %s, %s)
                                   ON DUPLICATE KEY UPDATE requirement_type=VALUES(requirement_type)""", (yid, pid, code, rtype))
            for yid in year_ids:
                cur.execute("""INSERT INTO program_rules VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE electives_needed=VALUES(electives_needed)""",
                            (yid, pid, p["electives_needed"]))
    return len(pv.valid)

# ------------------------------------------------------------------ Semester course offerings (the schedule of classes)
# One row per class SECTION (and per meeting pattern), e.g.  ACCT-101-A , BIOL-110-H-L (a lab) , CHEM-101-A-R (a recitation).
OFFERING_COLUMNS = ["code", "subterm", "title", "credits", "type", "capacity", "enrollment", "location", "room",
                    "professor", "days", "start", "finish", "start_date", "end_date"]
_SECTION_RX = re.compile(r"^([A-Z]{2,6})-(\d{3}[A-Z]?)-([A-Z0-9]{1,3})(?:-([A-Z]))?$")       # DEPT-123-SEC[-L|-R]
_COMPONENT = {"L": "Lab", "R": "Recitation"}
_MONTH_TERM = {8: "Fall", 9: "Fall", 1: "Spring", 2: "Spring", 3: "Spring", 5: "Summer", 6: "Summer", 7: "Summer"}
_DATE_FORMATS = ("%b %d %Y", "%B %d %Y", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d")
_TIME_FORMATS = ("%I:%M %p", "%I:%M%p", "%H:%M")


def _parse_date(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(raw)


def _parse_time(raw: str):
    raw = (raw or "").strip().upper()
    if not raw:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%H:%M:%S")
        except ValueError:
            pass
    raise ValueError(raw)


def detect_term(rows: list[dict]) -> tuple[str, int] | None:
    """Fall / Spring / Summer + year from the most common start date (Aug 26 2026 -> Fall 2026)."""
    c: Counter = Counter()
    for r in rows:
        try:
            d = _parse_date(r.get("start_date", ""))
        except ValueError:
            continue
        if d and d.month in _MONTH_TERM:
            c[(_MONTH_TERM[d.month], d.year)] += 1
    return c.most_common(1)[0][0] if c else None


def parse_offerings(path, term: str | None = None, year: int | None = None) -> Preview:
    rows = _read(path, ["code", "title", "credits"])
    pv = Preview("offerings", total_rows=len(rows))
    if not (term and year):
        guess = detect_term(rows)
        if not guess:
            raise ValueError("Could not tell which semester this file is from (no usable start dates).\n"
                             "Choose the semester and the year above, then press Validate again.")
        term, year = guess
    catalog = {c["code"]: c for c in db.all_courses()}
    seen = set()
    per_course: dict[str, dict[str, list]] = {}
    for i, r in enumerate(rows, start=2):
        m = _SECTION_RX.match(r["code"].strip().upper())
        err = None
        if not m:
            err = f"Cannot read the section code '{r['code']}' (expected something like ACCT-101-A or BIOL-110-H-L)"
        else:
            try:
                start_t, end_t = _parse_time(r.get("start", "")), _parse_time(r.get("finish", ""))
                start_d, end_d = _parse_date(r.get("start_date", "")), _parse_date(r.get("end_date", ""))
            except ValueError as e:
                err = f"Cannot read the time or date '{e.args[0]}'"
        if not err and not r["title"]:
            err = "The course title is empty"
        if err:
            pv.errors.append((i, err)); continue
        dept, num, sec, comp = m.groups()
        code = f"{dept} {num}"
        component = _COMPONENT.get(comp or "", "Lecture")
        if comp and comp not in _COMPONENT:
            sec = f"{sec}-{comp}"                                          # unknown suffix: keep it as part of the section
        prof = r.get("professor", "").strip()
        rec = {"term": term, "year": year, "course_code": code, "section": sec, "component": component,
               "subterm": r.get("subterm") or None, "title": r["title"][:200], "credits": _credits(r["credits"], default=0),
               "delivery": r.get("type") or None,
               "capacity": int(r["capacity"]) if r.get("capacity", "").isdigit() else None,
               "enrollment": int(r["enrollment"]) if r.get("enrollment", "").isdigit() else None,
               "location": r.get("location") or None, "room": r.get("room") or None,
               "professor": None if (not prof or prof.lower().startswith("jenzabar")) else prof,     # system placeholder = unassigned
               "days": r.get("days") or None, "start_time": start_t, "end_time": end_t, "start_date": start_d, "end_date": end_d}
        key = (code, sec, component, rec["days"], start_t, end_t, rec["room"])
        if key in seen:
            pv.errors.append((i, "Duplicate of an earlier row (same section, days, time and room)")); continue
        seen.add(key)
        pv.valid.append(rec)
        # the COURSE's own title/credits come from lecture rows only: lab and recitation rows say "... Lab", 0 credits
        per_course.setdefault(code, {"Lecture": [], "other": []})["Lecture" if component == "Lecture" else "other"].append((rec["title"], rec["credits"]))

    offered = set(per_course)
    for code, parts in sorted(per_course.items()):
        if code in catalog:
            continue
        pool = parts["Lecture"] or parts["other"]
        titles = Counter(t for t, _ in pool)
        title = sorted(titles.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]                 # most common title, then alphabetical
        credits = Counter(c for _, c in pool).most_common(1)[0][0]
        note = ("Section titles vary: " + "; ".join(sorted(titles)))[:240] if len(titles) > 1 else None
        pv.new_courses.append({"code": code, "name": title, "credits": credits, "notes": note})

    # how this semester's real schedule compares with the catalog's Fall/Spring/odd-even rules
    diffs = []
    for code, c in sorted(catalog.items()):
        if c["when_offered"] is None:
            continue
        predicted = is_offered(Course(code, c["name"], c["credits"], c["when_offered"], c["notes"] or ""), term, year)[0]
        if predicted and code not in offered:
            diffs.append(f"{code}: your catalog expects it in {term} {year}, but it is NOT in this schedule")
        elif not predicted and code in offered:
            diffs.append(f"{code}: your catalog says it is not offered in {term} {year}, but it IS in this schedule")
        elif code in per_course and per_course[code]["Lecture"]:
            sched = Counter(cr for _, cr in per_course[code]["Lecture"]).most_common(1)[0][0]
            if sched != c["credits"]:
                diffs.append(f"{code}: the schedule says {sched} credit(s), your catalog says {c['credits']}")
    pv.notes = diffs
    pv.title_updates = [(code, sorted(Counter(t for t, _ in (parts["Lecture"] or parts["other"])).items(), key=lambda kv: (-kv[1], kv[0]))[0][0])
                        for code, parts in per_course.items() if code in catalog and "(title to import)" in (catalog[code]["name"] or "")]
    pv.meta = {"term": term, "year": year, "courses": len(per_course), "sections": len({(r['course_code'], r['section']) for r in pv.valid}),
               "meetings": len(pv.valid), "departments": len({c.split()[0] for c in per_course})}
    return pv


def commit_offerings(pv: Preview) -> int:
    """Re-importing a semester REPLACES that semester only (other semesters are untouched). One transaction."""
    backup.auto_backup(f"before importing {pv.meta['term']} {pv.meta['year']} offerings")
    t, y = pv.meta["term"], pv.meta["year"]
    cols = ("term", "year", "course_code", "section", "component", "subterm", "title", "credits", "delivery", "capacity",
            "enrollment", "location", "room", "professor", "days", "start_time", "end_time", "start_date", "end_date")
    with db.tx() as cur:
        if pv.new_courses:
            cur.executemany("INSERT IGNORE INTO classes (code, name, credits, notes) VALUES (%s, %s, %s, %s)",
                            [(c["code"], c["name"], c["credits"], c.get("notes")) for c in pv.new_courses])
        if pv.title_updates:
            cur.executemany("UPDATE classes SET name=%s WHERE code=%s AND name LIKE '%%(title to import)%%'", [(n, c) for c, n in pv.title_updates])
        cur.execute("DELETE FROM course_sections WHERE term=%s AND year=%s", (t, y))
        cur.executemany(f"INSERT INTO course_sections ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                        [tuple(r[c] for c in cols) for r in pv.valid])
    return len(pv.valid)