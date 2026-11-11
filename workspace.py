"""Per-student workspace for the advisor:
Degree Progress (+CORE) | Semester Plan | Transfer Credit | Schedule Editor | Programs & Substitutions | Graduation & What-If"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar,
                               QPushButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

import db
from audit import (WhatIf, apply_what_if, audit_student, current_term, missing_prereqs, project_graduation)
from common import (STATUS_COLOR, add_new_course, combo_code, confirm, course_combo, fill_table, fit_height, guard, info,
                    make_table, refill_course_combo, selected_id, show_error)
from catalog_tabs import ProgramDialog
from plan_tabs import SemesterPlanView, TransferPanel
from report import ReportDialog


# ------------------------------------------------------------------ Dialogs
class CourseRecordDialog(QDialog):
    def __init__(self, parent=None, row=None):
        super().__init__(parent)
        self.setWindowTitle("Edit course record" if row else "Add course to schedule")
        self.course = course_combo(db.all_courses())
        new = QPushButton("New course..."); new.setToolTip("Add a course not in the catalog yet (any department)")
        new.clicked.connect(self.new_course)
        self.term = QComboBox(); self.term.addItems(["Fall", "Spring", "Summer"])
        self.year = QSpinBox(); self.year.setRange(1990, 2100); self.year.setValue(current_term()[0])
        self.status = QComboBox(); self.status.addItems(["Completed", "In Progress", "Planned"])
        self.grade = QLineEdit(); self.grade.setMaxLength(3); self.grade.setPlaceholderText("A, B+ ... (needed when Completed)")
        self.transfer = QCheckBox("Transfer credit")
        self.status.currentTextChanged.connect(lambda s: self.grade.setEnabled(s == "Completed"))
        if row:
            self.course.setCurrentIndex(self.course.findData(row["course_code"]))
            self.term.setCurrentText(row["term"]); self.year.setValue(row["year"])
            self.status.setCurrentText(row["status"]); self.grade.setText(row["grade"] or "")
            self.transfer.setChecked(bool(row["is_transfer"]))
        self.grade.setEnabled(self.status.currentText() == "Completed")
        form = QFormLayout(self)
        r = QHBoxLayout(); r.addWidget(self.course, 1); r.addWidget(new)
        form.addRow("Course:", r)
        for label, w in [("Term:", self.term), ("Year:", self.year), ("Status:", self.status), ("Grade:", self.grade), ("", self.transfer)]:
            form.addRow(label, w)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject); form.addRow(bb)
        self.setMinimumWidth(520)

    @guard
    def new_course(self):
        code = add_new_course(self)
        if code:
            refill_course_combo(self.course, code)

    def _ok(self):
        if not combo_code(self.course):
            show_error(self, "Pick a course from the list or press 'New course...'."); return
        if self.status.currentText() == "Completed" and not self.grade.text().strip():
            show_error(self, "A Completed course needs a grade."); return
        self.accept()

    def values(self):
        return (combo_code(self.course), self.term.currentText(), self.year.value(), self.status.currentText(),
                self.grade.text(), self.transfer.isChecked())


class PairDialog(QDialog):
    def __init__(self, required_options, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add approved course substitution")
        self.req = QComboBox()
        for code, name in required_options:
            self.req.addItem(f"{code} - {name}", code)
        self.sub = course_combo(db.all_courses())
        self.note = QPlainTextEdit(); self.note.setPlaceholderText("Reason / approval details"); self.note.setFixedHeight(70)
        f = QFormLayout(self)
        f.addRow("Requirement to replace:", self.req); f.addRow("Course taken instead:", self.sub); f.addRow("Note:", self.note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); f.addRow(bb)
        self.setMinimumWidth(500)


class CoreOverrideDialog(QDialog):
    def __init__(self, core_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Mark satisfied: {core_name}")
        self.course = course_combo(db.all_courses(), include_blank=True)
        self.note = QLineEdit(); self.note.setPlaceholderText("e.g. 'SPAN 102 + SPAN 201' or 'Transfer waiver'")
        f = QFormLayout(self)
        f.addRow("Satisfied by course (optional):", self.course); f.addRow("Note:", self.note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); f.addRow(bb)
        self.setMinimumWidth(520)


# ------------------------------------------------------------------ What-If Panel
class WhatIfPanel(QGroupBox):
    """Never writes to the database; runs the audit/projection engine on an in-memory copy."""

    def __init__(self, ws: "StudentWorkspace"):
        super().__init__("What-If scenario  (nothing here is ever saved)")
        self.ws = ws
        self.prog_list = QListWidget(); self.prog_list.setMaximumHeight(130)
        self.add_courses: list[str] = []
        self.drop_courses: list[str] = []
        self.add_combo = course_combo(db.all_courses())
        self.add_list = QListWidget(); self.add_list.setMaximumHeight(60)
        self.drop_combo = QComboBox()
        self.drop_list = QListWidget(); self.drop_list.setMaximumHeight(60)
        add_btn = QPushButton("Add"); add_btn.clicked.connect(self._add)
        rm_btn = QPushButton("Remove selected"); rm_btn.clicked.connect(lambda: self._rm(self.add_list, self.add_courses))
        drop_btn = QPushButton("Drop"); drop_btn.clicked.connect(self._drop)
        rm2_btn = QPushButton("Remove selected"); rm2_btn.clicked.connect(lambda: self._rm(self.drop_list, self.drop_courses))
        run = QPushButton("Run What-If"); run.setObjectName("primary"); run.clicked.connect(self.run)
        reset = QPushButton("Reset"); reset.clicked.connect(lambda: self.reset())
        self.result = QLabel(); self.result.setWordWrap(True); self.result.setObjectName("banner")
        self.table = make_table(["Term", "Courses", "Credits"], stretch_col=1); self.table.setMaximumHeight(170)
        g = QVBoxLayout(self)
        g.addWidget(QLabel("Programs to include in this scenario:")); g.addWidget(self.prog_list)
        r1 = QHBoxLayout(); r1.addWidget(QLabel("What if already completed:")); r1.addWidget(self.add_combo, 1); r1.addWidget(add_btn); r1.addWidget(rm_btn)
        g.addLayout(r1); g.addWidget(self.add_list)
        r2 = QHBoxLayout(); r2.addWidget(QLabel("What if dropped / never taken:")); r2.addWidget(self.drop_combo, 1); r2.addWidget(drop_btn); r2.addWidget(rm2_btn)
        g.addLayout(r2); g.addWidget(self.drop_list)
        r3 = QHBoxLayout(); r3.addWidget(run); r3.addWidget(reset); r3.addStretch(); g.addLayout(r3)
        g.addWidget(self.result); g.addWidget(self.table)

    def load(self, student, catalog):
        self.student, self.catalog = student, catalog
        self.prog_list.clear()
        for p in db.all_programs(base_only=True):
            it = QListWidgetItem(f"{p['code']} - {p['name']} ({p['type']})")
            it.setData(Qt.ItemDataRole.UserRole, p["id"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if p["id"] in student.program_ids else Qt.CheckState.Unchecked)
            self.prog_list.addItem(it)
        self.drop_combo.clear()
        for code in sorted({c.code for c in student.courses}):
            self.drop_combo.addItem(code, code)
        self.reset(programs=False)

    def _add(self):
        code = combo_code(self.add_combo)
        if code and code not in self.add_courses:
            self.add_courses.append(code); self.add_list.addItem(code)

    def _drop(self):
        code = self.drop_combo.currentData()
        if code and code not in self.drop_courses:
            self.drop_courses.append(code); self.drop_list.addItem(code)

    def _rm(self, lst, store):
        for it in lst.selectedItems():
            store.remove(it.text()); lst.takeItem(lst.row(it))

    def reset(self, programs: bool = True):
        self.add_courses.clear(); self.drop_courses.clear(); self.add_list.clear(); self.drop_list.clear()
        if programs:
            for i in range(self.prog_list.count()):
                it = self.prog_list.item(i)
                it.setCheckState(Qt.CheckState.Checked if it.data(Qt.ItemDataRole.UserRole) in self.student.program_ids else Qt.CheckState.Unchecked)
        self.table.setRowCount(0)
        self.result.setText("Tick/untick programs or add/drop courses, then press Run What-If.")

    def run(self):
        checked = {self.prog_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.prog_list.count())
                   if self.prog_list.item(i).checkState() == Qt.CheckState.Checked}
        cur = set(self.student.program_ids)
        w = WhatIf(sorted(checked - cur), sorted(cur - checked), list(self.add_courses), list(self.drop_courses))
        cap = self.ws.cap.value()
        base = project_graduation(self.student, self.catalog, max_credits=cap)
        alt = project_graduation(apply_what_if(self.student, w), self.catalog, max_credits=cap)
        b, a = base.graduation_label or "cannot be projected", alt.graduation_label or "cannot be projected"
        delta = ""
        if base.graduation_label and alt.graduation_label:
            d = alt.semesters_remaining - base.semesters_remaining
            delta = "   (no change)" if d == 0 else f"   ({abs(d)} term(s) {'later' if d > 0 else 'earlier'})"
        txt = f"Current plan: {b}   ->   What-If: {a}{delta}"
        if alt.blocked:
            txt += "\nBlocked in this scenario: " + "; ".join(f"{c} ({why})" for c, why in alt.blocked[:4])
        self.result.setText(txt)
        fill_table(self.table, [[t.label, ", ".join(t.courses), t.credits] for t in alt.terms])


# ------------------------------------------------------------------ Student Workspace
class StudentWorkspace(QWidget):
    changed = Signal()

    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self.user = user
        self.student_id: int | None = None
        self.header = QLabel("Select a student"); self.header.setObjectName("title")
        self.sub = QLabel(""); self.sub.setObjectName("muted")
        self.tabs = QTabWidget()
        self._build_progress(); self._build_semester(); self._build_transfer(); self._build_schedule(); self._build_programs(); self._build_grad()
        self.report_btn = QPushButton("Print advising report..."); self.report_btn.setObjectName("primary")
        self.report_btn.setToolTip("A PDF the student can take home: progress, registration plan with class times, notes"); self.report_btn.clicked.connect(self.print_report)
        top = QHBoxLayout(); top.addWidget(self.header, 1); top.addWidget(self.report_btn)
        lay = QVBoxLayout(self)
        lay.addLayout(top); lay.addWidget(self.sub); lay.addWidget(self.tabs)
        self.setEnabled(False)

    def _build_semester(self):
        self.semester = SemesterPlanView()
        self.tabs.addTab(self.semester, "Semester Plan")

    def _build_transfer(self):
        self.transfer = TransferPanel(on_changed=self.reload)
        self.tabs.addTab(self.transfer, "Transfer Credit")

    @guard
    def print_report(self):
        if self.student_id is None:
            return
        ReportDialog(self.row, self.student, self.catalog, self.audit, self.proj, self.rows,
                     f"{self.user['first_name']} {self.user['last_name']}", self.transfer.lines, self).exec()

    def _build_progress(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.summary = QLabel(""); self.summary.setObjectName("banner"); self.summary.setWordWrap(True)
        v.addWidget(self.summary)
        self.prog_area = QScrollArea(); self.prog_area.setWidgetResizable(True)
        self.prog_host = QWidget(); self.prog_lay = QVBoxLayout(self.prog_host); self.prog_area.setWidget(self.prog_host)
        v.addWidget(self.prog_area, 1)
        v.addWidget(QLabel("<span style='background:#d9f2e0'>&nbsp;Completed&nbsp;</span> <span style='background:#fff0c9'>&nbsp;In Progress&nbsp;</span> "
                           "<span style='background:#dbe8ff'>&nbsp;Planned&nbsp;</span> &nbsp; Uncolored = still needed"))
        self.tabs.addTab(w, "Degree Progress")

    def _build_schedule(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.sched = make_table(["Course", "Title", "Cr", "Term", "Year", "Status", "Grade", "Transfer"], stretch_col=1)
        self.sched.doubleClicked.connect(lambda *_: self.edit_course())
        v.addWidget(self.sched)
        row = QHBoxLayout()
        add = QPushButton("Add course"); add.setObjectName("primary"); add.clicked.connect(self.add_course)
        edit = QPushButton("Edit selected"); edit.clicked.connect(self.edit_course)
        dele = QPushButton("Delete selected"); dele.setObjectName("danger"); dele.clicked.connect(self.del_course)
        for b in (add, edit, dele):
            row.addWidget(b)
        row.addStretch(); v.addLayout(row)
        self.tabs.addTab(w, "Schedule Editor")

    def _build_programs(self):
        w = QWidget(); v = QVBoxLayout(w)
        form = QFormLayout()
        self.cy_combo, self.adv_combo = QComboBox(), QComboBox()
        form.addRow("Catalog year:", self.cy_combo); form.addRow("Advisor:", self.adv_combo)
        v.addLayout(form)
        v.addWidget(QLabel("<b>Declared majors / minors</b> (including outside Math & Computer Science):"))
        self.prog_check = QListWidget(); v.addWidget(self.prog_check, 2)
        row = QHBoxLayout()
        outside = QPushButton("Add outside major/minor..."); outside.clicked.connect(self.add_outside_program)
        save = QPushButton("Save changes"); save.setObjectName("primary"); save.clicked.connect(self.save_programs)
        row.addWidget(outside); row.addWidget(save); row.addStretch(); v.addLayout(row)
        v.addWidget(QLabel("<b>Approved course substitutions</b>"))
        self.sub_table = make_table(["Requirement", "Replaced by", "Note"], stretch_col=2); v.addWidget(self.sub_table, 1)
        r2 = QHBoxLayout()
        a = QPushButton("Add substitution..."); a.clicked.connect(self.add_sub)
        d = QPushButton("Delete selected"); d.setObjectName("danger"); d.clicked.connect(self.del_sub)
        r2.addWidget(a); r2.addWidget(d); r2.addStretch(); v.addLayout(r2)
        self.tabs.addTab(w, "Programs && Substitutions")

    def _build_grad(self):
        w = QWidget(); v = QVBoxLayout(w)
        top = QHBoxLayout()
        self.grad_label = QLabel(""); self.grad_label.setObjectName("big")
        top.addWidget(self.grad_label, 1); top.addWidget(QLabel("Max credits per term:"))
        self.cap = QSpinBox(); self.cap.setRange(6, 21); self.cap.setValue(15)
        self.cap.valueChanged.connect(lambda *_: self.recompute())
        top.addWidget(self.cap); v.addLayout(top)
        self.grad_table = make_table(["Term", "Courses", "Credits"], stretch_col=1); self.grad_table.setMaximumHeight(220)
        v.addWidget(self.grad_table)
        self.notes_box = QPlainTextEdit(); self.notes_box.setReadOnly(True); self.notes_box.setMaximumHeight(90)
        v.addWidget(self.notes_box)
        self.whatif = WhatIfPanel(self); v.addWidget(self.whatif)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setWidget(w)
        self.tabs.addTab(sc, "Graduation && What-If")

    @guard
    def load(self, student_id: int | None):
        self.student_id = student_id
        if student_id is None:
            self.setEnabled(False); self.header.setText("Select a student"); self.sub.setText(""); return
        self.setEnabled(True)
        self.row = db.get_student_row(student_id)
        self.student = db.load_student(student_id)
        self.catalog = db.load_catalog(self.row["catalog_year_id"])
        self.header.setText(self.student.name)
        progs = ", ".join(self.catalog.programs[p].code for p in self.student.program_ids if p in self.catalog.programs)
        self.sub.setText(f"{self.row['email_address']}   |   Catalog {self.row['catalog_year']}   |   Programs: {progs or 'none declared'}")
        self.recompute()
        self.refresh_schedule(); self.refresh_programs()
        self.whatif.load(self.student, self.catalog)

    def recompute(self):
        if self.student_id is None:
            return
        self.audit = audit_student(self.student, self.catalog)
        self.proj = project_graduation(self.student, self.catalog, max_credits=self.cap.value())
        self.refresh_progress(); self.refresh_grad()
        self.rows = db.student_course_rows(self.student_id)
        self.semester.load(self.rows, self.catalog, self.proj, self.student.transfer_map)
        self.transfer.load(self.student_id, self.rows, self.student, self.catalog, self.audit)

    def reload(self):
        self.load(self.student_id); self.changed.emit()

    def _clear(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def refresh_progress(self):
        res = self.audit
        self._clear(self.prog_lay)
        for pa in res.programs:
            tag = "  [outside department]" if pa.program.is_custom else ""
            box = QGroupBox(f"{pa.program.code} - {pa.program.name}  ({pa.program.type}){tag}")
            bv = QVBoxLayout(box)
            bar = QProgressBar(); bar.setRange(0, 100); bar.setValue(int(pa.percent_complete))
            bar.setFormat(f"{pa.units_completed} done + {pa.units_in_progress} in progress of {pa.units_total} requirements  ({pa.percent_complete:.0f}% complete)")
            bv.addWidget(bar)
            t = make_table(["Course", "Title", "Cr", "Type", "Status", "When", "Grade", "Also counts toward"], stretch_col=1)
            fill_table(t, [[i.code, i.name, i.credits or "", i.kind, i.status + (f" (via {i.via})" if i.via else ""), i.when, i.grade,
                            ", ".join(i.also_counts_for)] for i in pa.items], [STATUS_COLOR[i.status] for i in pa.items])
            fit_height(t); bv.addWidget(t)
            if not pa.items:
                bv.addWidget(QLabel("<i>No requirements entered for this program yet.</i>"))
            if pa.electives_remaining and pa.elective_options:
                lab = QLabel("Elective options: " + ", ".join(pa.elective_options)); lab.setWordWrap(True); lab.setObjectName("muted")
                bv.addWidget(lab)
            self.prog_lay.addWidget(box)
        if res.core:
            self._core_box(res.core)
        self.prog_lay.addStretch()
        shared = ", ".join(f"{c} ({'+'.join(p)})" for c, p in sorted(res.shared_courses.items()))
        self.summary.setText(f"Distinct major/minor courses still needed: <b>{res.unique_remaining}</b>"
                             + (f"<br>Courses counting toward more than one program: {shared}" if shared else ""))

    def _core_box(self, core):
        box = QGroupBox("CORE Curriculum  (required of every student)")
        bv = QVBoxLayout(box)
        bar = QProgressBar(); bar.setRange(0, 100); bar.setValue(int(core.percent_complete))
        bar.setFormat(f"{core.units_completed} done + {core.units_in_progress} in progress of {core.units_total} CORE requirements ({core.percent_complete:.0f}% complete)")
        bv.addWidget(bar)
        self.core_table = make_table(["Requirement", "Take as", "Offered", "Cr", "Status", "Satisfied by", "When", "Grade", "Notes"], stretch_col=8)
        rows = [[i.req.name, {"Fr": "Freshman", "So": "Sophomore", "Ju": "Junior", "Sr": "Senior"}[i.req.take_as], i.req.offered, i.req.credits,
                 i.status, i.satisfied_by, i.when, i.grade, i.note or i.req.notes] for i in core.items]
        fill_table(self.core_table, rows, [STATUS_COLOR[i.status] for i in core.items], [i.req.id for i in core.items])
        fit_height(self.core_table); bv.addWidget(self.core_table)
        row = QHBoxLayout()
        mark = QPushButton("Mark selected satisfied..."); mark.clicked.connect(self.mark_core)
        clear = QPushButton("Clear mark"); clear.clicked.connect(self.clear_core)
        row.addWidget(mark); row.addWidget(clear); row.addStretch(); bv.addLayout(row)
        self.prog_lay.addWidget(box)

    @guard
    def mark_core(self):
        cid = selected_id(self.core_table)
        if cid is None:
            info(self, "Select a CORE requirement first.", "Nothing selected"); return
        name = next(i.req.name for i in self.audit.core.items if i.req.id == cid)
        d = CoreOverrideDialog(name, self)
        if d.exec():
            db.set_core_override(self.student_id, cid, combo_code(d.course), d.note.text().strip())
            self.reload()

    @guard
    def clear_core(self):
        cid = selected_id(self.core_table)
        if cid is not None:
            db.clear_core_override(self.student_id, cid); self.reload()

    def refresh_schedule(self):
        rows = db.student_course_rows(self.student_id)
        self._sched_rows = {r["id"]: r for r in rows}
        fill_table(self.sched, [[r["course_code"], r["name"], r["credits"], r["term"], r["year"], r["status"], r["grade"] or "",
                                 "Yes" if r["is_transfer"] else ""] for r in rows], [STATUS_COLOR[r["status"]] for r in rows], [r["id"] for r in rows])

    @guard
    def add_course(self):
        self._course_dialog(None)

    @guard
    def edit_course(self):
        rid = selected_id(self.sched)
        if rid:
            self._course_dialog(self._sched_rows[rid])

    def _course_dialog(self, row):
        dlg = CourseRecordDialog(self, row)
        if not dlg.exec():
            return
        code, term, year, status, grade, transfer = dlg.values()
        have = {c.code for c in self.student.courses if c.status in ("Completed", "In Progress")}
        miss = missing_prereqs(self.catalog, code, have)
        if miss and status != "Completed":
            if not confirm(self, f"{code} requires: " + "; ".join(" or ".join(g) for g in miss) +
                           "\n\nPrerequisites not met. Save anyway?"):
                return
        db.save_student_course(self.student_id, code, term, year, status, grade, transfer, row["id"] if row else None)
        self.reload()

    @guard
    def del_course(self):
        rid = selected_id(self.sched)
        if rid and confirm(self, "Delete this course record?"):
            import backup
            backup.auto_backup("before deleting course", min_minutes=5)
            db.delete_student_course(rid); self.reload()

    def refresh_programs(self):
        self.cy_combo.clear()
        for y in db.catalog_years():
            self.cy_combo.addItem(y["label"], y["id"])
        self.cy_combo.setCurrentIndex(self.cy_combo.findData(self.row["catalog_year_id"]))
        self.adv_combo.clear(); self.adv_combo.addItem("(unassigned)", None)
        for a in db.list_advisors():
            self.adv_combo.addItem(f"{a['first_name']} {a['last_name']}", a["id"])
        self.adv_combo.setCurrentIndex(self.adv_combo.findData(self.row["advisor_id"]))
        self._fill_prog_check(set(self.student.program_ids))
        subs = db.list_substitutions(self.student_id)
        fill_table(self.sub_table, [[s["required_course_code"], s["substitute_course_code"], s["note"] or ""] for s in subs], ids=[s["id"] for s in subs])

    def _fill_prog_check(self, checked: set[int]):
        self.prog_check.clear()
        for p in db.all_programs(base_only=True):
            tag = "   [outside department]" if p["is_custom"] else ""
            it = QListWidgetItem(f"{p['code']} - {p['name']} ({p['type']}){tag}")
            it.setData(Qt.ItemDataRole.UserRole, p["id"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if p["id"] in checked else Qt.CheckState.Unchecked)
            self.prog_check.addItem(it)

    def _checked_programs(self) -> set[int]:
        return {self.prog_check.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.prog_check.count())
                if self.prog_check.item(i).checkState() == Qt.CheckState.Checked}

    @guard
    def add_outside_program(self):
        d = ProgramDialog(self.row["catalog_year_id"], None, self)
        if d.exec() and d.saved_id:
            keep = self._checked_programs() | {d.saved_id}
            self._fill_prog_check(keep)
            info(self, "Program created and ticked. Press 'Save changes' to attach it.")

    @guard
    def save_programs(self):
        db.update_student(self.student_id, self.cy_combo.currentData(), self.adv_combo.currentData(), sorted(self._checked_programs()))
        self.reload()
        info(self, "Programs, catalog year and advisor saved.", "Saved")

    @guard
    def add_sub(self):
        remaining = sorted({(i.code, i.name) for pa in self.audit.programs for i in pa.items if i.status == "Remaining" and i.kind == "Core"})
        if not remaining:
            info(self, "No remaining required courses to substitute.", "Nothing to substitute"); return
        d = PairDialog(remaining, self)
        if d.exec():
            sub = combo_code(d.sub)
            if not sub:
                show_error(self, "Pick the substitute course from the list."); return
            db.add_substitution(self.student_id, d.req.currentData(), sub, d.note.toPlainText())
            self.reload()

    @guard
    def del_sub(self):
        sid = selected_id(self.sub_table)
        if sid:
            db.delete_substitution(sid); self.reload()

    def refresh_grad(self):
        p = self.proj
        self.grad_label.setText(f"Projected graduation: {p.graduation_label}   ({p.semesters_remaining} more term(s))"
                                if p.graduation_label else "Projected graduation: cannot be determined (see blocked courses)")
        fill_table(self.grad_table, [[t.label, ", ".join(t.courses) + ("   [pinned: " + ", ".join(t.pinned) + "]" if t.pinned else ""), t.credits]
                                     for t in p.terms])
        lines = [f"Starts {p.start_label}. Covers major/minor + CORE requirements only."]
        lines += [f"BLOCKED  {c}: {why}" for c, why in p.blocked] + [f"WARNING  {x}" for x in p.warnings] + [f"Assumption: {x}" for x in p.assumptions]
        self.notes_box.setPlainText("\n".join(lines))