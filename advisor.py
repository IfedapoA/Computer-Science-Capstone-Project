from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget

import backup
from catalog_tabs import BackupTab, CoreTab, CoursesTab, PrereqTab, ProgramsTab, OfferingsTab
from panels import ImportPanel, StudentsPanel, PdfPanel
from plan_tabs import TransferCatalogTab


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