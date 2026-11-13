"""Advising report: a PDF the student takes home (the student has no access to this application).

    build_report_html()   pure: turns the student's data into one HTML page (tables, progress bars, KPI tiles)
    report_images()       the credits-by-semester chart, drawn with Qt (no extra libraries)
    save_pdf()            HTML + images -> PDF with Qt's own PDF writer
    ReportDialog          choose what to include, pick the registration semester, add notes, save the PDF
"""
from __future__ import annotations

import html
import os
import re
from datetime import date

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt, QUrl
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextDocument)
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QLabel, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QVBoxLayout)

import db
from audit import CORE_PREFIX
from common import guard, info, show_error
from plan import GENERAL_ELECTIVE, NOT_EVALUATED, build_term_columns, credit_summary, transfer_totals

# ------------------------------------------------------------------ theme
NAVY, TEAL, LIGHT, GRID = "#1f3a5f", "#2b7a78", "#eef3f9", "#c3ccd8"
GREEN, AMBER, BLUE, LILAC, GREY, RED = "#d9f2e0", "#fff0c9", "#dbe8ff", "#ece3f7", "#f1f1f1", "#f6d3d3"
BAR_GREEN, BAR_AMBER, BAR_TRACK = "#4c9f70", "#e9b949", "#e3e7ec"
STATUS_BG = {"Completed": GREEN, "In Progress": AMBER, "Planned": BLUE, "Projected": GREY, "Remaining": "#ffffff"}
DAY = {"M": "Mon", "T": "Tue", "W": "Wed", "R": "Thu", "F": "Fri", "S": "Sat", "U": "Sun"}
KIND = {"transfer": "Transfer credit", "past": "Completed", "current": "In progress", "planned": "Planned", "projected": "Suggested"}
E = html.escape


# ------------------------------------------------------------------ small html helpers
def _t(t) -> str:
    if t is None:
        return ""
    s = int(t.total_seconds()) if hasattr(t, "total_seconds") else int(t)
    h, m = s // 3600, (s % 3600) // 60
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def _range(a, b) -> str:
    """10:00 - 10:50 AM  (or 11:30 AM - 12:45 PM when the halves of the day differ)."""
    if a is None:
        return ""
    sa, sb = _t(a), _t(b) if b is not None else ""
    if sb and sa[-2:] == sb[-2:]:
        sa = sa[:-3]
    return f"{sa} - {sb}" if sb else sa


def _th(text: str, width: str = "", align: str = "left") -> str:
    return f"<th align='{align}' bgcolor='{NAVY}'{' width=' + repr(width) if width else ''}><font color='#ffffff'>{E(text)}</font></th>"


def _table(headers, rows, widths=None, pad=4) -> str:
    """rows: list of (cells, bgcolor|None) or plain cell lists."""
    head = "".join(_th(h, widths[i] if widths else "") for i, h in enumerate(headers))
    body = []
    for r in rows:
        cells, bg = (r if isinstance(r, tuple) else (r, None))
        body.append(f"<tr{' bgcolor=' + repr(bg) if bg else ''}>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    return (f"<table border='1' cellspacing='0' cellpadding='{pad}' width='100%' style='border-color:{GRID}'>"
            f"<tr>{head}</tr>{''.join(body)}</table>")


def _h2(text: str, page_break: bool = False) -> str:
    return (f"<h2 style='color:{NAVY}; margin-top:14px;{' page-break-before:always;' if page_break else ''}'>{E(text)}</h2>")


def _bar(done: float, in_prog: float = 0.0) -> str:
    """A progress bar made of table cells: green = done, amber = in progress, grey = still to do."""
    d, p = max(0, min(100, round(done))), max(0, min(100 - round(done), round(in_prog)))
    cells = []
    for pct, color in ((d, BAR_GREEN), (p, BAR_AMBER), (100 - d - p, BAR_TRACK)):
        if pct > 0:
            cells.append(f"<td width='{pct}%' bgcolor='{color}'><font size='1'>&nbsp;</font></td>")
    return "<table width='100%' cellspacing='0' cellpadding='0' border='0'><tr>" + "".join(cells) + "</tr></table>"


def _tiles(items) -> str:
    """Big-number tiles: items = [(value, label)]."""
    cells = "".join(f"<td align='center' bgcolor='{LIGHT}' width='{100 // len(items)}%'><font size='5' color='{NAVY}'><b>{v}</b></font><br>"
                    f"<font size='2' color='#556677'>{E(lbl)}</font></td>" for v, lbl in items)
    return f"<table width='100%' cellspacing='6' cellpadding='8' border='0'><tr>{cells}</tr></table>"


def _status_cell(status: str) -> str:
    return {"Completed": "<b>Done</b>", "In Progress": "<b>In progress</b>", "Planned": "<b>Planned</b>",
            "Remaining": "<font color='#b3261e'><b>Needed</b></font>"}.get(status, E(status))


def _needed_for(code: str, audit) -> str:
    out = []
    for pa in audit.programs:
        for it in pa.items:
            if it.code == code and it.status == "Remaining":
                out.append(f"{pa.program.code} " + ("required" if it.kind == "Core" else "elective"))
        if code in pa.elective_options and pa.electives_remaining:
            out.append(f"{pa.program.code} elective option")
    return "; ".join(dict.fromkeys(out))


# ------------------------------------------------------------------ the chart (drawn with Qt, embedded in the PDF)
def report_images(columns, width: int = 1100, height: int = 380) -> dict[str, QImage]:
    """{'chart_credits': QImage}: credits per semester, stacked by what they are."""
    cols = [c for c in columns if c.cards]
    if not cols:
        return {}
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    left, right, top, bottom = 56, 16, 46, 74
    pw, ph = width - left - right, height - top - bottom
    stack = [("Transfer", "#b79ad9"), ("Completed", "#4c9f70"), ("No credit (F/W)", "#d9534f"), ("In progress", "#e9b949"),
             ("Planned", "#6f9be0"), ("Suggested", "#b9bec7")]
    totals = []
    for c in cols:
        seg = {k: 0.0 for k, _ in stack}
        for k in c.cards:
            if k.status == "Completed":
                seg["Transfer" if k.transfer else ("Completed" if k.earned else "No credit (F/W)")] += k.credits
            elif k.status == "In Progress":
                seg["In progress"] += k.credits
            elif k.status == "Planned":
                seg["Planned"] += k.credits
            else:
                seg["Suggested"] += k.credits
        totals.append(seg)
    top_val = max(10.0, max(sum(s.values()) for s in totals))
    top_val = float(int((top_val + 4) // 5 * 5))
    f = QFont("Helvetica"); f.setPixelSize(15)
    p.setFont(f)
    p.setPen(QColor("#556677"))
    for i in range(0, int(top_val) + 1, 5):                                   # horizontal grid + y labels
        y = top + ph - ph * i / top_val
        p.setPen(QColor("#dde3ea")); p.drawLine(left, int(y), width - right, int(y))
        p.setPen(QColor("#556677")); p.drawText(QRectF(0, y - 10, left - 8, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(i))
    slot = pw / len(cols)
    bw = min(70.0, slot * 0.62)
    for i, (c, seg) in enumerate(zip(cols, totals)):
        x = left + slot * i + (slot - bw) / 2
        y = top + ph
        for name, color in stack:
            h = ph * seg[name] / top_val
            if h > 0:
                p.fillRect(QRectF(x, y - h, bw, h), QColor(color)); y -= h
        tot = sum(seg.values())
        p.setPen(QColor(NAVY)); p.drawText(QRectF(x - 10, y - 22, bw + 20, 20), Qt.AlignmentFlag.AlignCenter, f"{tot:g}")
        words = c.label.replace("  -  transfer credit", "").split()                # "Fall 2025"
        label = f"{words[0]}\n{' '.join(words[1:])}" + ("\n(transfer)" if c.kind == "transfer" else "")
        p.setPen(QColor("#334455")); p.drawText(QRectF(x - 14, top + ph + 6, bw + 28, 60), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)
    lx = left                                                                   # legend
    for name, color in stack:
        if any(s[name] for s in totals):
            p.fillRect(QRectF(lx, 14, 16, 16), QColor(color)); p.setPen(QColor("#334455"))
            p.drawText(QRectF(lx + 22, 10, 150, 24), Qt.AlignmentFlag.AlignVCenter, name)
            lx += 40 + len(name) * 8
    p.end()
    return {"chart_credits": img}


# ------------------------------------------------------------------ the report
def build_report_html(*, student_row: dict, advisor_name: str, catalog, audit, projection, rows: list[dict], transfer: list,
                      reg_term: tuple | None, reg_courses: list[str], sections_lookup, notes: str = "",
                      options: dict | None = None, today: date | None = None, transfer_map: dict | None = None) -> str:
    o = {"summary": True, "registration": True, "semesters": True, "requirements": True, "transfer": True, "projected": True, "chart": True}
    o.update(options or {})
    today = today or date.today()
    columns = build_term_columns(rows, catalog, projection, transfer_map or {}, include_projected=o["projected"])
    cs = credit_summary(columns)
    name = f"{student_row['first_name']} {student_row['last_name']}"
    progs = ", ".join(f"{pa.program.name} ({pa.program.type})" for pa in audit.programs) or "none declared"
    h: list[str] = []

    # ---- header band + student card
    h.append(f"<table width='100%' cellspacing='0' cellpadding='10' border='0'><tr><td bgcolor='{NAVY}'>"
             f"<font size='6' color='#ffffff'><b>Academic Advising Summary</b></font><br>"
             f"<font size='2' color='#cfd8e6'>Mount Saint Mary's University &nbsp;|&nbsp; Prepared {today:%B %d, %Y}</font></td></tr></table>")
    h.append("<br>" + _table(["Student", "Advisor", "Catalog year", "Declared programs"],
                             [[f"<b>{E(name)}</b><br><font size='2'>{E(student_row['email_address'])}</font>", E(advisor_name),
                               E(str(student_row['catalog_year'])), E(progs)]], ["26%", "18%", "14%", "42%"]))

    # ---- where you are
    if o["summary"]:
        grad = projection.graduation_label if projection else None
        h.append(_h2("Where you are"))
        h.append(_tiles([(f"{cs['earned']:g}", "credits earned"), (f"{cs['in_progress']:g}", "in progress now"), (f"{cs['planned']:g}", "planned"),
                         (E(grad) if grad else "?", "projected graduation")]))
        rows_p = []
        for pa in audit.programs:
            pct = pa.percent_complete
            ip = 100.0 * pa.units_in_progress / pa.units_total if pa.units_total else 0.0
            rows_p.append(([f"<b>{E(pa.program.name)}</b><br><font size='2'>{pa.program.type}</font>", _bar(pct, ip),
                            f"{pa.units_completed} of {pa.units_total} done" + (f" (+{pa.units_in_progress} in progress)" if pa.units_in_progress else "")], None))
        if audit.core:
            c = audit.core
            rows_p.append((["<b>CORE curriculum</b><br><font size='2'>required of every student</font>",
                            _bar(c.percent_complete, 100.0 * c.units_in_progress / c.units_total if c.units_total else 0),
                            f"{c.units_completed} of {c.units_total} done" + (f" (+{c.units_in_progress} in progress)" if c.units_in_progress else "")], None))
        h.append(_table(["Requirement area", "Progress", "Status"], rows_p, ["30%", "40%", "30%"]))
        h.append("<p><font size='2' color='#556677'>Green = done, amber = in progress, grey = still to do. The projected graduation date is an estimate that "
                 "counts major, minor and CORE requirements only (not free electives or the 120-credit total) and assumes a normal course load.</font></p>")
        if o["chart"] and any(c.cards for c in columns):
            h.append("<p><b>Credits by semester</b></p><p><img src='chart_credits' width='680'></p>")

    # ---- registration plan
    if o["registration"] and reg_term:
        term, year = reg_term
        h.append(_h2(f"Registration plan: {term} {year}", page_break=True))
        if not reg_courses:
            h.append("<p>No courses were selected for this semester.</p>")
        else:
            summ, total = [], 0.0
            for code in reg_courses:
                if code.startswith(CORE_PREFIX):
                    slot = code[len(CORE_PREFIX):]
                    req = next((r for r in catalog.core if r.name == slot), None)
                    summ.append((["[&nbsp;&nbsp;]", "<b>CORE</b>", f"{E(slot)}<br><font size='2'>choose any approved course: "
                                  f"{E(', '.join(req.options) if req and req.options else 'see the CORE list')}</font>", f"{req.credits if req else 3}", "CORE curriculum"], LILAC))
                    total += req.credits if req else 3
                else:
                    c = catalog.courses.get(code)
                    total += c.credits if c else 0
                    summ.append((["[&nbsp;&nbsp;]", f"<b>{E(code)}</b>", E(c.name if c else ""), f"{c.credits if c else '?'}", E(_needed_for(code, audit)) or "&nbsp;"], BLUE))
            summ.append((["", "", "<b>Total credits</b>", f"<b>{total:g}</b>", ""], LIGHT))
            h.append(_table(["Done", "Course", "Title", "Cr", "Counts toward"], summ, ["8%", "14%", "40%", "6%", "32%"]))
            h.append("<p><font size='2' color='#556677'>Tick each box once you have registered.</font></p>")
            h.append("<p><b>Class sections</b></p>")
            for code in [c for c in reg_courses if not c.startswith(CORE_PREFIX)]:
                c = catalog.courses.get(code)
                secs = sections_lookup(code) if sections_lookup else []
                rows_s = []
                for s in secs[:10]:
                    days = " ".join(DAY.get(x, x) for x in (s["days"] or "").split()) or "online / no set days"
                    seats = "" if s["capacity"] is None else str(max(0, s["capacity"] - (s["enrollment"] or 0)))
                    part = "" if s["component"] == "Lecture" else f" ({s['component'].lower()})"
                    rows_s.append(([f"{E(s['section'])}{part}", E(days), '<nobr>' + _range(s['start_time'], s['end_time']) + '</nobr>',
                                    E(' '.join(x for x in (s['location'], s['room']) if x)), E(s['professor'] or 'to be announced'), seats],
                                   "#f7f9fc" if len(rows_s) % 2 else None))
                if len(secs) > 10:
                    rows_s.append((["", f"... and {len(secs) - 10} more meetings. See the registrar's schedule.", "", "", "", ""], None))
                if not rows_s:
                    rows_s = [(["&nbsp;", f"The {term} {year} schedule is not loaded, or this course is not in it. Check the registrar's schedule for times.", "", "", "", ""], None)]
                h.append(f"<p style='margin-bottom:2px'><b>{E(code)}</b> {E(c.name if c else '')}</p>"
                         + _table(["Section", "Days", "Time", "Room", "Instructor", "Seats open"], rows_s, ["10%", "16%", "22%", "20%", "24%", "8%"], pad=3))

    # ---- notes
    h.append(_h2("Notes from your advising session", page_break=not (o["registration"] and reg_term)))
    note_html = E(notes).replace("\n", "<br>") if notes.strip() else "<i>(none recorded)</i>"
    h.append(f"<table width='100%' cellspacing='0' cellpadding='10' border='1' style='border-color:{GRID}'><tr><td bgcolor='#fffdf5'>{note_html}"
             f"<br><br><font size='2' color='#556677'>Questions to ask before you register:</font><br><br><br></td></tr></table>")

    # ---- requirements (tables, needed first)
    if o["requirements"]:
        h.append(_h2("Degree requirements"))
        h.append("<p><font size='2' color='#556677'>Sorted so that what you still need comes first.</font></p>")
        order = {"Remaining": 0, "In Progress": 1, "Planned": 1, "Completed": 2}
        for pa in audit.programs:
            h.append(f"<p style='margin-bottom:2px'><b>{E(pa.program.name)}</b> ({pa.program.type}) &nbsp; {pa.units_completed} of {pa.units_total} done</p>"
                     + _bar(pa.percent_complete, 100.0 * pa.units_in_progress / pa.units_total if pa.units_total else 0))
            rws = []
            for it in sorted(pa.items, key=lambda i: (order[i.status], i.kind != "Core", i.code)):
                if it.code.endswith("elective(s)"):
                    rws.append(([_status_cell("Remaining"), "<b>Electives</b>", f"Choose {pa.electives_remaining} more from: {E(', '.join(pa.elective_options[:14]))}",
                                 "", "", ""], RED))
                    continue
                when = " ".join(x for x in (it.when, ("grade " + it.grade) if it.grade else "") if x)
                via = f"<font size='2'>via {E(it.via)}</font>" if it.via else ""
                rws.append(([_status_cell(it.status), f"<b>{E(it.code)}</b>", E(it.name), str(it.credits or ""), it.kind.replace("Core", "Required"),
                             (E(when) + ("<br>" + via if via else "")) or "&nbsp;"], STATUS_BG[it.status] if it.status != "Remaining" else "#fff7f6"))
            h.append(_table(["Status", "Course", "Title", "Cr", "Type", "When / grade"], rws, ["11%", "13%", "36%", "5%", "11%", "24%"], pad=3) + "<br>")
        if audit.core:
            c = audit.core
            h.append(f"<p style='margin-bottom:2px'><b>CORE curriculum</b> (required of every student) &nbsp; {c.units_completed} of {c.units_total} done</p>"
                     + _bar(c.percent_complete, 100.0 * c.units_in_progress / c.units_total if c.units_total else 0))
            yr = {"Fr": "Freshman", "So": "Sophomore", "Ju": "Junior", "Sr": "Senior"}
            rws = []
            for ci in sorted(c.items, key=lambda i: (order[i.status], i.req.id)):
                by = f"{E(ci.satisfied_by)}" + (f"<br><font size='2'>{E(ci.note)}</font>" if ci.note else "") if ci.satisfied_by else "&nbsp;"
                rws.append(([_status_cell(ci.status), f"<b>{E(ci.req.name)}</b>", yr.get(ci.req.take_as, ci.req.take_as), by,
                             E(" ".join(x for x in (ci.when, ("grade " + ci.grade) if ci.grade else "") if x)) or "&nbsp;"],
                            STATUS_BG[ci.status] if ci.status != "Remaining" else "#fff7f6"))
            h.append(_table(["Status", "Requirement", "Take as", "Satisfied by", "When / grade"], rws, ["11%", "30%", "13%", "26%", "20%"], pad=3))

    # ---- transfer credit
    if o["transfer"] and transfer:
        t = transfer_totals(transfer)
        h.append(_h2("Transfer credit evaluation"))
        h.append(_tiles([(f"{t['total']:g}", "transfer credits"), (f"{t['mapped']:g}", "counted as MSMU courses"),
                         (f"{t['elective']:g}", "elective credit only"), (f"{t['unreviewed']:g}", "awaiting evaluation")]))
        trs = []
        for ln in transfer:
            if ln.state == "mapped":
                counts, bg = f"<b>{E(ln.equivalent)}</b> {E(ln.equivalent_title)}", GREEN
            elif ln.state == "elective":
                counts, bg = "elective credit only", "#ffffff"
            else:
                counts, bg = "<i>awaiting evaluation</i>", AMBER
            how = ("<i>awaiting evaluation</i>" if ln.state == "unreviewed" and ln.meets == [NOT_EVALUATED] else
                   "<br>".join(E(m) for m in ln.meets if m not in (GENERAL_ELECTIVE, NOT_EVALUATED)) or "General elective credit")
            trs.append(([f"<b>{E(ln.code)}</b>", E(ln.title), f"{ln.credits:g}", E(ln.grade), counts, how], bg))
        h.append(_table(["Transfer course", "Title on transcript", "Cr", "Grade", "Counts as", "Meets"], trs, ["13%", "24%", "6%", "7%", "22%", "28%"], pad=3))

    # ---- semester record (reference)
    if o["semesters"]:
        h.append(_h2("Semester by semester (reference)", page_break=True))
        body = []
        for col in columns:
            if col.kind == "transfer" and o["transfer"] and transfer:
                body.append(([f"<b>{E(col.label)}</b> &nbsp; {len(col.cards)} courses, {col.credits:g} credits "
                              "<font size='2'>(see 'Transfer credit evaluation' for how each one counts)</font>", "", "", "", ""], LILAC))
                continue
            body.append(([f"<b>{E(col.label)}</b> &nbsp; <font size='2'>{KIND[col.kind]} - {col.credits:g} credits</font>", "", "", "", ""], "#c9d6ea"))
            if col.kind == "projected":
                body.append(([E("; ".join(f"{c.code} {c.title}" for c in col.cards)), "", "", "", ""], GREY))
                continue
            for c in col.cards:
                bg = RED if (c.status == "Completed" and c.credits > 0 and c.earned == 0) else STATUS_BG.get(c.status, "#ffffff")
                grade = c.grade or ("in progress" if c.status == "In Progress" else "")
                body.append(([f"<b>{E(c.code)}</b>", E(c.title), f"{c.credits:g}", E(grade), f"<font size='2'>{E(c.note)}</font>"], bg))
        h.append(_semester_table(body))

    h.append(f"<hr><p><font size='2' color='#556677'>This summary is a planning aid prepared by your advisor on {today:%B %d, %Y}. It is not an official "
             "transcript or degree audit. Course offerings, times and requirements can change: confirm everything with the Registrar before you register.</font></p>")
    return "<html><body style='font-family:Helvetica,Arial,sans-serif; font-size:10pt'>" + "".join(h) + "</body></html>"


def _semester_table(body) -> str:
    """The semester record: banner rows span all five columns."""
    out = [f"<table border='1' cellspacing='0' cellpadding='3' width='100%' style='border-color:{GRID}'><tr>"
           + "".join(_th(h, w) for h, w in (("Course", "14%"), ("Title", "50%"), ("Cr", "7%"), ("Grade", "12%"), ("", "17%"))) + "</tr>"]
    for cells, bg in body:
        if cells[1:] == ["", "", "", ""]:
            out.append(f"<tr bgcolor='{bg}'><td colspan='5'>{cells[0]}</td></tr>")
        else:
            out.append(f"<tr bgcolor='{bg}'>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    return "".join(out) + "</table>"


def save_pdf(html_text: str, path, title: str = "Advising summary", images: dict | None = None) -> None:
    doc = QTextDocument()
    for name, image in (images or {}).items():
        doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
    doc.setHtml(html_text)
    w = QPdfWriter(str(path))
    w.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
    w.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Unit.Millimeter)
    w.setTitle(title)
    # lay the text out on the real printable area; without this Qt adds ~20 mm of hidden margin on each side
    area = w.pageLayout().paintRect(QPageLayout.Unit.Point)                          # printable area in points (1/72 inch)
    doc.setPageSize(QSizeF(area.width() * 96 / 72, area.height() * 96 / 72))        # ... in the document's own 96-dpi units
    doc.print_(w)


# ============================================================================ dialog
class ReportDialog(QDialog):
    def __init__(self, student_row, student, catalog, audit, projection, rows, advisor_name, transfer, parent=None):
        super().__init__(parent)
        self.ctx = dict(student_row=student_row, advisor_name=advisor_name, catalog=catalog, audit=audit, projection=projection,
                        rows=rows, transfer=transfer, transfer_map=student.transfer_map)
        self.setWindowTitle("Print advising report (PDF)")
        self.setMinimumWidth(560)
        self.boxes = {}
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Include in the report</b>"))
        for key, text in (("summary", "Where you are (credits, progress bars, projected graduation)"),
                          ("chart", "   ...with the credits-by-semester chart"),
                          ("registration", "Registration plan for the next semester (with class sections and times)"),
                          ("requirements", "Degree requirements (tables: what is done, in progress and still needed)"),
                          ("transfer", "Transfer credit evaluation"),
                          ("semesters", "Semester-by-semester record"), ("projected", "   ...including suggested future semesters")):
            cb = QCheckBox(text); cb.setChecked(True); self.boxes[key] = cb; lay.addWidget(cb)
        lay.addWidget(QLabel("<b>Registration semester</b>"))
        self.term = QComboBox()
        for t in (projection.terms[:4] if projection else []):
            self.term.addItem(t.label, (t.term, t.year, list(t.courses)))
        self.term.currentIndexChanged.connect(self._fill_courses)
        lay.addWidget(self.term)
        lay.addWidget(QLabel("Courses to list for registration (untick any you do not want on the sheet):"))
        self.courses = QListWidget(); self.courses.setMaximumHeight(140); lay.addWidget(self.courses)
        lay.addWidget(QLabel("<b>Advisor notes for the student</b>"))
        self.notes = QPlainTextEdit(); self.notes.setPlaceholderText("What you agreed in this meeting, deadlines, who to contact...")
        self.notes.setFixedHeight(110); lay.addWidget(self.notes)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setText("Save PDF...")
        bb.accepted.connect(self.save); bb.rejected.connect(self.reject); lay.addWidget(bb)
        self._fill_courses()

    def _fill_courses(self, *_):
        self.courses.clear()
        data = self.term.currentData()
        if not data:
            return
        cat = self.ctx["catalog"]
        for code in data[2]:
            c = cat.courses.get(code)
            label = f"CORE: {code[len(CORE_PREFIX):]}" if code.startswith(CORE_PREFIX) else f"{code}  {c.name if c else ''}"
            it = QListWidgetItem(label); it.setData(Qt.ItemDataRole.UserRole, code)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable); it.setCheckState(Qt.CheckState.Checked)
            self.courses.addItem(it)

    def html(self) -> str:
        data = self.term.currentData()
        term = (data[0], data[1]) if data else None
        chosen = [self.courses.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.courses.count())
                  if self.courses.item(i).checkState() == Qt.CheckState.Checked]
        lookup = (lambda code: db.sections_of(term[0], term[1], code)) if term else None
        return build_report_html(reg_term=term, reg_courses=chosen, sections_lookup=lookup, notes=self.notes.toPlainText(),
                                 options={k: b.isChecked() for k, b in self.boxes.items()}, **self.ctx)

    def images(self) -> dict:
        c = self.ctx
        return report_images(build_term_columns(c["rows"], c["catalog"], c["projection"], c["transfer_map"], self.boxes["projected"].isChecked()))

    @guard
    def save(self):
        sr = self.ctx["student_row"]
        default = re.sub(r"[^A-Za-z0-9_-]+", "_", f"Advising_{sr['last_name']}_{sr['first_name']}_{date.today():%Y-%m-%d}") + ".pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Save advising report", default, "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        save_pdf(self.html(), path, f"Advising summary - {sr['first_name']} {sr['last_name']}", self.images())
        if not os.path.exists(path) or os.path.getsize(path) < 500:
            show_error(self, "The PDF could not be written. Check that the folder is writable."); return
        info(self, f"Saved:\n{path}\n\nGive this to the student (print it or send it).", "Report saved")
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        self.accept()
