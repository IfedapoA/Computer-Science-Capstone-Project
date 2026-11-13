"""Catalog management tabs (the advisor does everything; there is no separate admin window):

    CoursesTab | OfferingsTab | CoreTab | ProgramsTab (+ ProgramDialog) | PrereqTab | BackupTab
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget)

import backup
from common import (add_new_course, CODE_RX, combo_code, confirm, course_combo, fill_table, guard, info, make_table,
                    refill_course_combo, selected_id, selected_row, show_error)
import config as cfg
import db
import importer

def _years_combo() -> QComboBox:
    cb = QComboBox()
    ys = db.catalog_years()
    for y in ys:
        cb.addItem(y["label"] + ("  (current)" if y["is_current"] else ""), y["id"])
    cb.setCurrentIndex(next((i for i, y in enumerate(ys) if y["is_current"]), max(0, len(ys) - 1)))
    return cb


# =========================================================================== courses
class CourseDialog(QDialog):
    def __init__(self, row=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit course" if row else "Add course")
        self.code, self.name = QLineEdit(), QLineEdit()
        self.credits = QSpinBox(); self.credits.setRange(0, 12); self.credits.setValue(3)
        self.offered = QComboBox(); self.offered.addItems(["(unknown)", "Fall", "Spring", "Both", "Not Offered"])
        self.notes = QPlainTextEdit(); self.notes.setFixedHeight(70)
        self.notes.setPlaceholderText("e.g. 'Spring of odd years' or 'On a rotating basis' (odd/even years are used by the projection)")
        if row:
            self.code.setText(row["code"]); self.name.setText(row["name"]); self.credits.setValue(row["credits"])
            self.offered.setCurrentText(row["when_offered"] or "(unknown)"); self.notes.setPlainText(row["notes"] or "")
        f = QFormLayout(self)
        for l, w in [("Code (e.g. POLS 101):", self.code), ("Title:", self.name), ("Credits:", self.credits), ("Offered:", self.offered), ("Notes:", self.notes)]:
            f.addRow(l, w)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject); f.addRow(bb); self.setMinimumWidth(520)

    def _ok(self):
        code = importer.normalize_code(self.code.text())
        if not CODE_RX.match(code):
            show_error(self, "Course code must look like 'CMSCI 120' or 'POLS 101'."); return
        if not self.name.text().strip():
            show_error(self, "Title is required."); return
        self.code.setText(code); self.accept()

    def values(self):
        wo = self.offered.currentText()
        return (self.code.text().strip(), self.name.text().strip(), self.credits.value(), None if wo == "(unknown)" else wo, self.notes.toPlainText().strip())


class CoursesTab(QWidget):
    """All courses of the university, grouped by department (= the letters of the course code)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dept = QListWidget(); self.dept.setMaximumWidth(260)
        self.dept.currentRowChanged.connect(lambda *_: self.refresh_courses())
        self.search = QLineEdit(); self.search.setPlaceholderText("Filter by code or title...")
        self.search.textChanged.connect(lambda *_: self.refresh_courses())
        self.table = make_table(["Code", "Title", "Cr", "Offered", "Notes"], stretch_col=1)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        self.count = QLabel(""); self.count.setObjectName("muted")
        row = QHBoxLayout()
        for text, fn, name in (("Add course", self.add, "primary"), ("Edit selected", self.edit, ""), ("Delete selected", self.delete, "danger")):
            b = QPushButton(text); b.clicked.connect(fn)
            if name:
                b.setObjectName(name)
            row.addWidget(b)
        row.addStretch()
        right = QWidget(); rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.search); rv.addWidget(self.table, 1); rv.addWidget(self.count); rv.addLayout(row)
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel("<b>Departments</b>")); lv.addWidget(self.dept)
        split = QSplitter(); split.addWidget(left); split.addWidget(right); split.setSizes([240, 900])
        lay = QVBoxLayout(self); lay.addWidget(split)
        self.refresh()

    @guard
    def refresh(self, *_):
        keep = self.dept.currentItem().data(Qt.ItemDataRole.UserRole) if self.dept.currentItem() else None
        self.dept.blockSignals(True); self.dept.clear()
        total = 0
        deps = db.departments()
        for d in deps:
            total += d["courses"]
            it = QListWidgetItem(f"{d['prefix']} - {d['name']}  ({d['courses']})" if d["name"] != d["prefix"] else f"{d['prefix']}  ({d['courses']})")
            it.setData(Qt.ItemDataRole.UserRole, d["prefix"]); self.dept.addItem(it)
        all_it = QListWidgetItem(f"All departments  ({total})"); all_it.setData(Qt.ItemDataRole.UserRole, None); self.dept.insertItem(0, all_it)
        idx = 0
        for i in range(self.dept.count()):
            if self.dept.item(i).data(Qt.ItemDataRole.UserRole) == keep:
                idx = i
        self.dept.setCurrentRow(idx); self.dept.blockSignals(False)
        self.refresh_courses()

    @guard
    def refresh_courses(self, *_):
        it = self.dept.currentItem()
        prefix = it.data(Qt.ItemDataRole.UserRole) if it else None
        q = self.search.text().strip().lower()
        self._rows = {c["id"]: c for c in db.all_courses(prefix)}
        rows = [c for c in self._rows.values() if not q or q in f"{c['code']} {c['name']}".lower()]
        fill_table(self.table, [[c["code"], c["name"], c["credits"], c["when_offered"] or "(unknown)", c["notes"] or ""] for c in rows], ids=[c["id"] for c in rows])
        self.count.setText(f"{len(rows)} course(s)")

    @guard
    def add(self):
        d = CourseDialog(parent=self)
        if d.exec():
            db.save_course(*d.values()); self.refresh()

    @guard
    def edit(self):
        cid = selected_id(self.table)
        if cid:
            d = CourseDialog(self._rows[cid], self)
            if d.exec():
                db.save_course(*d.values(), course_id=cid); self.refresh()

    @guard
    def delete(self):
        cid = selected_id(self.table)
        if cid and confirm(self, "Delete this course?\n(Refused automatically if any student, requirement or prerequisite still uses it.)"):
            db.delete_course(cid); self.refresh()


# =========================================================================== CORE
class CoreDialog(QDialog):
    def __init__(self, row=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit CORE requirement" if row else "Add CORE requirement")
        self.name = QLineEdit()
        self.take = QComboBox(); self.take.addItems(["Fr", "So", "Ju", "Sr"])
        self.offered = QComboBox(); self.offered.addItems(["Both", "Fall", "Spring"])
        self.credits = QSpinBox(); self.credits.setRange(0, 12); self.credits.setValue(3)
        self.manual = QCheckBox("Advisor marks it satisfied manually (no automatic course matching)")
        self.options = QPlainTextEdit(); self.options.setFixedHeight(110)
        self.options.setPlaceholderText("One per line. Any ONE of these satisfies the requirement.\nPHIL 103\nxxMO 300      <- lowercase x = any letter/digit\nGNSCI xxx")
        self.notes = QPlainTextEdit(); self.notes.setFixedHeight(70)
        if row:
            self.name.setText(row["name"]); self.take.setCurrentText(row["take_as"]); self.offered.setCurrentText(row["offered"])
            self.credits.setValue(row["credits"]); self.manual.setChecked(bool(row["manual_only"]))
            self.options.setPlainText("\n".join(row["options"])); self.notes.setPlainText(row["notes"] or "")
        f = QFormLayout(self)
        for l, w in [("Requirement name:", self.name), ("Take as (Fr/So/Ju/Sr):", self.take), ("Offered:", self.offered), ("Credits:", self.credits),
                     ("", self.manual), ("Courses that satisfy it:", self.options), ("Notes:", self.notes)]:
            f.addRow(l, w)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject); f.addRow(bb); self.setMinimumWidth(560)

    def _ok(self):
        if not self.name.text().strip():
            show_error(self, "Enter the requirement name."); return
        self.accept()

    def values(self):
        opts = [importer.normalize_code(o) if "x" not in o else o.strip() for o in self.options.toPlainText().splitlines() if o.strip()]
        return (self.name.text().strip(), self.take.currentText(), self.offered.currentText(), self.credits.value(),
                self.manual.isChecked(), self.notes.toPlainText().strip(), opts)


class CoreTab(QWidget):
    """The university CORE curriculum: required of every student, versioned by catalog year."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.year = _years_combo()
        self.year.currentIndexChanged.connect(lambda *_: self.refresh())
        self.table = make_table(["Requirement", "Take as", "Offered", "Cr", "Auto-match", "Courses that satisfy it", "Notes"], stretch_col=5)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        top = QHBoxLayout(); top.addWidget(QLabel("Catalog year:")); top.addWidget(self.year); top.addStretch()
        row = QHBoxLayout()
        for text, fn, name in (("Add requirement", self.add, "primary"), ("Edit selected", self.edit, ""), ("Delete selected", self.delete, "danger")):
            b = QPushButton(text); b.clicked.connect(fn)
            if name:
                b.setObjectName(name)
            row.addWidget(b)
        row.addStretch()
        hint = QLabel("These requirements apply to EVERY student under the selected catalog year and appear on each student's Degree Progress tab. "
                      "A lowercase <b>x</b> in a course code is a wildcard (<b>xxGE 3xx</b> matches any department's 3xx Global Encounters course). "
                      "Use <b>Mark selected satisfied</b> on a student for World Languages, waivers and special permissions.")
        hint.setWordWrap(True); hint.setObjectName("banner")
        lay = QVBoxLayout(self); lay.addLayout(top); lay.addWidget(hint); lay.addWidget(self.table, 1); lay.addLayout(row)
        self.refresh()

    @guard
    def refresh(self, *_):
        cy = self.year.currentData()
        if cy is None:
            return
        self._rows = {r["id"]: r for r in db.core_rows(cy)}
        rows = list(self._rows.values())
        fill_table(self.table, [[r["name"], r["take_as"], r["offered"], r["credits"], "no (manual)" if r["manual_only"] else "yes",
                                 ", ".join(r["options"]), r["notes"] or ""] for r in rows], ids=[r["id"] for r in rows])

    @guard
    def add(self):
        d = CoreDialog(parent=self)
        if d.exec():
            name, take, off, cr, man, notes, opts = d.values()
            for o in opts:
                if "x" not in o and not CODE_RX.match(o):
                    show_error(self, f"'{o}' is not a valid course code."); return
                if "x" not in o and not db.get_course(o):
                    db.ensure_course(o, o)            # CORE course not in the catalog yet: create a placeholder
            db.save_core(self.year.currentData(), name, take, off, cr, man, notes, opts); self.refresh()

    @guard
    def edit(self):
        cid = selected_id(self.table)
        if cid:
            d = CoreDialog(self._rows[cid], self)
            if d.exec():
                name, take, off, cr, man, notes, opts = d.values()
                for o in opts:
                    if "x" not in o and not db.get_course(o):
                        db.ensure_course(o, o)
                db.save_core(self.year.currentData(), name, take, off, cr, man, notes, opts, core_id=cid); self.refresh()

    @guard
    def delete(self):
        cid = selected_id(self.table)
        if cid and confirm(self, "Delete this CORE requirement for the selected catalog year?"):
            backup.auto_backup("before deleting a CORE requirement"); db.delete_core(cid); self.refresh()


# =========================================================================== programs
class ProgramsTab(QWidget):
    def __init__(self, on_change=None, parent=None):
        super().__init__(parent)
        self.on_change = on_change
        self.year = _years_combo()
        self.year.currentIndexChanged.connect(lambda *_: self.refresh())
        self.table = make_table(["Code", "Name", "Type", "Department", "Credits", "Source"], stretch_col=1)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        self.overlap = make_table(["Course", "# programs", "Programs"], stretch_col=2); self.overlap.setMaximumHeight(170)
        top = QHBoxLayout(); top.addWidget(QLabel("Catalog year:")); top.addWidget(self.year)
        ny = QPushButton("New catalog year..."); ny.clicked.connect(self.new_year)
        cur = QPushButton("Mark as current"); cur.clicked.connect(self.mark_current)
        top.addWidget(ny); top.addWidget(cur); top.addStretch()
        row = QHBoxLayout()
        for text, fn, name in (("New major / minor...", self.new, "primary"), ("Edit requirements...", self.edit, ""),
                               ("Import programs from CSV...", self.import_csv, ""), ("Delete selected", self.delete, "danger")):
            b = QPushButton(text); b.clicked.connect(fn)
            if name:
                b.setObjectName(name)
            row.addWidget(b)
        row.addStretch()
        lay = QVBoxLayout(self); lay.addLayout(top)
        lay.addWidget(QLabel("<b>Majors and minors</b> - built-in Math/CS programs plus any program from another department "
                             "(Political Science, Music, Biology...) that you add."))
        lay.addWidget(self.table, 1); lay.addLayout(row)
        lay.addWidget(QLabel("<b>Courses that count toward more than one program (selected year)</b>")); lay.addWidget(self.overlap)
        self.refresh()

    @guard
    def refresh(self, *_):
        self._rows = {p["id"]: p for p in db.all_programs()}
        rows = list(self._rows.values())
        fill_table(self.table, [[p["code"], p["name"], p["type"], p["department"] or "Mathematics & Computer Science", p["credits_required"],
                                 "added by advisor" if p["is_custom"] else "Math/CS"] for p in rows], ids=[p["id"] for p in rows])
        cy = self.year.currentData()
        if cy:
            fill_table(self.overlap, [[r["course_code"], r["program_count"], r["programs"]] for r in db.overlap_report(cy)])

    def _changed(self):
        self.refresh()
        if self.on_change:
            self.on_change()

    @guard
    def new(self):
        d = ProgramDialog(self.year.currentData(), None, self)
        if d.exec():
            self._changed()

    @guard
    def edit(self):
        pid = selected_id(self.table)
        if pid:
            d = ProgramDialog(self.year.currentData(), self._rows[pid], self)
            if d.exec():
                self._changed()

    @guard
    def delete(self):
        pid = selected_id(self.table)
        if pid and confirm(self, "Delete this program and its requirements?\n(Refused if a student still has it.)"):
            backup.auto_backup("before deleting a program"); db.delete_program(pid); self._changed()

    @guard
    def import_csv(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose programs CSV", "", "CSV files (*.csv)")
        if not f:
            return
        try:
            pv = importer.parse_programs(f)
        except ValueError as e:
            show_error(self, str(e), "Cannot read file"); return
        msg = f"{len(pv.valid)} program(s) ready, {len(pv.errors)} row(s) rejected, {len(pv.new_courses)} new course(s) to add.\n\n" + "\n".join(pv.notes[:10])
        if pv.errors:
            msg += "\n\nRejected:\n" + "\n".join(f"line {ln}: {m}" for ln, m in pv.errors[:10])
        if pv.valid and confirm(self, msg + "\n\nImport the ready programs?", "Import programs"):
            importer.commit_programs(pv); self._changed()
        elif not pv.valid:
            show_error(self, msg, "Nothing to import")

    @guard
    def new_year(self):
        label, ok = QInputDialog.getText(self, "New catalog year", "Label (e.g. 2027-2028):")
        if not ok:
            return
        m = re.match(r"^(\d{4})-(\d{4})$", label.strip())
        if not m or int(m.group(2)) != int(m.group(1)) + 1:
            show_error(self, "Use the format 2027-2028."); return
        backup.auto_backup("before adding a catalog year")
        db.add_catalog_year(label.strip(), int(m.group(1)), self.year.currentData())
        info(self, f"{label.strip()} was created as a copy of the selected year (requirements and CORE).\nEdit it independently; older years are unchanged.")
        self.year.blockSignals(True); self.year.clear()
        for y in db.catalog_years():
            self.year.addItem(y["label"] + ("  (current)" if y["is_current"] else ""), y["id"])
        self.year.blockSignals(False); self._changed()

    @guard
    def mark_current(self):
        db.set_current_catalog_year(self.year.currentData()); info(self, "Marked as the current catalog year.")


# =========================================================================== prerequisites
class PrereqTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.search = QLineEdit(); self.search.setPlaceholderText("Filter by course...")
        self.search.textChanged.connect(lambda *_: self.refresh())
        self.table = make_table(["Course", "Requires", "Group"], stretch_col=1)
        courses = db.all_courses()
        self.c, self.p = course_combo(courses), course_combo(courses)
        self.g = QSpinBox(); self.g.setRange(1, 9)
        add = QPushButton("Add prerequisite"); add.setObjectName("primary"); add.clicked.connect(self.add)
        rm = QPushButton("Remove selected"); rm.setObjectName("danger"); rm.clicked.connect(self.remove)
        row = QHBoxLayout()
        for w in (QLabel("Course:"), self.c, QLabel("requires:"), self.p, QLabel("group:"), self.g, add, rm):
            row.addWidget(w)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Same group number = <b>OR</b> (any one is enough). Different group numbers = <b>AND</b> (all groups required)."))
        lay.addWidget(self.search); lay.addWidget(self.table, 1); lay.addLayout(row)
        self.refresh()

    @guard
    def refresh(self, *_):
        q = self.search.text().strip().lower()
        fill_table(self.table, [[r["course_code"], r["prereq_course_code"], r["group_no"]] for r in db.prereq_rows()
                                if not q or q in f"{r['course_code']} {r['prereq_course_code']}".lower()])

    @guard
    def add(self):
        a, b = combo_code(self.c), combo_code(self.p)
        if not a or not b:
            show_error(self, "Pick both courses from the lists."); return
        if a == b:
            show_error(self, "A course cannot be its own prerequisite."); return
        db.add_prereq(a, b, self.g.value()); self.refresh()

    @guard
    def remove(self):
        r = selected_row(self.table)
        if r is not None:
            db.delete_prereq(self.table.item(r, 0).text(), self.table.item(r, 1).text()); self.refresh()


# =========================================================================== per-semester university catalog
class BackupTab(QWidget):
    def __init__(self, on_restore=None, parent=None):
        super().__init__(parent)
        self.on_restore = on_restore
        self.status = QLabel(""); self.status.setObjectName("banner"); self.status.setWordWrap(True)
        self.table = make_table(["Created", "Type", "Reason", "Students", "Size (KB)", "File"], stretch_col=2)
        mk = QPushButton("Back up now"); mk.setObjectName("primary"); mk.clicked.connect(self.make)
        res = QPushButton("Restore selected backup..."); res.setObjectName("danger"); res.clicked.connect(self.restore)
        ver = QPushButton("Verify selected"); ver.clicked.connect(self.verify)
        opn = QPushButton("Open backup folder"); opn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(cfg.BACKUP_DIR))))
        row = QHBoxLayout()
        for b in (mk, ver, res, opn):
            row.addWidget(b)
        row.addStretch()
        lay = QVBoxLayout(self)
        lay.addWidget(self.status)
        lay.addWidget(QLabel("<b>Backups</b> - taken automatically when the program starts and closes, and before every import, restore or delete."))
        lay.addWidget(self.table, 1); lay.addLayout(row)
        self.refresh()

    @guard
    def refresh(self, *_):
        self._b = backup.list_backups()
        fill_table(self.table, [[b["created"].replace("T", " "), b["kind"], b["reason"], b["students"], f"{b['size'] / 1024:.0f}", b["path"].name] for b in self._b])
        c = db.query("SELECT (SELECT COUNT(*) FROM students) s, (SELECT COUNT(*) FROM student_courses) c, (SELECT COUNT(*) FROM classes) k, "
                     "(SELECT MAX(version) FROM schema_migrations) v")[0]
        mirror = f"<br>Mirror copy folder: {cfg.BACKUP_MIRROR_DIR}" if cfg.BACKUP_MIRROR_DIR else "<br>Tip: set BACKUP_MIRROR_DIR to a OneDrive/USB folder to keep a second copy automatically."
        self.status.setText(f"Database: <b>{c['s']}</b> students, <b>{c['c']}</b> course records, <b>{c['k']}</b> catalog courses (schema v{c['v']}).<br>"
                            f"Backup folder: {cfg.BACKUP_DIR}{mirror}")

    @guard
    def make(self):
        p = backup.make_backup("manual", "requested by advisor")
        info(self, f"Backup saved:\n{p}"); self.refresh()

    def _sel(self):
        r = selected_row(self.table)
        return self._b[r]["path"] if r is not None else None

    @guard
    def verify(self):
        p = self._sel()
        if not p:
            info(self, "Select a backup first."); return
        try:
            d = backup.verify(p)
            info(self, f"OK - checksum matches. Contains {d['counts'].get('students', 0)} students, {d['counts'].get('student_courses', 0)} course records.")
        except backup.BackupError as e:
            show_error(self, str(e))

    @guard
    def restore(self):
        p = self._sel()
        if not p:
            info(self, "Select a backup first."); return
        if not confirm(self, f"Replace ALL current data with the backup\n{p.name}?\n\nA safety backup of the current data is taken first, and the restore is "
                             "all-or-nothing (if anything fails, nothing changes)."):
            return
        try:
            backup.restore(p)
        except backup.BackupError as e:
            show_error(self, str(e), "Restore failed"); return
        info(self, "Restored successfully."); self.refresh()
        if self.on_restore:
            self.on_restore()



# ============================================================================
# Create / edit a major or minor - including programs OUTSIDE Math & CS (Political Science, Music, Biology ...)
# ============================================================================

class ProgramDialog(QDialog):
    def __init__(self, catalog_year_id: int, program: dict | None = None, parent=None):
        super().__init__(parent)
        self.cy = catalog_year_id
        self.program = program
        self.saved_id: int | None = program["id"] if program else None
        self.setWindowTitle("Edit major / minor" if program else "New major / minor (any department)")
        self.setMinimumWidth(620)
        self.code = QLineEdit(); self.code.setPlaceholderText("short code, e.g. POLS or POLS-M")
        self.name = QLineEdit(); self.name.setPlaceholderText("e.g. Political Science")
        self.type = QComboBox(); self.type.addItems(["Major", "Minor"])
        if program and program["type"] not in ("Major", "Minor"):        # e.g. a built-in "Double Major": keep its type on save
            self.type.addItem(program["type"])
        self.dept = QLineEdit(); self.dept.setPlaceholderText("department / school (optional)")
        self.credits = QSpinBox(); self.credits.setRange(0, 200)
        self.n_el = QSpinBox(); self.n_el.setRange(0, 30)
        form = QFormLayout()
        form.addRow("Code:", self.code); form.addRow("Name:", self.name); form.addRow("Type:", self.type)
        form.addRow("Department:", self.dept); form.addRow("Credits required:", self.credits)
        form.addRow("Electives to choose:", self.n_el)
        self.table = make_table(["Course", "Title", "Cr", "Type"], stretch_col=1)
        self.table.setMinimumHeight(170)
        self.course = course_combo(db.all_courses())
        self.rtype = QComboBox(); self.rtype.addItems(["Core", "Elective"])
        add = QPushButton("Add"); add.clicked.connect(self.add_req)
        new = QPushButton("New course..."); new.clicked.connect(self.new_course)
        rm = QPushButton("Remove selected"); rm.clicked.connect(self.remove_req)
        row = QHBoxLayout()
        for w in (self.course, self.rtype, add, new, rm):
            row.addWidget(w, 1 if w is self.course else 0)
        self.all_years = QCheckBox("Use these requirements for every catalog year")
        self.all_years.setChecked(True)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.save); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(QLabel("<b>Required / elective courses</b> (courses can be from any department; "
                             "use 'New course...' if one is not in the catalog yet)"))
        lay.addWidget(self.table); lay.addLayout(row); lay.addWidget(self.all_years); lay.addWidget(bb)
        self.reqs: list[tuple[str, str]] = []
        if program:
            self.code.setText(program["code"]); self.code.setEnabled(False)
            self.name.setText(program["name"]); self.type.setCurrentText(program["type"])
            self.dept.setText(program["department"] or ""); self.credits.setValue(program["credits_required"])
            self.n_el.setValue(db.electives_needed(self.cy, program["id"]))
            self.reqs = [(r["course_code"], r["requirement_type"]) for r in db.requirement_rows(self.cy, program["id"])]
        self.refresh()

    def refresh(self):
        info = {c["code"]: c for c in db.all_courses()}
        fill_table(self.table, [[c, info.get(c, {}).get("name", "(not in catalog)"), info.get(c, {}).get("credits", ""), t]
                                for c, t in self.reqs])

    @guard
    def add_req(self):
        code = combo_code(self.course)
        if not code:
            show_error(self, "Pick a course from the list (or press 'New course...')."); return
        self.reqs = [(c, t) for c, t in self.reqs if c != code] + [(code, self.rtype.currentText())]
        self.refresh()

    @guard
    def new_course(self):
        code = add_new_course(self)
        if code:
            refill_course_combo(self.course, code)

    def remove_req(self):
        r = selected_row(self.table)
        if r is not None:
            code = self.table.item(r, 0).text()
            self.reqs = [(c, t) for c, t in self.reqs if c != code]
            self.refresh()

    @guard
    def save(self):
        code, name = self.code.text().strip(), self.name.text().strip()
        if not code or not name:
            show_error(self, "Code and name are required."); return
        if not re.match(r"^[A-Za-z0-9&\- ]{1,50}$", code):
            show_error(self, "Code may contain letters, numbers, '-' and '&' only."); return
        pid = db.save_program(code, name, self.type.currentText(), self.credits.value(), self.dept.text().strip(),
                              True, self.program["id"] if self.program else None)
        existing = {r["course_code"] for r in db.requirement_rows(self.cy, pid)}
        for c in existing - {c for c, _ in self.reqs}:
            db.delete_requirement(self.cy, pid, c)
        for c, t in self.reqs:
            db.add_requirement(self.cy, pid, c, t)
        db.set_electives_needed(self.cy, pid, self.n_el.value())
        if self.all_years.isChecked():
            db.copy_requirements_to_all_years(pid, self.cy)
        self.saved_id = pid
        self.accept()



# ============================================================================
# Semester Offerings: browse an imported schedule (e.g. fall.csv) by department
# ============================================================================

DAY_NAMES = {"M": "Mon", "T": "Tue", "W": "Wed", "R": "Thu", "F": "Fri", "S": "Sat", "U": "Sun"}


def _time(t) -> str:
    """MySQL TIME comes back as a timedelta: show 2:00 PM."""
    if t is None:
        return ""
    secs = int(t.total_seconds())
    h, m = secs // 3600, (secs % 3600) // 60
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


class OfferingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.term = QComboBox(); self.dept = QComboBox(); self.search = QLineEdit()
        self.search.setPlaceholderText("Search code or title...")
        self.delete_btn = QPushButton("Delete this semester's offerings"); self.delete_btn.setObjectName("danger")
        self.delete_btn.clicked.connect(self.delete_term)
        self.summary = QLabel(""); self.summary.setObjectName("banner"); self.summary.setWordWrap(True)
        self.courses = make_table(["Course", "Title", "Cr", "Sections", "Delivery", "Instructors"], stretch_col=1)
        self.sections = make_table(["Section", "Part", "Title", "Days", "Time", "Room", "Instructor", "Seats", "Dates"], stretch_col=2)
        self.courses.itemSelectionChanged.connect(self.show_sections)
        top = QHBoxLayout()
        for w in (QLabel("Semester:"), self.term, QLabel("Department:"), self.dept):
            top.addWidget(w)
        top.addWidget(self.search, 1); top.addWidget(self.delete_btn)
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.courses); split.addWidget(self.sections); split.setSizes([360, 240])
        lay = QVBoxLayout(self)
        lay.addLayout(top); lay.addWidget(self.summary); lay.addWidget(split, 1)
        self.term.currentIndexChanged.connect(self._term_changed)
        self.dept.currentIndexChanged.connect(self.refresh_courses)
        self.search.textChanged.connect(self.refresh_courses)
        self.refresh()

    # ------------------------------------------------------------------ data
    @guard
    def refresh(self, *_):
        keep = self.term.currentData()
        self.term.blockSignals(True); self.term.clear()
        for t in db.offering_terms():
            self.term.addItem(f"{t['term']} {t['year']}  ({t['courses']} courses, {t['sections']} sections)", (t["term"], t["year"]))
        if keep:
            self.term.setCurrentIndex(max(0, self.term.findData(keep)))
        self.term.blockSignals(False)
        self._term_changed()

    def _term_changed(self, *_):
        self.dept.blockSignals(True); self.dept.clear()
        data = self.term.currentData()
        self.dept.addItem("All departments", None)
        if data:
            for d in db.offering_departments(*data):
                self.dept.addItem(f"{d['prefix']} - {d['name']}  ({d['courses']})" if d["name"] != d["prefix"] else f"{d['prefix']}  ({d['courses']})",
                                  d["prefix"])
        self.dept.blockSignals(False)
        self.delete_btn.setEnabled(bool(data))
        self.refresh_courses()

    @guard
    def refresh_courses(self, *_):
        data = self.term.currentData()
        if not data:
            fill_table(self.courses, []); fill_table(self.sections, [])
            self.summary.setText("No semester schedule has been imported yet.  Go to  CSV Import  ->  file type  "
                                 "'Semester course offerings'  and choose your fall.csv.")
            return
        rows = db.offered_courses(data[0], data[1], self.dept.currentData(), self.search.text())
        fill_table(self.courses, [[r["course_code"], r["name"], r["credits"], r["sections"], r["delivery"] or "", r["professors"] or ""] for r in rows],
                   ids=[r["course_code"] for r in rows])
        self.summary.setText(f"{data[0]} {data[1]}: showing <b>{len(rows)}</b> course(s). The graduation projection uses this schedule for "
                             f"{data[0]} {data[1]} instead of the catalog's Fall / Spring rules.")
        fill_table(self.sections, [])

    def show_sections(self):
        data, code = self.term.currentData(), selected_id(self.courses)
        if not data or not code:
            return
        rows = db.sections_of(data[0], data[1], code)

        def days(d):
            return " ".join(DAY_NAMES.get(x, x) for x in (d or "").split())

        fill_table(self.sections, [[r["section"], r["component"], r["title"], days(r["days"]) or "no set days",
                                    f"{_time(r['start_time'])} - {_time(r['end_time'])}" if r["start_time"] else "",
                                    " ".join(x for x in (r["location"], r["room"]) if x), r["professor"] or "unassigned",
                                    f"{r['enrollment'] if r['enrollment'] is not None else '?'}/{r['capacity'] if r['capacity'] is not None else '?'}",
                                    f"{r['start_date']:%b %d} - {r['end_date']:%b %d}" if r["start_date"] and r["end_date"] else ""] for r in rows])

    @guard
    def delete_term(self):
        data = self.term.currentData()
        if data and confirm(self, f"Delete all {data[0]} {data[1]} offerings?\n(A safety backup is taken first. Courses stay in the catalog.)"):
            backup.auto_backup(f"before deleting {data[0]} {data[1]} offerings")
            db.delete_term_offerings(*data)
            info(self, "Deleted.")
            self.refresh()
