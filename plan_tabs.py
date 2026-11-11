"""Dashboard widgets for the student workspace:

    SemesterPlanView    the student's courses laid out semester by semester (Fall 2025, Spring 2026 ...)
    TransferPanel       every transfer course: what it counts as and which requirement(s) it meets
    TransferCatalogTab  all transfer-course decisions in one place (applies to every student)
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHeaderView, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QRadioButton, QScrollArea, QVBoxLayout, QWidget)

import db
from common import (STATUS_COLOR, combo_code, confirm, course_combo, fill_table, guard, info, make_table, selected_id,
                    show_error)
from plan import build_term_columns, credit_summary, transfer_lines, transfer_totals

KIND_TITLE = {"transfer": "TRANSFER", "past": "COMPLETED", "current": "IN PROGRESS", "planned": "PLANNED", "projected": "PROJECTED"}
CARD_BG = {"Completed": "#d9f2e0", "In Progress": "#fff0c9", "Planned": "#dbe8ff", "Projected": "#f4f4f4"}
TRANSFER_BG = "#ece3f7"


# ============================================================================ semester by semester
class SemesterPlanView(QWidget):
    """One column per semester. Past = green, in progress = amber, planned = blue, projected = grey, transfer = lilac."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.columns: list = []
        self._args = None
        self.summary = QLabel(""); self.summary.setObjectName("banner"); self.summary.setWordWrap(True)
        self.show_proj = QCheckBox("Show projected semesters (what is still needed)"); self.show_proj.setChecked(True)
        self.show_proj.toggled.connect(lambda *_: self._render())
        legend = QLabel("<span style='background:#ece3f7'>&nbsp;Transfer&nbsp;</span> <span style='background:#d9f2e0'>&nbsp;Completed&nbsp;</span> "
                        "<span style='background:#fff0c9'>&nbsp;In progress&nbsp;</span> <span style='background:#dbe8ff'>&nbsp;Planned&nbsp;</span> "
                        "<span style='background:#f4f4f4'>&nbsp;Projected (suggested)&nbsp;</span>")
        self.host = QWidget(); self.row = QHBoxLayout(self.host); self.row.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setWidget(self.host)
        top = QHBoxLayout(); top.addWidget(legend, 1); top.addWidget(self.show_proj)
        lay = QVBoxLayout(self); lay.addWidget(self.summary); lay.addLayout(top); lay.addWidget(self.scroll, 1)

    def load(self, rows, catalog, projection, transfer_map=None):
        self._args = (rows, catalog, projection, transfer_map or {})
        self._render()

    def _render(self):
        while self.row.count():
            it = self.row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not self._args:
            return
        rows, catalog, projection, tmap = self._args
        self.columns = build_term_columns(rows, catalog, projection, tmap, include_projected=self.show_proj.isChecked())
        s = credit_summary(self.columns)
        self.summary.setText(f"Earned <b>{s['earned']:g}</b> credits ({s['transfer']:g} transfer)  |  in progress <b>{s['in_progress']:g}</b>  |  "
                             f"planned <b>{s['planned']:g}</b>  |  still to schedule (projected) <b>{s['projected']:g}</b>.  "
                             "Projected courses cover major/minor + CORE requirements only.")
        if not self.columns:
            self.row.addWidget(QLabel("No courses recorded yet."))
        for col in self.columns:
            self.row.addWidget(self._column(col))

    @staticmethod
    def _column(col) -> QFrame:
        f = QFrame(); f.setFixedWidth(232); f.setFrameShape(QFrame.Shape.StyledPanel)
        v = QVBoxLayout(f); v.setSpacing(5)
        head = QLabel(f"<b>{col.label}</b><br><span style='color:#667'>{KIND_TITLE[col.kind]}  -  {col.credits:g} cr</span>")
        head.setWordWrap(True); v.addWidget(head)
        for c in col.cards:
            bg = TRANSFER_BG if c.transfer and c.status == "Completed" else CARD_BG[c.status]
            failed = c.status == "Completed" and c.credits > 0 and c.earned == 0
            if failed:
                bg = "#f6d3d3"
            border = "1px dashed #aaa" if c.status == "Projected" else "1px solid #c9cfd8"
            extra = []
            if c.grade:
                extra.append(f"grade <b>{c.grade}</b>")
            if c.status == "In Progress":
                extra.append("in progress")
            if failed:
                extra.append("no credit earned")
            if c.note:
                extra.append(c.note)
            card = QLabel(f"<b>{c.code}</b> &nbsp;{c.credits:g} cr<br>{c.title}" + (f"<br><i>{' - '.join(extra)}</i>" if extra else ""))
            card.setWordWrap(True); card.setTextFormat(Qt.TextFormat.RichText)
            card.setStyleSheet(f"background:{bg}; border:{border}; border-radius:5px; padding:5px;")
            v.addWidget(card)
        v.addStretch()
        return f


# ============================================================================ transfer credit
STATE_COLOR = {"mapped": STATUS_COLOR["Completed"], "elective": None, "unreviewed": STATUS_COLOR["In Progress"]}
STATE_TEXT = {"mapped": "Evaluated", "elective": "Elective credit only", "unreviewed": "NOT evaluated yet"}


class EquivalencyDialog(QDialog):
    """Decide what a transfer course counts as. Suggestions come from the course title; the advisor decides."""

    def __init__(self, code: str, title: str, credits: float, grade: str, suggestions, current: str | None | bool = False,
                 notes: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Transfer course {code}")
        self.setMinimumWidth(560)
        head = QLabel(f"<b>{code}</b> - {title}<br>{credits:g} credits, grade {grade or '-'}"); head.setWordWrap(True)
        self.rb_course = QRadioButton("Counts as this MSMU course:")
        self.combo = course_combo(db.all_courses())
        self.rb_elective = QRadioButton("Elective credit only (satisfies no specific requirement)")
        self.sug = QListWidget(); self.sug.setMaximumHeight(92)
        for c, name, score in suggestions:
            it = QListWidgetItem(f"{c} - {name}    ({score:.0%} title match)"); it.setData(Qt.ItemDataRole.UserRole, c); self.sug.addItem(it)
        if not suggestions:
            self.sug.addItem("(no confident suggestion - choose the course yourself)")
            self.sug.setEnabled(False)
        self.sug.itemClicked.connect(lambda it: (self.combo.setCurrentIndex(max(0, self.combo.findData(it.data(Qt.ItemDataRole.UserRole)))),
                                                 self.rb_course.setChecked(True)))
        self.note = QLineEdit(notes); self.note.setPlaceholderText("Note (optional), e.g. 'per registrar articulation 2026'")
        if current:
            self.combo.setCurrentIndex(max(0, self.combo.findData(current))); self.rb_course.setChecked(True)
        elif current is None:
            self.rb_elective.setChecked(True)
        elif suggestions:
            self.combo.setCurrentIndex(max(0, self.combo.findData(suggestions[0][0]))); self.rb_course.setChecked(True)
        else:
            self.rb_course.setChecked(True)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(head); lay.addWidget(QLabel("Suggestions (click one to use it):")); lay.addWidget(self.sug)
        lay.addWidget(self.rb_course); lay.addWidget(self.combo); lay.addWidget(self.rb_elective); lay.addWidget(self.note); lay.addWidget(bb)

    def _ok(self):
        if self.rb_course.isChecked() and not combo_code(self.combo):
            show_error(self, "Pick the MSMU course from the list, or choose 'Elective credit only'."); return
        self.accept()

    def values(self) -> tuple[str | None, str]:
        return (combo_code(self.combo) if self.rb_course.isChecked() else None), self.note.text().strip()


class TransferPanel(QWidget):
    COLS = ["Transcript course", "Title on the transcript", "Cr", "Grade", "Counts as", "How it meets the requirements", "Status"]

    def __init__(self, on_changed=None, parent=None):
        super().__init__(parent)
        self.on_changed, self.lines, self.student_id = on_changed, [], None
        self.summary = QLabel("No transfer credit."); self.summary.setObjectName("banner"); self.summary.setWordWrap(True)
        self.table = make_table(self.COLS, stretch_col=5)
        self.table.setWordWrap(True)
        self.table.doubleClicked.connect(lambda *_: self.set_equivalent())
        b1 = QPushButton("Set MSMU equivalent..."); b1.setObjectName("primary"); b1.clicked.connect(self.set_equivalent)
        b2 = QPushButton("Elective credit only"); b2.clicked.connect(self.set_elective)
        b3 = QPushButton("Clear decision"); b3.clicked.connect(self.clear_decision)
        b4 = QPushButton("Accept confident suggestions..."); b4.setToolTip("Applies every suggestion that is a 90%+ title match, after you confirm the list")
        b4.clicked.connect(self.accept_confident)
        self.note = QLabel(""); self.note.setObjectName("muted"); self.note.setWordWrap(True)
        row = QHBoxLayout()
        for b in (b1, b2, b3): row.addWidget(b)
        row.addStretch(); row.addWidget(b4)
        lay = QVBoxLayout(self)
        lay.addWidget(self.summary); lay.addWidget(self.table, 1); lay.addLayout(row); lay.addWidget(self.note)

    def load(self, student_id, rows, student, catalog, audit):
        self.student_id = student_id
        eq = {r["transfer_code"]: {"msmu_code": r["msmu_code"], "notes": r["notes"]} for r in db.transfer_equivalencies()}
        self.lines = transfer_lines(rows, student, catalog, audit, eq, db.msmu_course_candidates())
        t = transfer_totals(self.lines)
        if not self.lines:
            self.summary.setText("This student has no transfer credit. (Transfer courses are imported from a transcript PDF/CSV, "
                                 "or added in the Schedule Editor with 'Transfer credit' ticked.)")
        else:
            self.summary.setText(
                f"<b>{t['total']:g}</b> transfer credits in {len(self.lines)} courses:  <b>{t['mapped']:g}</b> counted as MSMU courses,  "
                f"<b>{t['elective']:g}</b> elective credit only,  <b>{t['unreviewed']:g}</b> not evaluated yet.  "
                f"<b>{t['meets_requirements']:g}</b> credits currently meet a program or CORE requirement.")
        rows_out, colors = [], []
        for ln in self.lines:
            counts = (f"{ln.equivalent} {ln.equivalent_title}" if ln.state == "mapped" else
                      "elective credit only" if ln.state == "elective" else
                      ("not evaluated - suggest: " + f"{ln.suggestions[0][0]} ({ln.suggestions[0][2]:.0%})" if ln.suggestions else "not evaluated"))
            how = "; ".join(ln.meets) + (f"   ! {ln.warning}" if ln.warning else "")
            rows_out.append([ln.code, ln.title, f"{ln.credits:g}", ln.grade, counts, how, STATE_TEXT[ln.state]])
            colors.append(STATE_COLOR[ln.state])
        fill_table(self.table, rows_out, colors, ids=[ln.code for ln in self.lines])
        h = self.table.horizontalHeader()                               # fixed widths for the wordy columns; the "meets" column takes the rest
        for col, width in ((1, 190), (4, 215)):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive); self.table.setColumnWidth(col, width)
        self.table.resizeRowsToContents()
        self.note.setText("A decision is saved for the transfer COURSE and applies to every student who has it. "
                          "Courses without a decision are credited only if their code happens to be an MSMU course - check them.")

    def _line(self):
        code = selected_id(self.table)
        return next((ln for ln in self.lines if ln.code == code), None)

    def _changed(self):
        if self.on_changed:
            self.on_changed()

    @guard
    def set_equivalent(self):
        ln = self._line()
        if not ln:
            show_error(self, "Select a transfer course first."); return
        cur = ln.equivalent if ln.state == "mapped" else (None if ln.state == "elective" else False)
        d = EquivalencyDialog(ln.code, ln.title, ln.credits, ln.grade, ln.suggestions, cur, ln.notes, self)
        if d.exec():
            target, note = d.values()
            db.set_transfer_equivalency(ln.code, target, note)
            self._changed()

    @guard
    def set_elective(self):
        ln = self._line()
        if ln:
            db.set_transfer_equivalency(ln.code, None, ln.notes)
            self._changed()

    @guard
    def clear_decision(self):
        ln = self._line()
        if ln and ln.state != "unreviewed" and confirm(self, f"Remove the decision for {ln.code}? It becomes 'not evaluated' for every student."):
            db.delete_transfer_equivalency(ln.code)
            self._changed()

    @guard
    def accept_confident(self):
        todo = [(ln, ln.suggestions[0]) for ln in self.lines if ln.state == "unreviewed" and ln.suggestions and ln.suggestions[0][2] >= 0.90]
        if not todo:
            info(self, "There is no 90%+ suggestion left to accept."); return
        text = "\n".join(f"{ln.code}  {ln.title}   ->   {s[0]} {s[1]}   ({s[2]:.0%})" for ln, s in todo)
        if confirm(self, f"Count these transfer courses as the MSMU courses shown?\n\n{text}\n\nCheck the list: it is based on titles only."):
            for ln, s in todo:
                db.set_transfer_equivalency(ln.code, s[0], "accepted suggestion")
            self._changed()


class TransferCatalogTab(QWidget):
    """Every transfer-course decision made so far, for all students."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = make_table(["Transfer course", "Counts as", "MSMU title", "Note", "Students", "Decided"], stretch_col=3)
        b1 = QPushButton("Edit selected..."); b1.clicked.connect(self.edit)
        b2 = QPushButton("Delete selected"); b2.setObjectName("danger"); b2.clicked.connect(self.delete)
        info_lbl = QLabel("Decisions are made on a student's <b>Transfer Credit</b> tab. Here you can review, change or remove them."); info_lbl.setObjectName("muted")
        row = QHBoxLayout(); row.addWidget(b1); row.addWidget(b2); row.addStretch()
        lay = QVBoxLayout(self); lay.addWidget(info_lbl); lay.addWidget(self.table, 1); lay.addLayout(row)
        self.refresh()

    @guard
    def refresh(self, *_):
        self.rows = db.transfer_equivalencies()
        fill_table(self.table, [[r["transfer_code"], r["msmu_code"] or "(elective credit only)", r["msmu_title"] or "", r["notes"] or "",
                                 r["students"], f"{r['decided_at']:%Y-%m-%d}" if r["decided_at"] else ""] for r in self.rows],
                   ids=[r["transfer_code"] for r in self.rows])

    @guard
    def edit(self):
        code = selected_id(self.table)
        r = next((x for x in self.rows if x["transfer_code"] == code), None)
        if r:
            d = EquivalencyDialog(code, "", 0, "", [], r["msmu_code"] if r["msmu_code"] else None, r["notes"] or "", self)
            if d.exec():
                target, note = d.values()
                db.set_transfer_equivalency(code, target, note); self.refresh()

    @guard
    def delete(self):
        code = selected_id(self.table)
        if code and confirm(self, f"Delete the decision for {code}? It becomes 'not evaluated' for every student."):
            db.delete_transfer_equivalency(code); self.refresh()
