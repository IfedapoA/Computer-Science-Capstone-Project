# PyInstaller recipe for the Degree Tracker.  Build from the repository root:
#     python -m PyInstaller packaging/degree_tracker.spec --distpath dist --workpath build -y
# Windows / Linux -> one file  dist/DegreeTracker(.exe)
# macOS           -> an app     dist/DegreeTracker.app
# PyInstaller cannot cross-compile: every operating system builds its own executable (GitHub Actions does all three).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent          # the repository root (this file lives in packaging/)
IS_MAC = sys.platform == "darwin"

datas = [(str(ROOT / "Capstone_Database.sql"), ".")]       # read by migrate.py from sys._MEIPASS
datas += collect_data_files("pdfminer")                     # CMaps used when reading transcript PDFs

hiddenimports = collect_submodules("mysql.connector")       # auth plug-ins and error messages are imported by name at run time

# Qt modules the program never uses: leaving them out makes the download much smaller.
excludes = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
            "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
            "PySide6.QtNetwork", "PySide6.QtSql", "PySide6.QtTest"]

a = Analysis([str(ROOT / "main.py")], pathex=[str(ROOT)], datas=datas, hiddenimports=hiddenimports,
             excludes=excludes, noarchive=False)
pyz = PYZ(a.pure)

if IS_MAC:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DegreeTracker", console=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="DegreeTracker", upx=False)
    app = BUNDLE(coll, name="DegreeTracker.app", bundle_identifier="edu.capstone.degreetracker",
                 info_plist={"NSHighResolutionCapable": True})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="DegreeTracker",
              console=False,              # no black console window; --selftest writes its result to ~/DegreeTracker/
              upx=False, runtime_tmpdir=None)
