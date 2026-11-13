"""J1 Advising Worksheet / transcript PDF  ->  course rows  ->  CSV   (100% local, free software).

Design (from the professor's conversation): extraction is deterministic and knows NOTHING about degree
requirements - it only reports what the PDF says (term, course, title, credits, grade). The advisor reviews
the rows on screen, then saves a CSV and/or imports it; the degree audit happens later, in the app.

Pipeline:  pdfplumber (text lines + tables)  ->  parse_lines()  ->  review table  ->  CSV (importer format)
Lines that are not clearly course history (no credits and no grade) are flagged and left UNCHECKED, so a list of
"courses you still need" on the worksheet is not mistaken for completed work."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from audit import current_term, term_index

PASSING = {"A", "B", "C", "D", "P", "S", "CR", "TR", "AU"}
GRADE_STRONG = re.compile(r"^(?:[A-D][+-]?|F|P|NP|W|WF|IP|CR|NC|NG|AU|TR|TRN)$")
GRADE_AMBIG = {"I", "S", "U", "T"}              # also appear as title words ("Computer Science I"): need a number before them
NUM = re.compile(r"^\d{1,2}(?:\.\d{1,2})?$")
CODE_LINE = re.compile(r"^\s*([A-Z]{2,6})\s?-?\s?(\d{3}[A-Z]?)\b\s*(.*)$")
CODE_ANY = re.compile(r"\b[A-Z]{2,6}\s?-?\d{3}[A-Z]?\b")
_TERMNAME = r"(Fall|Spring|Summer|Winter|Autumn|FA|SP|SU|WI)"
TERM_PATTERNS = [
    re.compile(rf"\b((?:19|20)\d{{2}})\s*[-/]\s*((?:19|20)?\d{{2}})\s*[-\u2013]?\s*{_TERMNAME}\b", re.I),            # 2025-2026 Fall
    re.compile(rf"\b{_TERMNAME}\s*(?:Semester|Term|Session)?\s*,?\s*((?:19|20)\d{{2}})\b", re.I),        # Fall 2025
    re.compile(rf"\b((?:19|20)\d{{2}})\s*[-/ ]?\s*{_TERMNAME}\b", re.I),                                 # 2025 Fall / 2025FA
    re.compile(rf"\b{_TERMNAME}\s*[-/ ]?\s*(\d{{4}}|\d{{2}})\b", re.I),                                  # FA25 / FA 2025
]
_NAME = {"fall": "Fall", "autumn": "Fall", "fa": "Fall", "spring": "Spring", "sp": "Spring",
         "summer": "Summer", "su": "Summer", "winter": "Spring", "wi": "Spring"}


@dataclass
class ParsedRow:
    term: str = ""
    year: int = 0
    code: str = ""
    title: str = ""
    credits: float = 0
    grade: str = ""
    status: str = ""
    transfer: bool = False
    include: bool = True
    flag: str = ""
    source: str = ""


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    raw_text: str = ""
    header_lines: list[str] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    method: str = "text"
    student_name: str = ""

# ----------------------------------------------------------------- term detection
def find_term(line: str):
    """-> (term, year, line_without_the_term_text) or None"""
    for i, rx in enumerate(TERM_PATTERNS):
        m = rx.search(line)
        if not m:
            continue
        g = m.groups()
        if i == 0:
            y1, y2, name = int(g[0]), g[1], g[2].lower()
            term = _NAME[name]
            year = y1 if term == "Fall" else (int(y2) if len(y2) == 4 else y1 + 1)
            if term == "Summer":
                year = int(y2) if len(y2) == 4 else y1 + 1
        elif i == 2:
            year, term = int(g[0]), _NAME[g[1].lower()]
        else:
            name, y = g[0].lower(), g[1]
            term, year = _NAME[name], int(y) if len(y) == 4 else 2000 + int(y)
        return term, year, (line[:m.start()] + " " + line[m.end():]).strip()
    return None


# ----------------------------------------------------------------- one course line
def parse_course_line(text: str):
    """'CMSCI 120 Introduction to Computer Science I 3.00 A' -> dict, or None if it is not a course line."""
    m = CODE_LINE.match(text)
    if not m:
        return None
    code = f"{m.group(1)} {m.group(2)}"
    tokens = m.group(3).split()
    idx, grade, nums = len(tokens), "", []
    for _ in range(5):
        if idx == 0:
            break
        tok = tokens[idx - 1]
        if not grade and GRADE_STRONG.match(tok):
            grade = tok; idx -= 1; continue
        if not grade and tok in GRADE_AMBIG and idx >= 2 and NUM.match(tokens[idx - 2]):
            grade = tok; idx -= 1; continue
        if NUM.match(tok):
            nums.append(float(tok)); idx -= 1; continue
        break
    credits = nums[-1] if nums else 0.0            # leftmost number of the trailing block (credits, not quality points)
    if credits > 12:
        credits = 0.0
    return {"code": code, "title": " ".join(tokens[:idx]).strip(" -:"), "credits": credits, "grade": grade}


def parse_lines(lines: list[str], today: Optional[date] = None) -> ParseResult:
    res = ParseResult()
    cur_year, cur_term = current_term(today)
    now_idx = term_index(cur_year, cur_term)
    term = year = None
    in_transfer = False
    transfer_no_term = False
    seen: dict[tuple, int] = {}
    for n, raw in enumerate(lines):
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if n < 12:
            res.header_lines.append(line)
        t = find_term(line)
        rest = line
        if t:
            term, year, rest = t
            in_transfer = bool(re.search(r"transfer", line, re.I))
            transfer_no_term = False
            if not rest:
                continue                                          # a pure term-header line
        elif re.search(r"\btransfer\b", line, re.I) and not CODE_ANY.search(line):
            in_transfer = True
            transfer_no_term = True                              # "Transfer Credit" section: no term of its own
            continue
        info = parse_course_line(rest)
        if not info:
            if CODE_ANY.search(line) and (t is None or rest):
                res.unparsed.append(line)                         # contains a course code but not in a recognisable layout
            continue
        row = ParsedRow(term=term or "", year=year or 0, code=info["code"], title=info["title"],
                        credits=info["credits"], grade=info["grade"], source=line)
        g = row.grade
        row.transfer = in_transfer or g in ("TR", "TRN")
        if g in ("TRN",):
            row.grade = "TR"
        flags = []
        if transfer_no_term and row.transfer:
            flags.append("Transfer credit: term copied from the section above - check it")
        if g == "IP":
            row.status, row.grade = "In Progress", ""
        elif g in ("W", "WF"):
            row.status = "Completed"; flags.append("Withdrawn - does not count toward requirements")
        elif g:
            row.status = "Completed"
        elif row.year:
            idx = term_index(row.year, row.term)
            if idx == now_idx:
                row.status = "In Progress"
            elif idx > now_idx:
                row.status = "Planned"
            else:
                row.status = "Completed"; flags.append("Past term but no grade found - enter the grade or untick")
                row.include = False
        else:
            row.status = "Completed"
        if not row.year:
            flags.append("No term found above this line"); row.include = False
        if not info["grade"] and not info["credits"]:
            flags.append("No credits or grade: probably a requirement list, not history"); row.include = False
        elif not info["credits"]:
            flags.append("Credits not found (3 assumed)"); row.credits = 3
        key = (row.code, row.term, row.year)
        if key in seen:
            flags.append("Duplicate of an earlier row"); row.include = False
        else:
            seen[key] = len(res.rows)
        row.flag = "; ".join(flags)
        res.rows.append(row)
    return res


# ----------------------------------------------------------------- PDF extraction

_RIGHT_START = re.compile(r"^(?:[A-Z]{2,6}\s?-?\s?\d{3}[A-Z]?\b|(?:Fall|Spring|Summer|Winter|Autumn)\b|(?:19|20)\d{2}\b)", re.I)


def find_gutter(page) -> Optional[float]:
    """x position of the gutter if the page is TWO COLUMNS (e.g. J1's two-column landscape layout), else None.
    A gutter is an empty vertical band near the middle AND the right column's lines START like course history
    (a course code or a term name).  An ordinary table (Course | Title | Credits | Grade) fails that test."""
    words = page.extract_words()
    if len(words) < 12:
        return None
    width = float(page.width)
    mid = width / 2
    best = None
    for x in range(int(width * 0.35), int(width * 0.65)):
        if all(not (w["x0"] < x + 3 and w["x1"] > x - 3) for w in words):
            if best is None or abs(x - mid) < abs(best - mid):
                best = x
    if best is None:
        return None
    lines: dict[int, list] = {}
    for w in words:
        lines.setdefault(round(w["top"] / 3), []).append(w)
    both = starts = 0
    for ws in lines.values():
        left = [w for w in ws if w["x1"] <= best]
        right = sorted((w for w in ws if w["x0"] >= best), key=lambda w: w["x0"])
        if left and right:
            both += 1
            if _RIGHT_START.match(" ".join(w["text"] for w in right[:2])):
                starts += 1
    return float(best) if starts >= 3 and starts >= 0.6 * both else None


def pdf_support_problem() -> Optional[str]:
    """None if PDF reading works. Otherwise a plain-English explanation that names the EXACT Python running this
    program and the exact command for it (a plain 'pip install' often installs into a different Python)."""
    import sys
    py = sys.executable
    try:
        import pdfplumber  # noqa: F401
        return None
    except ModuleNotFoundError as e:
        if e.name == "pdfplumber":
            return ("The 'pdfplumber' package is not installed for the Python that is running this program:\n"
                    f"    {py}\n\nInstall it into THAT Python with:\n"
                    f'    "{py}" -m pip install pdfplumber\n\n'
                    "(If you use a virtual environment, activate it first. A plain 'pip install' may have gone to a different Python.)")
        return (f"pdfplumber is installed, but one of the parts it needs is missing: '{e.name}'.\n"
                f'Repair it with:\n    "{py}" -m pip install --upgrade pdfplumber\n\nDetails: {e}')
    except ImportError as e:
        return (f"pdfplumber is installed but could not be loaded: {e}\n"
                f'Try:\n    "{py}" -m pip install --upgrade pdfplumber')


def extract(path: str | Path) -> tuple[list[str], list[str], str]:
    """-> (text_lines, table_lines, raw_text).  Needs: pdfplumber (see pdf_support_problem)"""
    problem = pdf_support_problem()
    if problem:
        raise RuntimeError(problem)
    import pdfplumber
    text_lines, table_lines, raw = [], [], []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            gutter = find_gutter(page)
            if gutter:                                   # two columns: read the whole LEFT column, then the RIGHT one
                left = page.crop((0, 0, gutter, page.height)).extract_text() or ""
                right = page.crop((gutter, 0, page.width, page.height)).extract_text() or ""
                txt = left + "\n" + right
                raw.append(f"----- page {i} (two columns: left column, then right column) -----\n{txt}")
            else:
                txt = page.extract_text() or ""
                raw.append(f"----- page {i} -----\n{txt}")
            text_lines += txt.splitlines()
            try:
                for table in page.extract_tables():
                    for row in table:
                        cells = [re.sub(r"\s+", " ", c or "").strip() for c in row]
                        table_lines.append(" ".join(c for c in cells if c))
            except Exception:
                pass
    return text_lines, table_lines, "\n".join(raw)

# ----------------------------------------------------------------- COLUMN LAYOUT  (MyMount / J1 "Unofficial Transcript")
# In this layout every course is a BLOCK of several text lines: the subject code on the line above, the number below,
# a wrapped title, and the grade + credits on the middle line. Reading it line by line scrambles the pieces, so the
# words are placed by their x / y position instead.  The reader also checks itself against the "Term Totals" lines.
_DEC = re.compile(r"^\d+\.\d{2}$")
_HEADER_WORDS = {"Attempted", "Earned", "GPA", "Quality", "Credits", "Points", "Course", "Title", "Grade", "Repeat", "Type"}
_CODE_CELL = re.compile(r"^([A-Z]{2,6})(\d{3})([A-Z]?)$")          # CMSCI475A  /  ARTT116 (a cell wrapped as 'ARTT1' + '16')
_NAME_RX = re.compile(r"Transcript for:\s*(.+)", re.I)
MAX_BLOCK_DISTANCE = 26                                            # a word further than this (in points) from a course row is ignored


def _cluster_rows(words, tol: float = 2.5) -> list[list[dict]]:
    rows: list[list] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0] - w["top"]) <= tol:
            rows[-1][1].append(w)
        else:
            rows.append([w["top"], [w]])
    return [sorted(r[1], key=lambda w: w["x0"]) for r in rows]


def _term_of_row(r):
    if max(w["x0"] for w in r) > 300 or any(_DEC.match(w["text"]) for w in r):
        return None
    text = " ".join(w["text"] for w in r)
    t = find_term(text)
    return (t[0], t[1], bool(re.search(r"transfer", text, re.I))) if t else None


def parse_columns(path: str | Path, today: Optional[date] = None) -> Optional[ParseResult]:
    """Course rows from a column-layout transcript, or None if the PDF does not look like one.
    NOTE: every term is its own table with its OWN column widths, so the column positions are read from each term's
    own 'Course Title Grade Repeat' header row (using one set for the whole PDF mixes up titles, grades and credits)."""
    import pdfplumber
    cur_year, cur_term = current_term(today)
    now_idx = term_index(cur_year, cur_term)
    allrows = []
    with pdfplumber.open(str(path)) as pdf:
        for pn, page in enumerate(pdf.pages):
            allrows += [(pn * 10000 + r[0]["top"], r) for r in _cluster_rows(page.extract_words())]

    res = ParseResult(method="columns")
    sections: list[dict] = []
    sec_cols: dict[int, tuple[float, float, float, float]] = {}      # section -> (title_x, grade_x, repeat_x, numbers_x)
    anchors: list[dict] = []
    content: list[tuple[float, int, dict]] = []
    totals: dict[int, float] = {}
    recent: list[tuple[float, list]] = []
    last_cols = None
    for top, r in allrows:
        text = " ".join(w["text"] for w in r)
        if len(res.header_lines) < 8:
            res.header_lines.append(text)
        m = _NAME_RX.search(text)
        if m and not res.student_name:
            res.student_name = m.group(1).strip()
        pos = {w["text"]: w["x0"] for w in r}
        if sections and all(k in pos for k in ("Course", "Title", "Grade", "Repeat")):
            att = [w["x0"] for t2, rr in recent for w in rr if w["text"] == "Attempted" and 0 < top - t2 < 25]
            last_cols = sec_cols[len(sections) - 1] = (pos["Title"] - 8, pos["Grade"] - 8, pos["Repeat"] - 8,
                                                        (min(att) if att else pos["Repeat"] + 49) - 8)
        recent = (recent + [(top, r)])[-6:]
        if all(w["text"] in _HEADER_WORDS for w in r) or text.startswith("Printable"):
            continue
        if any("Totals" in w["text"] for w in r):
            nums = [float(w["text"]) for w in r if _DEC.match(w["text"])]
            if sections and text.startswith("Term") and nums:
                totals[len(sections) - 1] = nums[0]               # attempted credits the transcript says this term has
            continue
        t = _term_of_row(r)
        if t:
            sections.append({"term": t[0], "year": t[1], "transfer": t[2]})
            continue
        if not sections:
            continue                                               # the summary table above the first term
        sec = len(sections) - 1
        nums_x = sec_cols.get(sec, last_cols or (0, 0, 0, 10 ** 6))[3]
        if sum(1 for w in r if w["x0"] >= nums_x and _DEC.match(w["text"])) >= 3:
            anchors.append({"top": top, "sec": sec, "row": r, "words": []})
        content += [(top, sec, w) for w in r]
    if not sec_cols:
        return None                                                # no 'Course Title Grade Repeat' header: not this layout

    for top, sec, w in content:                                    # every word joins the nearest course row of its term
        near = [a for a in anchors if a["sec"] == sec]
        if near:
            best = min(near, key=lambda a: abs(a["top"] - top))
            if abs(best["top"] - top) <= MAX_BLOCK_DISTANCE:
                best["words"].append((top, w))

    seen: set[tuple] = set()
    for a in anchors:
        sec = sections[a["sec"]]
        title_x, grade_x, repeat_x, nums_x = sec_cols.get(a["sec"]) or last_cols
        words = sorted(a["words"], key=lambda tw: (round(tw[0] / 3), tw[1]["x0"]))
        cell = "".join(w["text"] for _, w in words if w["x0"] < title_x).upper()
        title = " ".join(w["text"] for _, w in words if title_x <= w["x0"] < grade_x)
        grade = "".join(w["text"] for _, w in words if grade_x <= w["x0"] < repeat_x).strip()
        repeat = "".join(w["text"] for _, w in words if repeat_x <= w["x0"] < nums_x).strip()
        nums = [float(w["text"]) for w in a["row"] if w["x0"] >= nums_x and _DEC.match(w["text"])]
        cm = _CODE_CELL.match(cell)
        row = ParsedRow(term=sec["term"], year=sec["year"], code=f"{cm.group(1)} {cm.group(2)}" if cm else "",
                        title=title, credits=nums[0] if nums else 0.0, grade=grade, transfer=sec["transfer"] or grade in ("TR", "TRN"),
                        source=f"{cell} | {title} | {grade} | {nums}")
        flags = []
        g = grade.upper()
        if not cm:
            flags.append(f"Course code not recognised ('{cell}') - type it in"); row.include = False
        if g in ("WIP", "IP"):
            row.status, row.grade = "In Progress", ""
        elif g:
            row.status = "Completed"
            if g in ("W", "WF"):
                flags.append("Withdrawn - does not count toward requirements")
            elif g in ("F", "NP", "U"):
                flags.append("Failing grade - does not count toward requirements")
        else:
            row.status = "In Progress" if term_index(row.year, row.term) >= now_idx else "Completed"
            if row.status == "Completed":
                flags.append("Past term but no grade found - enter the grade or untick"); row.include = False
        if repeat and repeat != "-":
            flags.append(f"Repeat column says '{repeat}'")
        if row.code:
            key = (row.code, row.term, row.year)
            if key in seen:
                flags.append("Duplicate of an earlier row"); row.include = False
            seen.add(key)
        row.flag = "; ".join(flags)
        res.rows.append(row)

    # self-check against the transcript's own "Term Totals" (skipped for terms that are only in progress)
    for i, sec in enumerate(sections):
        mine = [r for r, a in zip(res.rows, anchors) if a["sec"] == i]
        if i in totals and mine and any(r.status == "Completed" for r in mine):
            got = sum(r.credits for r in mine)
            if abs(got - totals[i]) > 0.01:
                res.warnings.append(f"{sec['term']} {sec['year']}{' (transfer)' if sec['transfer'] else ''}: the rows add up to "
                                    f"{got:g} credits but the transcript's Term Totals say {totals[i]:g} - a course may be missing. "
                                    "Check 'Show raw text'.")
    return res if res.rows else None

def parse_pdf(path: str | Path, today: Optional[date] = None) -> ParseResult:
    text_lines, table_lines, raw = extract(path)
    if not raw.replace("-----", "").strip() or not any(text_lines):
        r = ParseResult(raw_text=raw)
        r.warnings.append("No text could be read. This looks like a scanned image. Ask J1 for the text version of the PDF "
                          "(print to PDF instead of scanning), or OCR it first.")
        return r
    columns = parse_columns(path, today)                  # transcripts laid out in columns (MyMount / J1 unofficial transcript)
    if columns:
        columns.raw_text = raw
        return columns
    a = parse_lines(text_lines, today)
    b = parse_lines(table_lines, today) if table_lines else ParseResult()
    use_b = sum(r.include for r in b.rows) > sum(r.include for r in a.rows)
    res = b if use_b else a
    res.method = "table" if use_b else "text"
    res.raw_text = raw
    if not res.header_lines:
        res.header_lines = text_lines[:12]
    if not res.rows:
        res.warnings.append("No course lines were recognised. Open 'Show raw text' to see what the PDF contains, "
                            "then adjust the patterns in pdf_import.py (or send a redacted sample).")
    return res


# ----------------------------------------------------------------- CSV output (the importer's format)
CSV_COLUMNS = ["student_email", "course_code", "term", "year", "status", "grade", "transfer", "title", "credits"]


def to_csv_rows(rows: list[ParsedRow], student_email: str) -> list[list]:
    out = []
    for r in rows:
        if not r.include:
            continue
        out.append([student_email, r.code, r.term, r.year, r.status, r.grade if r.status == "Completed" else "",
                    "yes" if r.transfer else "", r.title, f"{r.credits:g}"])
    return out


def write_csv(rows: list[ParsedRow], student_email: str, path: str | Path) -> int:
    data = to_csv_rows(rows, student_email)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        w.writerows(data)
    return len(data)
