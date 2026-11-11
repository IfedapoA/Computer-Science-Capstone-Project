"""Student list (with add/delete), the CSV import panel and the J1 transcript PDF panel.

    StudentsPanel | ImportPanel (CSV: transcripts, roster, programs, semester offerings) | PdfPanel (J1 PDF -> review -> CSV/import)
The PDF reading itself lives in pdf_import.py; this file is only the screen.
"""
from __future__ import annotations

import csv
from datetime import date
import os
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

import backup
from common import confirm, fill_table, guard, info, make_table, show_error
import db
import importer
import pdf_import
from workspace import StudentWorkspace

class AddStudentDialog(QDialog):
    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add student")
        self.first, self.last, self.email = QLineEdit(), QLineEdit(), QLineEdit()
        self.cy = QComboBox()
        years = db.catalog_years()
        for y in years:
            self.cy.addItem(y["label"], y["id"])
        self.cy.setCurrentIndex(next((i for i, y in enumerate(years) if y["is_current"]), len(years) - 1))
        self.adv = QComboBox(); self.adv.addItem("(unassigned)", None)
        for a in db.list_advisors():
            self.adv.addItem(f"{a['first_name']} {a['last_name']}", a["id"])
        self.adv.setCurrentIndex(self.adv.findData(user["advisor_id"]))
        self.progs = QListWidget(); self.progs.setMaximumHeight(150)
        for p in db.all_programs(base_only=True):
            it = QListWidgetItem(f"{p['code']} - {p['name']}" + ("  [outside department]" if p["is_custom"] else ""))
            it.setData(Qt.ItemDataRole.UserRole, p["id"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable); it.setCheckState(Qt.CheckState.Unchecked)
            self.progs.addItem(it)
        f = QFormLayout(self)
        for l, w in [("First name:", self.first), ("Last name:", self.last), ("E-mail:", self.email), ("Catalog year:", self.cy),
                     ("Advisor:", self.adv), ("Programs:", self.progs)]:
            f.addRow(l, w)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject); f.addRow(bb)
        self.setMinimumWidth(460)

    def _ok(self):
        if not (self.first.text().strip() and self.last.text().strip()):
            show_error(self, "First and last name are required."); return
        if not importer.EMAIL_RX.match(self.email.text().strip()):
            show_error(self, "Enter a valid e-mail address."); return
        self.accept()

    def program_ids(self):
        return [self.progs.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.progs.count())
                if self.progs.item(i).checkState() == Qt.CheckState.Checked]


class StudentsPanel(QWidget):
    """Left: searchable student list. Right: the student's workspace."""

    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self.user = user
        self.rows: list[dict] = []
        self.scope = QComboBox(); self.scope.addItems(["My advisees", "All students"])
        self.scope.currentIndexChanged.connect(lambda *_: self.refresh())
        self.search = QLineEdit(); self.search.setPlaceholderText("Search name, e-mail or program...")
        self.search.textChanged.connect(self.apply_filter)
        self.table = make_table(["Student", "Programs", "Catalog"], stretch_col=0)
        self.table.itemSelectionChanged.connect(self.on_select)
        add = QPushButton("Add student"); add.setObjectName("primary"); add.clicked.connect(self.add_student)
        delete = QPushButton("Delete"); delete.setObjectName("danger"); delete.clicked.connect(self.delete_student)
        self.count = QLabel(""); self.count.setObjectName("muted")
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.scope); lv.addWidget(self.search); lv.addWidget(self.table, 1)
        row = QHBoxLayout(); row.addWidget(add); row.addWidget(delete); lv.addLayout(row); lv.addWidget(self.count)
        self.ws = StudentWorkspace(user)
        self.ws.changed.connect(self.refresh)
        split = QSplitter(); split.addWidget(left); split.addWidget(self.ws)
        split.setStretchFactor(0, 1); split.setStretchFactor(1, 4); split.setSizes([300, 940])
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.addWidget(split)
        self.refresh()

    @guard
    def refresh(self, *_):
        keep = self.current_id()
        self.rows = db.list_students(self.user["advisor_id"] if self.scope.currentIndex() == 0 else None)
        self.apply_filter()
        if keep:
            for r in range(self.table.rowCount()):
                if self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) == keep:
                    self.table.selectRow(r); break

    def apply_filter(self, *_):
        q = self.search.text().strip().lower()
        shown = [s for s in self.rows if not q or q in f"{s['first_name']} {s['last_name']} {s['email_address']} {s['programs'] or ''}".lower()]
        fill_table(self.table, [[f"{s['last_name']}, {s['first_name']}", s["programs"] or "-", s["catalog_year"]] for s in shown], ids=[s["id"] for s in shown])
        self.count.setText(f"{len(shown)} of {len(self.rows)} students")

    def current_id(self):
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole) if rows else None

    def on_select(self):
        self.ws.load(self.current_id())

    def select_student(self, sid: int):
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) == sid:
                self.table.selectRow(r); return

    @guard
    def add_student(self):
        dlg = AddStudentDialog(self.user, self)
        if dlg.exec():
            sid = db.add_student(dlg.first.text(), dlg.last.text(), dlg.email.text(), dlg.cy.currentData(), dlg.adv.currentData(), dlg.program_ids())
            self.refresh(); self.select_student(sid)

    @guard
    def delete_student(self):
        sid = self.current_id()
        if sid and confirm(self, "Delete this student and ALL of their course records and notes?\n"
                                 "A safety backup is taken first so this can be undone from the Backup tab."):
            backup.make_backup("auto", f"before deleting student {sid}")
            db.delete_student(sid); self.ws.load(None); self.refresh()


class ImportPanel(QWidget):
    """CSV batch upload with validate -> review -> import."""
    KINDS = ["Transcripts / schedules", "Student roster (new students)", "Outside majors / minors (programs)",
             "Semester course offerings (e.g. fall.csv)"]

    def __init__(self, user: dict, on_done=None, parent=None):
        super().__init__(parent)
        self.user, self.on_done, self.pv = user, on_done, None
        self.kind = QComboBox(); self.kind.addItems(self.KINDS)
        self.add_missing = QCheckBox("Add courses missing from the catalog")
        self.add_missing.setToolTip("Courses in the file not currently in the catalog are created automatically")
        self.add_missing.setChecked(True)
        # semester controls (only for 'Semester course offerings')
        self.term = QComboBox(); self.term.addItems(["Detect from the file", "Fall", "Spring", "Summer"])
        self.year = QSpinBox(); self.year.setRange(2000, 2100); self.year.setValue(date.today().year)
        self.term.currentIndexChanged.connect(lambda i: self.year.setEnabled(i > 0)); self.year.setEnabled(False)
        self.term_lbl = QLabel("Semester:")
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.path = QLineEdit(); self.path.setReadOnly(True); self.path.setPlaceholderText("Choose a .csv file...")
        browse = QPushButton("Browse..."); browse.clicked.connect(self.browse)
        tmpl = QPushButton("Save CSV template..."); tmpl.clicked.connect(self.save_template)
        self.preview_btn = QPushButton("1. Validate file"); self.preview_btn.clicked.connect(self.preview)
        self.commit_btn = QPushButton("2. Import valid rows"); self.commit_btn.setObjectName("primary")
        self.commit_btn.setEnabled(False); self.commit_btn.clicked.connect(self.commit)
        self.summary = QLabel("Nothing validated yet."); self.summary.setObjectName("banner"); self.summary.setWordWrap(True)
        self.notes = QPlainTextEdit(); self.notes.setReadOnly(True); self.notes.setMaximumHeight(110); self.notes.hide()
        self.errors = make_table(["CSV line", "Problem"], stretch_col=1)
        self.valid = make_table(["Rows that will be imported"], stretch_col=0)
        top = QHBoxLayout(); top.addWidget(QLabel("File type:")); top.addWidget(self.kind); top.addWidget(self.path, 1); top.addWidget(browse); top.addWidget(tmpl)
        act = QHBoxLayout(); act.addWidget(self.preview_btn); act.addWidget(self.commit_btn); act.addWidget(self.add_missing)
        act.addWidget(self.term_lbl); act.addWidget(self.term); act.addWidget(self.year); act.addStretch()
        lay = QVBoxLayout(self)
        lay.addLayout(top); lay.addLayout(act); lay.addWidget(self.summary); lay.addWidget(self.notes)
        lay.addWidget(QLabel("<b>Rejected rows</b> (fix them in the file and validate again):")); lay.addWidget(self.errors, 1)
        lay.addWidget(QLabel("<b>Valid rows</b>")); lay.addWidget(self.valid, 2)
        self._kind_changed(0)

    def _kind_changed(self, i):
        self.add_missing.setVisible(i == 0)
        for w in (self.term_lbl, self.term, self.year):
            w.setVisible(i == 3)
        self.commit_btn.setEnabled(False); self.notes.hide()

    def browse(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose CSV", "", "CSV files (*.csv)")
        if f:
            self.path.setText(f); self.commit_btn.setEnabled(False); self.summary.setText("File chosen. Press Validate.")

    @guard
    def save_template(self):
        i = self.kind.currentIndex()
        cols = [importer.TRANSCRIPT_COLUMNS, importer.ROSTER_COLUMNS, importer.PROGRAM_COLUMNS, importer.OFFERING_COLUMNS][i]
        example = [["ada@example.edu", "POLS 101", "Fall", 2025, "Completed", "A", "", "Intro to Political Science", 3],
                   ["Eli", "Example", "eli@example.edu", "2026-2027", "CS;POLS", "advisor@example.edu"],
                   ["POLS", "Political Science", "Major", 36, "Political Science", "POLS 101", "Core", 3, "", "Intro to Political Science", 3],
                   ["CMSCI-120-A", "Full Semester", "Introduction to Computer Science I", 3, "Classroom (IP)", 25, 0, "EMMIT", "ACNTR 320",
                    "Doe, Jane", "M W", "11:00 AM", "12:15 PM", "Aug 26 2026", "Dec 18 2026"]][i]
        f, _ = QFileDialog.getSaveFileName(self, "Save template", ["transcript_template.csv", "roster_template.csv", "program_template.csv",
                                                                   "offerings_template.csv"][i], "CSV (*.csv)")
        if f:
            with open(f, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh); w.writerow(cols); w.writerow(example)

    @guard
    def preview(self):
        if not self.path.text():
            show_error(self, "Choose a CSV file first."); return
        try:
            i = self.kind.currentIndex()
            if i == 0:
                self.pv = importer.parse_transcript(self.path.text(), self.add_missing.isChecked())
            elif i == 1:
                self.pv = importer.parse_roster(self.path.text())
            elif i == 2:
                self.pv = importer.parse_programs(self.path.text())
            else:
                t = self.term.currentText() if self.term.currentIndex() > 0 else None
                self.pv = importer.parse_offerings(self.path.text(), t, self.year.value() if t else None)
        except ValueError as e:
            show_error(self, str(e), "Cannot read file"); return
        pv = self.pv
        fill_table(self.errors, [[ln, msg] for ln, msg in pv.errors])
        if pv.kind == "transcript":
            rows = [[f"{r['email']}  |  {r['course_code']}  |  {r['term']} {r['year']}  |  {r['status']}  {r['grade'] or ''}"] for r in pv.valid]
        elif pv.kind == "roster":
            rows = [[f"{r['first']} {r['last']}  |  {r['email']}  |  {len(r['program_ids'])} program(s)"] for r in pv.valid]
        elif pv.kind == "offerings":
            rows = [[f"{r['course_code']}-{r['section']}  {r['component']}  |  {r['title']}  |  {r['credits']} cr  |  {r['days'] or 'no set days'} "
                     f"{(r['start_time'] or '')[:5]}  |  {r['professor'] or 'unassigned'}"] for r in pv.valid[:500]]
        else:
            rows = [[f"{p['code']} - {p['name']} ({p['type']})  |  {len(p['reqs'])} course(s)"] for p in pv.valid]
        fill_table(self.valid, rows)
        extra = f"  <b>{len(pv.new_courses)} new course(s)</b> will be added to the catalog." if pv.new_courses else ""
        if pv.kind == "offerings":
            m = pv.meta
            extra = (f"<br>Semester: <b>{m['term']} {m['year']}</b>  -  {m['courses']} courses, {m['sections']} sections, "
                     f"{m['departments']} departments." + extra +
                     f"<br>Importing again for {m['term']} {m['year']} REPLACES that semester only; other semesters are untouched.")
            self.notes.setPlainText("Differences between this schedule and your catalog's own rules (check them):\n" + "\n".join(pv.notes))
            self.notes.setVisible(bool(pv.notes))
        else:
            self.notes.hide()
        self.summary.setText(f"{pv.total_rows} rows read:  <b>{len(pv.valid)} valid</b>,  <b>{len(pv.errors)} rejected</b>.{extra}")
        self.commit_btn.setEnabled(bool(pv.valid))

    @guard
    def commit(self):
        if not self.pv or not self.pv.valid:
            return
        if self.pv.errors and not confirm(self, f"{len(self.pv.errors)} row(s) were rejected and will be skipped.\nImport the {len(self.pv.valid)} valid row(s)?"):
            return
        n = {"transcript": importer.commit_transcript, "roster": importer.commit_roster, "programs": importer.commit_programs,
             "offerings": importer.commit_offerings}[self.pv.kind](self.pv)
        self.commit_btn.setEnabled(False)
        self.summary.setText(f"Imported {n} row(s) successfully.")
        info(self, f"Imported {n} row(s).", "Import complete")
        if self.on_done:
            self.on_done()



# ============================================================================
# J1 PDF -> review table -> CSV / import
# ============================================================================

COLS = ["Use", "Term", "Year", "Course", "Title", "Cr", "Grade", "Status", "Transfer", "Review note"]
AMBER = QColor("#fff0c9")


class RawTextDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Text extracted from the PDF (what the parser sees)")
        box = QPlainTextEdit(text); box.setReadOnly(True)
        lay = QVBoxLayout(self); lay.addWidget(box); self.resize(820, 620)


class PdfPanel(QWidget):
    def __init__(self, user: dict, on_done=None, parent=None):
        super().__init__(parent)
        self.user, self.on_done, self.result = user, on_done, None
        self.path = QLineEdit_ro()
        browse = QPushButton("Choose PDF..."); browse.clicked.connect(self.browse)
        self.student = QComboBox(); self.student.setMinimumWidth(280)
        self.reload_students()
        self.extract_btn = QPushButton("1. Read PDF"); self.extract_btn.setObjectName("primary"); self.extract_btn.clicked.connect(self.extract)
        self.raw_btn = QPushButton("Show raw text..."); self.raw_btn.clicked.connect(self.show_raw); self.raw_btn.setEnabled(False)
        self.header_lbl = QLabel(""); self.header_lbl.setObjectName("muted"); self.header_lbl.setWordWrap(True)
        self.summary = QLabel("Choose a J1 Advising Worksheet / transcript PDF, pick the student it belongs to, then press Read PDF.")
        self.summary.setObjectName("banner"); self.summary.setWordWrap(True)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader(); h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents); h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.save_csv_btn = QPushButton("2a. Save as CSV..."); self.save_csv_btn.clicked.connect(self.save_csv)
        self.import_btn = QPushButton("2b. Import into this student now"); self.import_btn.setObjectName("primary"); self.import_btn.clicked.connect(self.import_now)
        add = QPushButton("Add row"); add.clicked.connect(self.add_row)
        rm = QPushButton("Remove selected row"); rm.clicked.connect(self.remove_row)
        top = QHBoxLayout(); top.addWidget(QLabel("PDF:")); top.addWidget(self.path, 1); top.addWidget(browse)
        r2 = QHBoxLayout(); r2.addWidget(QLabel("Student:")); r2.addWidget(self.student); r2.addWidget(self.extract_btn); r2.addWidget(self.raw_btn); r2.addStretch()
        r3 = QHBoxLayout(); r3.addWidget(add); r3.addWidget(rm); r3.addStretch(); r3.addWidget(self.save_csv_btn); r3.addWidget(self.import_btn)
        lay = QVBoxLayout(self)
        lay.addLayout(top); lay.addLayout(r2); lay.addWidget(self.header_lbl); lay.addWidget(self.summary)
        lay.addWidget(QLabel("<b>Review every row</b> before saving - the cells are editable. Rows with a note are unchecked until you confirm them."))
        lay.addWidget(self.table, 1); lay.addLayout(r3)
        hint = QLabel("All processing happens on this computer (no cloud, no internet). Scanned (image-only) PDFs cannot be read - "
                      "ask J1 for the text version.")
        hint.setObjectName("muted"); hint.setWordWrap(True); lay.addWidget(hint)

    def reload_students(self):
        self.student.clear(); self.student.addItem("(choose the student)", None)
        for s in db.list_students():
            self.student.addItem(f"{s['last_name']}, {s['first_name']}  <{s['email_address']}>", s["email_address"])

    def browse(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose PDF", "", "PDF files (*.pdf)")
        if f:
            self.path.setText(f)

    # ---- extraction
    @guard
    def extract(self):
        if not self.path.text():
            show_error(self, "Choose a PDF file first."); return
        try:
            self.result = pdf_import.parse_pdf(self.path.text())
        except RuntimeError as e:
            show_error(self, str(e), "PDF support missing"); return
        except Exception as e:
            show_error(self, f"Could not read this PDF:\n{e}"); return
        r = self.result
        self.raw_btn.setEnabled(True)
        self.header_lbl.setText("Top of the document: " + "  |  ".join(r.header_lines[:4]))
        if r.student_name and not self.student.currentData():       # pre-select the student whose name is on the PDF
            hits = [s for s in db.list_students() if self._name_matches(r.student_name, s)]
            if len(hits) == 1:
                self.student.setCurrentIndex(max(0, self.student.findData(hits[0]["email_address"])))
        self.table.setRowCount(0)
        for row in r.rows:
            self._append(row)
        use = sum(x.include for x in r.rows)
        msg = f"Found {len(r.rows)} course line(s): <b>{use} ready</b>, {len(r.rows) - use} need your attention (method: {r.method})."
        if r.unparsed:
            msg += f"<br>{len(r.unparsed)} line(s) mention a course but were not understood (see 'Show raw text')."
        for w in r.warnings:
            msg += f"<br><b>{w}</b>"
        self.summary.setText(msg)

    def _append(self, row):
        i = self.table.rowCount(); self.table.insertRow(i)
        use = QTableWidgetItem(); use.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        use.setCheckState(Qt.CheckState.Checked if row.include else Qt.CheckState.Unchecked)
        self.table.setItem(i, 0, use)
        term = QComboBox(); term.addItems(["", "Fall", "Spring", "Summer"]); term.setCurrentText(row.term); self.table.setCellWidget(i, 1, term)
        year = QSpinBox(); year.setRange(0, 2100); year.setValue(row.year); self.table.setCellWidget(i, 2, year)
        status = QComboBox(); status.addItems(["Completed", "In Progress", "Planned"]); status.setCurrentText(row.status or "Completed")
        self.table.setCellWidget(i, 7, status)
        vals = {3: row.code, 4: row.title, 5: f"{row.credits:g}", 6: row.grade, 8: "yes" if row.transfer else "", 9: row.flag}
        for c, v in vals.items():
            it = QTableWidgetItem(v)
            if c == 9:
                it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                if v:
                    it.setBackground(QBrush(AMBER))
            self.table.setItem(i, c, it)

    def add_row(self):
        self._append(pdf_import.ParsedRow(status="Completed", include=True))

    def remove_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def show_raw(self):
        if self.result:
            txt = self.result.raw_text
            if self.result.unparsed:
                txt += "\n\n===== lines mentioning a course that were NOT understood =====\n" + "\n".join(self.result.unparsed)
            RawTextDialog(txt, self).exec()

    # ---- read table back
    def _rows(self) -> list[pdf_import.ParsedRow]:
        out = []
        for i in range(self.table.rowCount()):
            def cell(c):
                it = self.table.item(i, c)
                return it.text().strip() if it else ""
            try:
                cr = float(cell(5) or 3)
            except ValueError:
                cr = 3
            out.append(pdf_import.ParsedRow(
                term=self.table.cellWidget(i, 1).currentText(), year=self.table.cellWidget(i, 2).value(),
                code=importer.normalize_code(cell(3)), title=cell(4), credits=cr, grade=cell(6).upper(),
                status=self.table.cellWidget(i, 7).currentText(), transfer=cell(8).lower() in ("yes", "y", "1", "true"),
                include=self.table.item(i, 0).checkState() == Qt.CheckState.Checked))
        return out

    @staticmethod
    def _name_matches(pdf_name: str, student: dict) -> bool:
        """True if the student's first AND last name both appear in the name printed on the PDF."""
        name = pdf_name.lower()
        first = (student["first_name"].split() or [""])[0].lower()
        last = (student["last_name"].split() or [""])[-1].lower()
        return bool(first) and bool(last) and first in name and last in name

    def _need_student(self) -> str | None:
        email = self.student.currentData()
        if not email:
            show_error(self, "Choose the student these courses belong to.")
            return None
        name = self.result.student_name if self.result else ""
        if name:                                                      # never silently put one person's transcript on another
            s = next((x for x in db.list_students() if x["email_address"] == email), None)
            if s and not self._name_matches(name, s):
                if not confirm(self, f"The PDF is for  \"{name}\"  but you selected  {s['first_name']} {s['last_name']}.\n\n"
                                     "Importing it will put another person's courses on this student.\n\nContinue anyway?", "Name does not match"):
                    return None
        return email

    @guard
    def save_csv(self):
        email = self._need_student()
        if not email:
            return
        f, _ = QFileDialog.getSaveFileName(self, "Save CSV", os.path.splitext(os.path.basename(self.path.text() or "transcript"))[0] + ".csv", "CSV (*.csv)")
        if f:
            n = pdf_import.write_csv(self._rows(), email, f)
            info(self, f"Saved {n} course row(s) to\n{f}\n\nYou can import it from the 'CSV Import' tab.")

    @guard
    def import_now(self):
        email = self._need_student()
        if not email:
            return
        rows = self._rows()
        tmp = os.path.join(tempfile.gettempdir(), "j1_import_tmp.csv")
        n = pdf_import.write_csv(rows, email, tmp)
        if n == 0:
            show_error(self, "No rows are ticked."); return
        pv = importer.parse_transcript(tmp, add_missing=True)
        try:
            os.remove(tmp)
        except OSError:
            pass
        if pv.errors:
            text = "\n".join(f"row {ln - 1}: {msg}" for ln, msg in pv.errors[:12])
            show_error(self, f"{len(pv.errors)} row(s) have problems. Fix or untick them, then try again:\n\n{text}", "Cannot import yet")
            return
        new = f"\n{len(pv.new_courses)} new course(s) will be added to the catalog: " + ", ".join(c['code'] for c in pv.new_courses[:8]) if pv.new_courses else ""
        if confirm(self, f"Import {len(pv.valid)} course row(s) for {self.student.currentText()}?{new}\n\n(A backup is taken first. Existing rows for the same course and term are updated.)"):
            importer.commit_transcript(pv)
            info(self, f"Imported {len(pv.valid)} course row(s).")
            if self.on_done:
                self.on_done()


def QLineEdit_ro():
    from PySide6.QtWidgets import QLineEdit
    e = QLineEdit(); e.setReadOnly(True); e.setPlaceholderText("Choose a J1 PDF..."); return e
