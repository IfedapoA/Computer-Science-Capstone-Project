"""Shared UI helpers, colours and the application style sheet."""
from __future__ import annotations

import re
from functools import wraps

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QCompleter, QDialog, QDialogButtonBox, QFormLayout, QHeaderView,
                               QLineEdit, QMessageBox, QSpinBox, QTableWidget, QTableWidgetItem)

import db

GREEN, AMBER, BLUE = QColor("#d9f2e0"), QColor("#fff0c9"), QColor("#dbe8ff")
STATUS_COLOR = {"Completed": GREEN, "In Progress": AMBER, "Planned": BLUE, "Remaining": None}
CODE_RX = re.compile(r"^[A-Z]{2,6} \d{3}[A-Z]?$")

STYLE = """
QWidget { font-size: 13px; }
QMainWindow, QDialog { background: #fafafa; }
QGroupBox { font-weight: 600; border: 1px solid #cfd6e0; border-radius: 6px; margin-top: 10px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QPushButton { padding: 5px 12px; border: 1px solid #9aa7b8; border-radius: 4px; background: #ffffff; }
QPushButton:hover { background: #eef3fb; }
QPushButton:disabled { color: #999; background: #f0f0f0; }
QPushButton#primary { background: #2f5fa7; color: white; border-color: #2f5fa7; font-weight: 600; }
QPushButton#primary:hover { background: #274f8c; }
QPushButton#danger { color: #a22; }
QTableWidget { gridline-color: #e1e5eb; alternate-background-color: #fbfcfe; }
QHeaderView::section { background: #e9eef6; padding: 4px; border: 0; border-right: 1px solid #d4dbe6; font-weight: 600; }
QProgressBar { border: 1px solid #aab5c5; border-radius: 4px; text-align: center; height: 18px; }
QProgressBar::chunk { background: #4c9f70; }
QLabel#title { font-size: 18px; font-weight: 700; }
QLabel#big { font-size: 20px; font-weight: 700; color: #1f4e8c; }
QLabel#muted { color: #667; }
QLabel#banner { background: #fff6dd; border: 1px solid #ecd48a; border-radius: 4px; padding: 6px; }
"""


def show_error(parent, text: str, title: str = "Something went wrong"):
    QMessageBox.critical(parent, title, text)


def info(parent, text: str, title: str = "Done"):
    QMessageBox.information(parent, title, text)


def confirm(parent, text: str, title: str = "Please confirm") -> bool:
    return QMessageBox.question(parent, title, text) == QMessageBox.StandardButton.Yes


def guard(fn):
    """Slot decorator: show a friendly dialog instead of crashing."""
    @wraps(fn)
    def wrapper(self, *a, **kw):
        try:
            return fn(self, *a, **kw)
        except db.DBError as e:
            show_error(self, str(e))
        except Exception as e:
            show_error(self, f"{type(e).__name__}: {e}")
    return wrapper


def make_table(headers: list[str], stretch_col: int | None = None, select_rows=True) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    if select_rows:
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if stretch_col is not None:
        h.setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
    return t


def fill_table(t: QTableWidget, rows: list[list], colors: list | None = None, ids: list | None = None):
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            item = QTableWidgetItem("" if val is None else str(val))
            if colors and colors[r] is not None:
                item.setBackground(QBrush(colors[r]))
            if ids is not None and c == 0:
                item.setData(Qt.ItemDataRole.UserRole, ids[r])
            t.setItem(r, c, item)


def fit_height(t: QTableWidget, row_h: int = 26):
    t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    t.verticalHeader().setDefaultSectionSize(row_h)
    t.setFixedHeight(28 + row_h * t.rowCount() + 4)


def selected_id(t: QTableWidget):
    rows = t.selectionModel().selectedRows()
    return t.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole) if rows else None


def selected_row(t: QTableWidget):
    rows = t.selectionModel().selectedRows()
    return rows[0].row() if rows else None


def course_combo(courses: list, include_blank: bool = False) -> QComboBox:
    cb = QComboBox()
    cb.setEditable(True)
    cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    if include_blank:
        cb.addItem("", "")
    for c in courses:
        code = c.code if hasattr(c, "code") else c["code"]
        name = c.name if hasattr(c, "name") else c["name"]
        cb.addItem(f"{code} - {name}", code)
    comp = QCompleter(cb.model(), cb)
    comp.setFilterMode(Qt.MatchFlag.MatchContains)
    comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    cb.setCompleter(comp)
    return cb


def combo_code(cb: QComboBox) -> str:
    idx = cb.findText(cb.currentText(), Qt.MatchFlag.MatchFixedString | Qt.MatchFlag.MatchCaseSensitive)
    if idx >= 0:
        return cb.itemData(idx) or ""
    typed = re.sub(r"\s+", " ", cb.currentText().strip().upper())
    i = cb.findData(typed)
    return typed if i >= 0 else ""


def refill_course_combo(cb: QComboBox, select_code: str | None = None):
    cb.clear()
    for c in db.all_courses():
        cb.addItem(f"{c['code']} - {c['name']}", c["code"])
    if select_code:
        cb.setCurrentIndex(max(0, cb.findData(select_code)))


class NewCourseDialog(QDialog):
    """Dialog to dynamically add any outside departmental course (e.g., POLS 101, MUSC 110, BIO 201)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add a course to the catalog")
        self.code = QLineEdit(); self.code.setPlaceholderText("e.g. POLS 101")
        self.title = QLineEdit()
        self.credits = QSpinBox(); self.credits.setRange(0, 12); self.credits.setValue(3)
        f = QFormLayout(self)
        f.addRow("Course code:", self.code); f.addRow("Title:", self.title); f.addRow("Credits:", self.credits)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject); f.addRow(bb)
        self.setMinimumWidth(380)

    def _ok(self):
        code = re.sub(r"\s+", " ", self.code.text().strip().upper())
        m = re.match(r"^([A-Z]{2,6})\s?(\d{3}[A-Z]?)$", code)
        if not m:
            show_error(self, "Course code must look like 'POLS 101'.")
            return
        if not self.title.text().strip():
            show_error(self, "Enter the course title.")
            return
        self.final_code = f"{m.group(1)} {m.group(2)}"
        try:
            db.ensure_course(self.final_code, self.title.text().strip(), self.credits.value())
        except db.DBError as e:
            show_error(self, str(e))
            return
        self.accept()


def add_new_course(parent) -> str | None:
    d = NewCourseDialog(parent)
    return d.final_code if d.exec() else None