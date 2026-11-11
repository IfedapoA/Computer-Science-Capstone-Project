"""Pure helpers (no database, no Qt) shared by the Semester Plan tab, the Transfer Credit tab and the printed report.

    build_term_columns()   the student's courses grouped by semester (Fall 2025, Spring 2026 ...) + projected semesters
    transfer_lines()       for every transfer course: how it counts and which requirement(s) it meets
    suggest_equivalents()  likely MSMU equivalents of a transfer course, from its title and credits
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from audit import CORE_PREFIX, FAIL_GRADES, term_index

# --------------------------------------------------------------------------- semester columns
KIND_ORDER = {"transfer": 0, "past": 1, "current": 2, "planned": 3, "projected": 4}


@dataclass
class CourseCard:
    code: str
    title: str
    credits: float
    status: str                  # Completed | In Progress | Planned | Projected
    grade: str = ""
    transfer: bool = False
    note: str = ""

    @property
    def earned(self) -> float:
        """Credits that count as earned: completed with a passing grade."""
        return self.credits if self.status == "Completed" and (self.grade or "").upper() not in FAIL_GRADES else 0.0


@dataclass
class TermColumn:
    label: str
    year: int
    term: str
    kind: str                    # transfer | past | current | planned | projected
    cards: list[CourseCard] = field(default_factory=list)

    @property
    def credits(self) -> float:
        return sum(c.credits for c in self.cards)


def build_term_columns(rows: list[dict], catalog, projection=None, transfer_map: Optional[dict] = None,
                       include_projected: bool = True) -> list[TermColumn]:
    """rows = db.student_course_rows(); projection = audit.Projection (optional)."""
    transfer_map = transfer_map or {}
    cols: dict[tuple, TermColumn] = {}
    for r in rows:
        tr = bool(r["is_transfer"])
        key = (r["year"], r["term"], tr)
        col = cols.setdefault(key, TermColumn(f"{r['term']} {r['year']}" + ("  -  transfer credit" if tr else ""),
                                              r["year"], r["term"], "transfer" if tr else "past"))
        title = (r.get("source_title") if tr else None) or r["name"]
        credits = float(r["source_credits"]) if r.get("source_credits") is not None else float(r["credits"])   # what the transcript printed
        note = ""
        if tr:
            if r["course_code"] in transfer_map:
                tgt = transfer_map[r["course_code"]]
                note = f"counts as {tgt}" if tgt else "elective credit only"
            else:
                note = "not yet evaluated"
        col.cards.append(CourseCard(r["course_code"], title, credits, r["status"], r["grade"] or "", tr, note))
    for col in cols.values():
        if col.kind != "transfer":
            sts = {c.status for c in col.cards}
            col.kind = "current" if "In Progress" in sts else ("planned" if sts == {"Planned"} else "past")
    if include_projected and projection is not None:
        for t in projection.terms:
            key = (t.year, t.term, False)
            col = cols.setdefault(key, TermColumn(t.label, t.year, t.term, "projected"))
            have = {c.code for c in col.cards}
            for code in t.courses:
                if code in have:
                    continue
                info = projection.course_info.get(code)
                if code.startswith(CORE_PREFIX):
                    col.cards.append(CourseCard("CORE", code[len(CORE_PREFIX):], float(info.credits if info else 3), "Projected"))
                else:
                    c = catalog.courses.get(code)
                    col.cards.append(CourseCard(code, (c.name if c else code), float(c.credits if c else 3), "Projected"))
    return sorted(cols.values(), key=lambda c: (term_index(c.year, c.term), c.kind != "transfer", KIND_ORDER[c.kind]))


def credit_summary(columns: list[TermColumn]) -> dict[str, float]:
    out = {"earned": 0.0, "transfer": 0.0, "in_progress": 0.0, "planned": 0.0, "projected": 0.0}
    for col in columns:
        for c in col.cards:
            if c.status == "Completed":
                out["earned"] += c.earned
                if c.transfer:
                    out["transfer"] += c.earned
            elif c.status == "In Progress":
                out["in_progress"] += c.credits
            elif c.status == "Planned":
                out["planned"] += c.credits
            else:
                out["projected"] += c.credits
    return out


# --------------------------------------------------------------------------- title matching
_ABBR = {"intro": "introduction", "prin": "principles", "princ": "principles", "comp": "computer", "sci": "science",
         "lit": "literature", "hist": "history", "mgmt": "management", "comm": "communication", "dev": "development",
         "fund": "fundamentals", "pro": "professional", "bus": "business", "econ": "economics", "psych": "psychology",
         "soc": "sociology", "math": "mathematics", "stat": "statistics", "calc": "calculus", "chem": "chemistry",
         "bio": "biology", "phys": "physics", "eng": "english", "govt": "government", "gen": "general", "rsrch": "research",
         "org": "organization", "struct": "structures", "prog": "programming"}
_STOP = {"to", "of", "the", "and", "at", "in", "for", "a", "an", "with", "on"}
_GENERIC = {"introduction", "principles", "fundamentals", "general", "elementary", "basic", "topics", "survey", "advanced"}   # carry little meaning
_ROMAN = {"i", "ii", "iii", "iv", "v"}


def _tokens(title: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (title or "").lower().replace("&", " and "))
    return [_ABBR.get(w, w) for w in words if w not in _STOP]


def title_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    ca = {t for t in ta if t not in _GENERIC} or set(ta)          # "Introduction to X" should match on X, not on "introduction"
    cb = {t for t in tb if t not in _GENERIC} or set(tb)
    jac = len(ca & cb) / len(ca | cb)
    seq = SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    score = 0.55 * jac + 0.45 * seq
    ra, rb = set(ta) & _ROMAN, set(tb) & _ROMAN
    if ra and rb and ra != rb:                       # "Calculus I" is not "Calculus II"
        score *= 0.5
    return score


def _level(code: str) -> Optional[int]:
    m = re.search(r"(\d)\d\d", code or "")
    return int(m.group(1)) if m else None


def suggest_equivalents(title: str, credits: float, candidates: list[dict], k: int = 3, min_score: float = 0.45,
                        transfer_code: str = ""):
    """-> [(msmu_code, msmu_title, score 0..1)], best first. A suggestion only: the advisor decides.
    Score = title similarity (+ small bonus for similar credits, - penalty when the course level is far apart)."""
    out, lv = [], _level(transfer_code)
    for c in candidates:
        s = title_similarity(title, c["name"])
        if abs(float(c["credits"]) - float(credits or 0)) <= 1:
            s += 0.05
        cl = _level(c["code"])
        if lv is not None and cl is not None:
            s -= 0.05 * max(0, abs(cl - lv) - 1)
        out.append((c["code"], c["name"], max(0.0, min(1.0, s))))
    return [x for x in sorted(out, key=lambda x: -x[2]) if x[2] >= min_score][:k]


# --------------------------------------------------------------------------- transfer evaluation
@dataclass
class TransferLine:
    row_id: int
    code: str
    title: str
    credits: float
    grade: str
    term: str
    year: int
    state: str                   # mapped | elective | unreviewed
    equivalent: str = ""         # the MSMU course it counts as
    equivalent_title: str = ""
    notes: str = ""
    meets: list[str] = field(default_factory=list)
    suggestions: list[tuple] = field(default_factory=list)
    warning: str = ""

    @property
    def counts_somewhere(self) -> bool:
        return bool(self.meets) and self.meets[0] not in (GENERAL_ELECTIVE, NOT_EVALUATED)


GENERAL_ELECTIVE = "General elective credit only"
NOT_EVALUATED = "Not evaluated yet"


def _meets(code: str, catalog, student, audit) -> list[str]:
    out: list[str] = []
    for pa in audit.programs:
        counted = False
        for it in pa.items:
            if it.code == code and it.status != "Remaining":
                counted = True
                out.append(f"{pa.program.code} {pa.program.type.lower()}: " + ("required course" if it.kind == "Core" else "elective"))
        reqs = catalog.requirements.get(pa.program.id)
        if not counted and reqs is not None and code in reqs.electives:
            out.append(f"{pa.program.code}: elective option (extra - not needed)")
    if audit.core:
        for ci in audit.core.items:
            if ci.satisfied_by == code and ci.status != "Remaining":
                out.append(f"CORE: {ci.req.name}")
    return out or [GENERAL_ELECTIVE]


def transfer_lines(rows: list[dict], student, catalog, audit, equivalencies: dict[str, dict], candidates: list[dict]) -> list[TransferLine]:
    """equivalencies = {transfer_code: {'msmu_code': str|None, 'notes': str}}"""
    lines: list[TransferLine] = []
    for r in rows:
        if not r["is_transfer"]:
            continue
        code = r["course_code"]
        title = r.get("source_title") or r["name"]
        credits = float(r["source_credits"]) if r.get("source_credits") is not None else float(r["credits"])
        eq = equivalencies.get(code)
        if eq is None:
            state, counted, target = "unreviewed", code, ""
        elif eq["msmu_code"]:
            state, counted, target = "mapped", eq["msmu_code"], eq["msmu_code"]
        else:
            state, counted, target = "elective", None, ""
        line = TransferLine(r["id"], code, title, credits, r["grade"] or "", r["term"], r["year"], state, target,
                            catalog.courses[target].name if target and target in catalog.courses else "", (eq or {}).get("notes") or "")
        line.meets = _meets(counted, catalog, student, audit) if counted else [GENERAL_ELECTIVE]
        if state == "unreviewed" and line.meets == [GENERAL_ELECTIVE]:
            line.meets = [NOT_EVALUATED]
        if state != "mapped":
            line.suggestions = suggest_equivalents(title, credits, candidates, transfer_code=code)
        mc = catalog.courses.get(code)
        if state == "unreviewed" and mc and r.get("source_title") and title_similarity(r["source_title"], mc.name) < 0.4:
            line.warning = f"Same code as the MSMU course '{mc.name}', but the transcript title differs - probably not the same course."
        lines.append(line)
    return lines


def transfer_totals(lines: list[TransferLine]) -> dict[str, float]:
    out = {"total": 0.0, "mapped": 0.0, "elective": 0.0, "unreviewed": 0.0, "meets_requirements": 0.0}
    for ln in lines:
        out["total"] += ln.credits
        out[ln.state] += ln.credits
        if ln.counts_somewhere:
            out["meets_requirements"] += ln.credits
    return out
