"""
Degree audit, CORE curriculum, prerequisite checking, graduation projection and What-If.
Pure Python: no database and no UI imports, so it is fully testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Optional

FAIL_GRADES = {"F", "W", "WF", "I", "NP", "U"}
STATUS_RANK = {"Completed": 3, "In Progress": 2, "Planned": 1}
CORE_RANK = {"Fr": 0, "So": 1, "Ju": 2, "Sr": 3}
CORE_PREFIX = "CORE: "


# --------------------------------------------------------------------------- Data Model
@dataclass(frozen=True)
class Course:
    code: str
    name: str
    credits: int = 3
    when_offered: Optional[str] = None      # Fall | Spring | Both | Not Offered | None (unknown)
    notes: str = ""


@dataclass(frozen=True)
class Program:
    id: int
    code: str
    name: str
    type: str
    credits_required: int = 0
    is_custom: bool = False


@dataclass
class ProgramReqs:
    core: list[str] = field(default_factory=list)
    electives: list[str] = field(default_factory=list)
    electives_needed: int = 0


@dataclass(frozen=True)
class CoreReq:
    id: int
    name: str
    take_as: str = "Fr"
    offered: str = "Both"
    credits: int = 3
    manual_only: bool = False
    notes: str = ""
    options: tuple = ()


@dataclass
class Catalog:
    courses: dict[str, Course]
    prereqs: dict[str, dict[int, set[str]]]
    programs: dict[int, Program]
    requirements: dict[int, ProgramReqs]
    core: list[CoreReq] = field(default_factory=list)
    offerings: dict[tuple[int, str], set[str]] = field(default_factory=dict)   # {(year, term): codes in that semester's schedule}


@dataclass(frozen=True)
class TakenCourse:
    code: str
    term: str
    year: int
    status: str
    grade: Optional[str] = None
    is_transfer: bool = False
    transfer_from: str = ""            # the transcript's own code when this row was re-pointed to an MSMU course


@dataclass
class StudentRecord:
    id: int
    name: str
    catalog_year: str
    program_ids: list[int]
    courses: list[TakenCourse]
    substitutions: dict[str, str] = field(default_factory=dict)
    core_overrides: dict[int, tuple] = field(default_factory=dict)    # core_id -> (course_code|None, note)
    transfer_map: dict[str, Optional[str]] = field(default_factory=dict)   # transfer code -> MSMU code (None = elective credit only)


# --------------------------------------------------------------------------- Results
@dataclass
class ReqItem:
    code: str
    name: str
    credits: int
    kind: str
    status: str
    when: str = ""
    grade: str = ""
    via: str = ""
    also_counts_for: list[str] = field(default_factory=list)


@dataclass
class ProgramAudit:
    program: Program
    items: list[ReqItem]
    electives_needed: int
    electives_remaining: int
    elective_options: list[str]
    credits_completed: int
    credits_in_progress: int
    units_total: int
    units_completed: int
    units_in_progress: int

    @property
    def percent_complete(self) -> float:
        return 100.0 * self.units_completed / self.units_total if self.units_total else 100.0


@dataclass
class CoreItem:
    req: CoreReq
    status: str
    satisfied_by: str = ""
    when: str = ""
    grade: str = ""
    note: str = ""


@dataclass
class CoreAudit:
    items: list[CoreItem]
    units_total: int
    units_completed: int
    units_in_progress: int

    @property
    def percent_complete(self) -> float:
        return 100.0 * self.units_completed / self.units_total if self.units_total else 100.0


@dataclass
class AuditResult:
    programs: list[ProgramAudit]
    shared_courses: dict[str, list[str]]
    unique_remaining: int
    core: Optional[CoreAudit] = None


@dataclass
class PlannedTerm:
    label: str
    year: int
    term: str
    courses: list[str]
    credits: int
    pinned: list[str] = field(default_factory=list)


@dataclass
class Projection:
    start_label: str
    terms: list[PlannedTerm]
    graduation_label: Optional[str]
    blocked: list[tuple[str, str]]
    warnings: list[str]
    assumptions: list[str]
    extra_prereq_courses: list[str]
    semesters_remaining: int
    course_info: dict[str, Course] = field(default_factory=dict)


# --------------------------------------------------------------------------- Term & Prereq Helpers
def term_label(year: int, term: str) -> str:
    return f"{term} {year}"


def current_term(today: Optional[date] = None) -> tuple[int, str]:
    today = today or date.today()
    if today.month >= 8:
        return today.year, "Fall"
    return today.year, "Spring"


def next_term(year: int, term: str) -> tuple[int, str]:
    return (year, "Fall") if term in ("Spring", "Summer") else (year + 1, "Spring")


def term_index(year: int, term: str) -> int:
    return year * 3 + {"Spring": 0, "Summer": 1, "Fall": 2}[term]


def is_offered(course: Course, term: str, year: int) -> tuple[bool, bool]:
    wo = course.when_offered
    if wo == "Not Offered":
        return False, False
    uncertain = wo is None or "rotating" in (course.notes or "").lower()
    if term == "Summer":
        return False, False
    if wo == "Fall" and term != "Fall":
        return False, False
    if wo == "Spring" and term != "Spring":
        return False, False
    notes = (course.notes or "").lower()
    if re.search(r"\bodd years\b", notes) and year % 2 == 0:
        return False, uncertain
    if re.search(r"\beven years\b", notes) and year % 2 == 1:
        return False, uncertain
    return True, uncertain


def offered_in(catalog: Catalog, course: Course, term: str, year: int) -> tuple[bool, bool]:
    """If that semester's real schedule (e.g. fall.csv) was imported, it decides. Otherwise use the catalog rules
    (Fall / Spring / Both and the 'odd years' / 'even years' notes). CORE placeholders always use their own rule."""
    offs = catalog.offerings.get((year, term))
    if offs and not course.code.startswith(CORE_PREFIX):
        return course.code in offs, False
    return is_offered(course, term, year)


def missing_prereqs(catalog: Catalog, code: str, satisfied: set[str]) -> list[list[str]]:
    return [sorted(alts) for _g, alts in sorted(catalog.prereqs.get(code, {}).items()) if not (alts & satisfied)]


def prereqs_ok(catalog: Catalog, code: str, satisfied: set[str]) -> bool:
    return not missing_prereqs(catalog, code, satisfied)


def effective_status(tc: TakenCourse) -> Optional[str]:
    if tc.status == "Completed":
        if tc.grade and tc.grade.strip().upper() in FAIL_GRADES:
            return None
        return "Completed"
    return tc.status


def best_records(student: StudentRecord) -> dict[str, tuple[str, TakenCourse]]:
    """Best record per course the student can be credited with. A TRANSFER course with an advisor decision is credited
    as its MSMU equivalent (decision = None means 'elective credit only': it satisfies no requirement)."""
    best: dict[str, tuple[str, TakenCourse]] = {}
    for tc in student.courses:
        st = effective_status(tc)
        if st is None:
            continue
        if tc.is_transfer and tc.code in student.transfer_map:
            target = student.transfer_map[tc.code]
            if not target:
                continue
            tc = replace(tc, code=target, transfer_from=tc.code)
        cur = best.get(tc.code)
        if cur is None or STATUS_RANK[st] > STATUS_RANK[cur[0]]:
            best[tc.code] = (st, tc)
    return best


def _lookup(best, student, code):
    if code in best:
        st, tc = best[code]
        return st, tc, ""
    sub = student.substitutions.get(code)
    if sub and sub in best:
        st, tc = best[sub]
        return st, tc, sub
    return "Remaining", None, ""


def _when(tc: Optional[TakenCourse]) -> str:
    if not tc:
        return ""
    return term_label(tc.year, tc.term) if tc.year else "(what-if)"


# --------------------------------------------------------------------------- CORE Audit
def option_matches(option: str, code: str) -> bool:
    if "x" not in option:
        return option.strip().upper() == code.strip().upper()
    rx = "".join("[A-Z0-9]" if ch == "x" else re.escape(ch.upper()) for ch in option.strip())
    return re.fullmatch(rx, code.strip().upper()) is not None


def audit_core(student: StudentRecord, catalog: Catalog) -> Optional[CoreAudit]:
    if not catalog.core:
        return None
    best = best_records(student)
    used: set[str] = set()
    results: dict[int, CoreItem] = {}
    order = sorted(catalog.core, key=lambda r: (any("x" in o for o in r.options), r.id))
    for req in order:
        ov = student.core_overrides.get(req.id)
        if ov is not None:
            code, note = ov
            tc = best.get(code, (None, None))[1] if code else None
            results[req.id] = CoreItem(req, "Completed", code or "", _when(tc), (tc.grade or "") if tc else "", note or "Marked satisfied by advisor")
            if code:
                used.add(code)
            continue
        found = None
        for code, (st, tc) in sorted(best.items(), key=lambda kv: -STATUS_RANK[kv[1][0]]):
            if code in used:
                continue
            if any(option_matches(o, code) for o in req.options):
                found = (code, st, tc)
                break
        if found:
            code, st, tc = found
            used.add(code)
            results[req.id] = CoreItem(req, st, code, _when(tc), tc.grade or "", f"via {tc.transfer_from} transfer" if tc.transfer_from else "")
        else:
            results[req.id] = CoreItem(req, "Remaining")
    items = [results[r.id] for r in catalog.core]
    return CoreAudit(items, len(items), sum(i.status == "Completed" for i in items), sum(i.status == "In Progress" for i in items))


# --------------------------------------------------------------------------- Degree Audit
def audit_student(student: StudentRecord, catalog: Catalog) -> AuditResult:
    best = best_records(student)
    progs = [catalog.programs[pid] for pid in student.program_ids if pid in catalog.programs]
    appears: dict[str, set[str]] = {}
    for p in progs:
        r = catalog.requirements.get(p.id, ProgramReqs())
        for c in list(r.core) + list(r.electives):
            appears.setdefault(c, set()).add(p.code)
    results: list[ProgramAudit] = []
    remaining_codes: set[str] = set()
    for p in progs:
        reqs = catalog.requirements.get(p.id, ProgramReqs())
        items: list[ReqItem] = []
        done = inprog = cr_done = cr_inprog = 0

        def mk(code, kind, st, tc, via):
            course = catalog.courses.get(code) or Course(code, code)
            if tc is not None and tc.transfer_from and not via:
                via = f"{tc.transfer_from} transfer"
            return ReqItem(code, course.name, course.credits, kind, st, _when(tc), (tc.grade or "") if tc else "", via, sorted(appears.get(code, set()) - {p.code}))

        for code in reqs.core:
            st, tc, via = _lookup(best, student, code)
            it = mk(code, "Core", st, tc, via)
            items.append(it)
            if st == "Completed":
                done += 1; cr_done += it.credits
            elif st == "In Progress":
                inprog += 1; cr_inprog += it.credits
            elif st == "Remaining":
                remaining_codes.add(code)
        taken = []
        for code in reqs.electives:
            st, tc, via = _lookup(best, student, code)
            if st != "Remaining":
                taken.append((-STATUS_RANK[st], code, st, tc, via))
        taken.sort(key=lambda t: (t[0], t[1]))
        counted = taken[: reqs.electives_needed]
        for _r, code, st, tc, via in counted:
            it = mk(code, "Elective", st, tc, via)
            items.append(it)
            if st == "Completed":
                done += 1; cr_done += it.credits
            elif st == "In Progress":
                inprog += 1; cr_inprog += it.credits
        left = max(0, reqs.electives_needed - len(counted))
        counted_codes = {c[1] for c in counted}
        pool_left = [c for c in reqs.electives if c not in best and c not in counted_codes]
        if left:
            items.append(ReqItem(f"{left} elective(s)", "Choose from the elective list for this program", 0, "Elective", "Remaining"))
        results.append(ProgramAudit(p, items, reqs.electives_needed, left, pool_left, cr_done, cr_inprog, len(reqs.core) + reqs.electives_needed, done, inprog))
    shared = {c: sorted(ps) for c, ps in appears.items() if len(ps) > 1}
    return AuditResult(results, shared, len(remaining_codes) + sum(r.electives_remaining for r in results), audit_core(student, catalog))


# --------------------------------------------------------------------------- Graduation Projection
def project_graduation(student: StudentRecord, catalog: Catalog, *, max_credits: int = 15,
                       today: Optional[date] = None, max_terms: int = 14, include_core: bool = True) -> Projection:
    cur_year, cur_term = current_term(today)
    start_year, start_term = next_term(cur_year, cur_term)
    best = best_records(student)
    satisfied = {c for c, (st, _tc) in best.items() if st in ("Completed", "In Progress")}
    for req, sub in student.substitutions.items():
        if sub in satisfied:
            satisfied.add(req)

    courses = dict(catalog.courses)
    assumptions: list[str] = []
    warnings: list[str] = []
    progs = [catalog.programs[pid] for pid in student.program_ids if pid in catalog.programs]

    needed: set[str] = set()
    core_rank: dict[str, int] = {}
    for p in progs:
        for c in catalog.requirements.get(p.id, ProgramReqs()).core:
            if c not in satisfied:
                needed.add(c)

    if include_core:
        ca = audit_core(student, catalog)
        for it in (ca.items if ca else []):
            r = it.req
            if it.status in ("Completed", "In Progress"):
                continue
            if it.status == "Planned" and it.satisfied_by:
                code = it.satisfied_by
            else:
                fixed = [o for o in r.options if "x" not in o]
                if len(r.options) == 1 and len(fixed) == 1 and fixed[0] in courses:
                    code = fixed[0]
                else:
                    code = CORE_PREFIX + r.name
                    courses[code] = Course(code, r.name, r.credits, r.offered, "")
            if code in satisfied:
                continue
            needed.add(code)
            core_rank[code] = CORE_RANK.get(r.take_as, 1)

    merged = dict(catalog.prereqs)
    for c in list(needed):
        m = re.match(rf"^({re.escape(CORE_PREFIX)}.*) 2$", c)
        if m and f"{m.group(1)} 1" in needed:
            merged[c] = {**merged.get(c, {}), 99: {f"{m.group(1)} 1"}}
    catalog = replace(catalog, prereqs=merged)

    def depth(code, seen=()):
        if code in seen:
            return 0
        d = 0
        for alts in catalog.prereqs.get(code, {}).values():
            if alts & satisfied:
                continue
            d = max(d, 1 + min((depth(a, seen + (code,)) for a in alts), default=0))
        return d

    chosen_electives: set[str] = set()
    for p in progs:
        reqs = catalog.requirements.get(p.id, ProgramReqs())
        have = sum(1 for c in reqs.electives if c in satisfied)
        planned_pool = [c for c in reqs.electives if c in best and best[c][0] == "Planned"]
        for c in planned_pool[: max(0, reqs.electives_needed - have)]:
            chosen_electives.add(c); needed.add(c)
        k = max(0, reqs.electives_needed - have - len(planned_pool))
        if not k:
            continue
        pool = [c for c in reqs.electives if c not in satisfied]
        free = [c for c in pool if c in needed or c in chosen_electives]
        rest = [c for c in pool if c not in free]

        def rank(c):
            course = courses.get(c)
            off = course.when_offered if course else None
            return (off == "Not Offered", off is None, depth(c), c)
        rest.sort(key=rank)
        picks = (free + rest)[:k]
        for c in picks:
            chosen_electives.add(c); needed.add(c)
        if len(picks) < k:
            warnings.append(f"{p.code}: only {len(picks)} of {k} remaining electives are available in the pool.")

    extra: set[str] = set()
    stack = list(needed)
    while stack:
        c = stack.pop()
        for alts in catalog.prereqs.get(c, {}).values():
            if alts & (satisfied | needed):
                continue
            pick = sorted(alts, key=lambda a: (depth(a), a))[0]
            needed.add(pick); extra.add(pick); stack.append(pick)

    deps: dict[str, set[str]] = {c: set() for c in needed}
    for c in needed:
        for alts in catalog.prereqs.get(c, {}).values():
            for a in alts:
                if a in needed:
                    deps[a].add(c)
    memo: dict[str, int] = {}

    def chain(c, seen=()):
        if c in memo:
            return memo[c]
        if c in seen:
            return 1
        v = 1 + max((chain(d, seen + (c,)) for d in deps.get(c, ())), default=0)
        memo[c] = v
        return v

    def scarcity(c):
        course = courses.get(c) or Course(c, c)
        yy, tt, n = start_year, start_term, 0
        for _ in range(8):
            n += offered_in(catalog, course, tt, yy)[0]
            yy, tt = next_term(yy, tt)
        return n

    pinned: dict[tuple[int, str], set[str]] = {}
    for tc in student.courses:
        if tc.status == "Planned" and tc.code in needed and term_index(tc.year, tc.term) >= term_index(start_year, start_term):
            pinned.setdefault((tc.year, tc.term), set()).add(tc.code)
    pin_of = {c: k for k, cs in pinned.items() for c in cs}

    done = set(satisfied)
    pending = set(needed)
    terms: list[PlannedTerm] = []
    y, t = start_year, start_term
    idle = 0
    elapsed = last_used = 0
    uncertain_used: set[str] = set()

    def info(c):
        return courses.get(c) or Course(c, c)

    for _ in range(max_terms):
        if not pending:
            break
        elapsed += 1
        eligible = []
        for c in pending:
            if c in pin_of and pin_of[c] != (y, t):
                continue
            ok, unc = offered_in(catalog, info(c), t, y)
            if ok and prereqs_ok(catalog, c, done):
                eligible.append((c, unc))
        pin_here = {c for c in pinned.get((y, t), set()) if c in pending}
        for c in sorted(pin_here):
            if not prereqs_ok(catalog, c, done):
                warnings.append(f"{c} is planned for {term_label(y, t)} but its prerequisites are not met by then.")
        chosen: list[str] = sorted(pin_here)
        credits = sum(info(c).credits for c in chosen)
        for c, unc in sorted(eligible, key=lambda e: (-chain(e[0]), scarcity(e[0]), core_rank.get(e[0], 1.5), -info(e[0]).credits, e[0])):
            if c in chosen:
                continue
            cr = info(c).credits
            if credits + cr > max_credits and chosen:
                continue
            chosen.append(c); credits += cr
            if unc:
                uncertain_used.add(c)
        if chosen:
            terms.append(PlannedTerm(term_label(y, t), y, t, chosen, credits, sorted(pin_here)))
            done |= set(chosen); pending -= set(chosen); idle = 0; last_used = elapsed
        else:
            idle += 1
            if idle >= 4:
                break
        y, t = next_term(y, t)

    blocked: list[tuple[str, str]] = []
    for c in sorted(pending):
        course = info(c)
        if course.when_offered == "Not Offered":
            blocked.append((c, "Marked 'Not Offered' in the catalog"))
            continue
        miss = missing_prereqs(catalog, c, done)
        if miss:
            blocked.append((c, "Prerequisite not satisfiable"))
        else:
            blocked.append((c, "No scheduled term offers it in the projection window"))

    grad = None
    if not pending:
        grad = terms[-1].label if terms else term_label(cur_year, cur_term)
    return Projection(term_label(start_year, start_term), terms, grad, blocked, warnings, assumptions, sorted(extra), last_used, {c: info(c) for c in needed})


# --------------------------------------------------------------------------- What-If
@dataclass
class WhatIf:
    add_program_ids: list[int] = field(default_factory=list)
    remove_program_ids: list[int] = field(default_factory=list)
    add_completed: list[str] = field(default_factory=list)
    drop_courses: list[str] = field(default_factory=list)


def apply_what_if(student: StudentRecord, w: WhatIf) -> StudentRecord:
    progs = [p for p in student.program_ids if p not in set(w.remove_program_ids)]
    for p in w.add_program_ids:
        if p not in progs:
            progs.append(p)
    courses = [c for c in student.courses if c.code not in set(w.drop_courses)]
    have = {c.code for c in courses}
    for code in w.add_completed:
        if code not in have:
            courses.append(TakenCourse(code, "Fall", 0, "Completed"))
    return replace(student, program_ids=progs, courses=courses)


def compare(student: StudentRecord, catalog: Catalog, w: WhatIf, **kw):
    base = project_graduation(student, catalog, **kw)
    alt_student = apply_what_if(student, w)
    return base, project_graduation(alt_student, catalog, **kw), audit_student(alt_student, catalog)