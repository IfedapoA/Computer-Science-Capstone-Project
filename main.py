"""Undergraduate Degree Tracking Application - the application shell (run this file).

    python main.py                 start the advisor application
    python main.py --demo          also load fictional demo students
    python main.py --selftest      check the installation without opening a window

Contents: sign-in (LoginDialog), the main window (AdvisorWindow), demo data (seed_demo) and the start-up sequence.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton, QTabWidget, QVBoxLayout)

import backup
from catalog_tabs import BackupTab, CoreTab, CoursesTab, OfferingsTab, PrereqTab, ProgramsTab
from common import guard, show_error, STYLE
import config as cfg
import db
import importer
import migrate
from panels import ImportPanel, PdfPanel, StudentsPanel
from plan_tabs import TransferCatalogTab



# ============================================================================
# Sign in (by e-mail, no password: the role is the advisor)
# ============================================================================

class NewAdvisorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create advisor account")
        self.first, self.last, self.email = QLineEdit(), QLineEdit(), QLineEdit()
        f = QFormLayout(self)
        f.addRow("First name:", self.first); f.addRow("Last name:", self.last); f.addRow("E-mail:", self.email)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject); f.addRow(bb)
        self.setMinimumWidth(380)

    @guard
    def _ok(self):
        if not (self.first.text().strip() and self.last.text().strip() and importer.EMAIL_RX.match(self.email.text().strip())):
            show_error(self, "Enter first name, last name, and a valid e-mail address."); return
        db.add_advisor(self.first.text(), self.last.text(), self.email.text())
        self.accept()


class LoginDialog(QDialog):
    """Advisor sign-in by e-mail (no password, per the Project Plan)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Degree Tracker - Advisor Sign in")
        self.setMinimumWidth(440)
        self.user = None
        title = QLabel("Undergraduate Degree Tracker"); title.setObjectName("title")
        sub = QLabel("Mount Saint Mary's University - Academic Advising"); sub.setObjectName("muted")
        self.email = QLineEdit(); self.email.setPlaceholderText("advisor@msmary.edu"); self.email.returnPressed.connect(self.try_login)
        form = QFormLayout(); form.addRow("Advisor e-mail:", self.email)
        self.msg = QLabel(""); self.msg.setStyleSheet("color:#a22;")
        btn = QPushButton("Sign in"); btn.setObjectName("primary"); btn.setDefault(True); btn.clicked.connect(self.try_login)
        new = QPushButton("Create advisor account..."); new.clicked.connect(self.create)
        lay = QVBoxLayout(self)
        lay.addWidget(title); lay.addWidget(sub); lay.addSpacing(10); lay.addLayout(form); lay.addWidget(self.msg)
        row = QHBoxLayout(); row.addWidget(new); row.addStretch(); row.addWidget(btn); lay.addLayout(row)
        if not db.list_advisors():
            self.msg.setStyleSheet("color:#364;")
            self.msg.setText("First time here? Press 'Create advisor account...' to set yourself up.")

    @guard
    def try_login(self):
        email = self.email.text().strip()
        if not email:
            self.msg.setText("Please enter your e-mail address."); return
        user = db.find_advisor(email)
        if not user:
            self.msg.setStyleSheet("color:#a22;")
            self.msg.setText("No advisor found with that e-mail. Use 'Create advisor account...' if new."); return
        self.user = user; self.accept()

    @guard
    def create(self):
        d = NewAdvisorDialog(self)
        if d.exec():
            self.msg.setStyleSheet("color:#364;")
            self.msg.setText("Account created. You can now sign in.")



# ============================================================================
# The main window
# ============================================================================

class AdvisorWindow(QMainWindow):
    """The central advisor dashboard: advisees, CSV/PDF imports, and catalog/CORE/backup management tools."""

    def __init__(self, user):
        super().__init__()
        self.user = user
        self.logout_requested = False
        self.setWindowTitle(f"Degree Tracker - Advisor: {user['first_name']} {user['last_name']}")
        self.resize(1360, 860)
        
        self.students = StudentsPanel(user)
        self.pdf = PdfPanel(user, on_done=self._students_changed)
        self.courses = CoursesTab()
        self.offerings = OfferingsTab()
        self.transfers = TransferCatalogTab()
        self.core = CoreTab()
        self.programs = ProgramsTab(on_change=self.students.refresh)
        self.prereq = PrereqTab()
        self.backups = BackupTab(on_restore=self._after_restore)
        
        self.tabs = QTabWidget()
        for w, name in (
            (self.students, "Advisees"),
            (ImportPanel(user, on_done=self._import_done), "CSV Import"),
            (self.pdf, "J1 PDF to CSV"),
            (self.courses, "Courses"),
            (self.offerings, "Semester Offerings"),
            (self.transfers, "Transfer Equivalencies"),
            (self.core, "CORE Curriculum"),
            (self.programs, "Majors && Minors"),
            (self.prereq, "Prerequisites"),
            (self.backups, "Backup")
        ):
            self.tabs.addTab(w, name)
            
        self.tabs.currentChanged.connect(self._on_tab)
        self.setCentralWidget(self.tabs)
        
        m = self.menuBar().addMenu("&Session")
        out = QAction("Log out", self); out.triggered.connect(self.logout); m.addAction(out)
        q = QAction("Quit", self); q.triggered.connect(self.close); m.addAction(q)
        self.statusBar().addWidget(QLabel(f"Signed in as {user['email_address']}  |  Advisor Workspace"))

    def _students_changed(self):
        self.students.refresh()
        self.pdf.reload_students()

    def _import_done(self):
        self._students_changed()
        self.courses.refresh()                 # an import can add courses to the catalog
        self.offerings.refresh()               # ...or a new semester schedule
        self.transfers.refresh()

    def _after_restore(self):
        self._students_changed()
        self.courses.refresh()
        self.offerings.refresh()
        self.transfers.refresh()
        self.core.refresh()
        self.programs.refresh()

    def _on_tab(self, i):
        w = self.tabs.widget(i)
        if w is self.backups:
            self.backups.refresh()
        elif w is self.courses:
            self.courses.refresh()
        elif w is self.offerings:
            self.offerings.refresh()
        elif w is self.transfers:
            self.transfers.refresh()
        elif w is self.pdf:
            self.pdf.reload_students()

    def logout(self):
        self.logout_requested = True
        self.close()

    def closeEvent(self, e):
        backup.auto_backup("on exit", min_minutes=10)
        super().closeEvent(e)



# ============================================================================
# Optional demo data (fictional people)
# ============================================================================

DEMO_ADVISOR = ("Jane", "Doe", "advisor@example.edu")


def _prog(code):
    return next(p["id"] for p in db.all_programs() if p["code"] == code)


def seed_demo() -> dict:
    if not db.find_advisor(DEMO_ADVISOR[2]):
        db.add_advisor(*DEMO_ADVISOR)
    adv = db.find_advisor(DEMO_ADVISOR[2])["advisor_id"]
    years = {y["label"]: y["id"] for y in db.catalog_years()}
    existing = {s["email_address"] for s in db.list_students()}
    # an outside-the-department program (Political Science minor) to show requirement #5
    if "POLS-M" not in {p["code"] for p in db.all_programs()}:
        for code, title in (("PSCI 100", None), ("PSCI 210", "Comparative Politics"), ("PSCI 220", "International Relations"), ("PSCI 330", "Political Theory")):
            if not db.get_course(code):
                db.ensure_course(code, title or "Introduction to Political Science", 3)
        pid = db.save_program("POLS-M", "Political Science Minor", "Minor", 18, "Political Science", True)
        cy = years["2026-2027"]
        for code, t in (("PSCI 100", "Core"), ("PSCI 210", "Core"), ("PSCI 220", "Core"), ("PSCI 330", "Elective")):
            db.add_requirement(cy, pid, code, t)
        db.set_electives_needed(cy, pid, 1)
        db.copy_requirements_to_all_years(pid, cy)
    people = [
        ("Ada", "Lovelace-Sample", "ada@example.edu", "2025-2026", ["CS"], [
            ("CMSCI 120", "Fall", 2025, "Completed", "A"), ("CMSCI 125", "Spring", 2026, "Completed", "A-"),
            ("MATH 247", "Spring", 2026, "Completed", "B+"), ("MATH 228", "Fall", 2025, "Completed", "A"),
            ("FSYM 101", "Fall", 2025, "Completed", "A"), ("WCIV 102", "Spring", 2026, "Completed", "B"),
            ("PHIL 103", "Spring", 2026, "Completed", "B+"), ("CMSCI 254", "Fall", 2026, "In Progress", None),
            ("CMSCI 277", "Fall", 2026, "In Progress", None)]),
        ("Ben", "Byte", "ben@example.edu", "2024-2025", ["Cyber", "CS"], [
            ("CMSCI 120", "Fall", 2024, "Completed", "B"), ("CMSCI 125", "Spring", 2025, "Completed", "B+"), ("MATH 228", "Spring", 2025, "Completed", "B"),
            ("MATH 247", "Fall", 2025, "Completed", "C+"), ("CMSCI 254", "Fall", 2025, "Completed", "B"), ("CYBER 100", "Spring", 2025, "Completed", "A"),
            ("CYBER 260", "Spring", 2026, "Completed", "B+"), ("CYBER 261", "Fall", 2025, "Completed", "A-"), ("CMSCI 355", "Fall", 2025, "Completed", "B"),
            ("CMSCI 358", "Fall", 2026, "In Progress", None), ("CYBER 301", "Fall", 2026, "In Progress", None)]),
        ("Pia", "Politics", "pia@example.edu", "2026-2027", ["Data", "POLS-M"], [
            ("CMSCI 120", "Fall", 2026, "In Progress", None), ("DATA 200", "Fall", 2026, "In Progress", None), ("PSCI 100", "Fall", 2026, "In Progress", None),
            ("FSYM 101", "Fall", 2026, "In Progress", None)]),
    ]
    made = {}
    for first, last, email, year, progs, courses in people:
        if email in existing:
            continue
        sid = db.add_student(first, last, email, years[year], adv, [_prog(p) for p in progs])
        for code, term, y, status, grade in courses:
            db.save_student_course(sid, code, term, y, status, grade)
        made[email] = sid
    return made


# ============================================================================ start-up
def prepare_database() -> bool:
    """Create / upgrade the database safely without dropping real data. Returns False if the program cannot continue."""
    try:
        migrate.run()
        db.connect().close()
        return True
    except migrate.LegacyDatabase as e:
        if e.student_rows == 0:
            ask = QMessageBox.question(
                None,
                "Rebuild the database?",
                f"{e.message}\n\nRebuild it now? (Old empty tables will be replaced by valid ones, and the CORE curriculum/catalog will be loaded.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ask == QMessageBox.StandardButton.Yes:
                try:
                    migrate.rebuild_unused_legacy()
                    return True
                except (migrate.MigrationError, db.DBError) as e2:
                    QMessageBox.critical(None, "Rebuild failed", str(e2))
            return False
        QMessageBox.critical(None, "Database not changed", str(e))
        return False
    except (migrate.MigrationError, db.DBError) as e:
        QMessageBox.critical(None, "Database problem", str(e))
        return False


def selftest(skip_db: bool = False) -> int:
    """`DegreeTracker --selftest`: checks the installation WITHOUT opening a window (used to verify the built executable).
    The result is also written to degree_tracker_selftest.txt (a windowed Windows .exe has no console to print to)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    ok, out = True, [f"{cfg.APP_NAME} {cfg.VERSION} self-test"]

    def step(name, fn):
        nonlocal ok
        try:
            out.append(f"  ok    {name}: {fn() or ''}")
        except Exception as e:                                     # report every failure, not just the first
            ok = False
            out.append(f"  FAIL  {name}: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}")

    if skip_db:
        out.append("  --    database: skipped (--skip-db)")
    else:
        step("database", lambda: f"{len(migrate.run())} migration(s) applied, {db.query('SELECT COUNT(*) n FROM classes')[0]['n']} courses in the catalog")
    step("PDF reader (pdfplumber)", lambda: __import__("pdfplumber").__version__)
    step("bundled schema file", lambda: f"{migrate.SCHEMA_FILE.name}, {migrate.SCHEMA_FILE.stat().st_size:,} bytes")

    def pdf_out():
        import report
        QApplication.instance() or QApplication(["selftest"])
        path = os.path.join(tempfile.gettempdir(), "degree_tracker_selftest.pdf")
        report.save_pdf("<html><body><h2>self-test</h2><table border='1'><tr><td>ok</td></tr></table></body></html>", path)
        size = os.path.getsize(path)
        os.remove(path)
        assert size > 500
        return f"wrote a {size:,}-byte PDF"
    step("PDF report writer (Qt)", pdf_out)
    out.append("SELFTEST OK" if ok else "SELFTEST FAILED")
    text = "\n".join(out)
    print(text)
    try:
        cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (cfg.DATA_DIR / "degree_tracker_selftest.txt").write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog=cfg.APP_NAME, description="Undergraduate Degree Tracker - advisor desktop application")
    ap.add_argument("--demo", action="store_true", help="load fictional demo students and an advisor (advisor@example.edu), then start")
    ap.add_argument("--selftest", action="store_true", help="check the installation (database, PDF) and exit; no window")
    ap.add_argument("--skip-db", action="store_true", help="with --selftest: do not contact MySQL")
    ap.add_argument("--version", action="version", version=f"{cfg.APP_NAME} {cfg.VERSION}")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest(args.skip_db)

    app = QApplication([sys.argv[0]])
    app.setStyleSheet(STYLE)
    if not prepare_database():
        return 1
    if args.demo:
        seed_demo()
    backup.auto_backup("program start", min_minutes=60)

    while True:
        login = LoginDialog()
        if not login.exec() or not login.user:
            return 0
        win = AdvisorWindow(login.user)
        win.show()
        app.exec()
        if not getattr(win, "logout_requested", False):
            return 0


if __name__ == "__main__":
    sys.exit(main())
