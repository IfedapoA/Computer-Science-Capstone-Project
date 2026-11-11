"""Settings. Everything can be overridden with environment variables or a `degree_tracker.env` file (KEY=VALUE lines)
placed next to the program (or in the folder you start it from).  Example degree_tracker.env:

    DB_HOST=192.168.1.20
    DB_PASSWORD=my-secret
"""
import os
import sys
from pathlib import Path

APP_NAME = "DegreeTracker"
VERSION = "1.0.0"

# ----------------------------------------------------------------------------- where things live
FROZEN = getattr(sys, "frozen", False)                              # True inside the PyInstaller executable
SRC_DIR = Path(__file__).resolve().parent                           # the code
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", SRC_DIR))              # bundled files (Capstone_Database.sql): a temp folder when frozen
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else SRC_DIR.parent   # next to the .exe, or the project root
DATA_DIR = Path.home() / APP_NAME if FROZEN else APP_DIR            # backups survive updates of the program


def _load_env_file() -> None:
    for folder in (Path.cwd(), APP_DIR):
        f = folder / "degree_tracker.env"
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return


_load_env_file()

# ----------------------------------------------------------------------------- database (MySQL 8, see docker-compose.yml)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "capstone")
DB_NAME = os.getenv("DB_NAME", "capstone")
# Pure-Python MySQL driver: used by the packaged executable (the C driver needs MySQL plug-in files that are not bundled).
DB_PURE = os.getenv("DB_PURE", "1" if FROZEN else "0") == "1"
DB_EXTRA = {"use_pure": True} if DB_PURE else {}                  # passed only when True: use_pure=False would REQUIRE the C driver

# ----------------------------------------------------------------------------- backups (kept OUTSIDE the Docker volume)
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", DATA_DIR / "backups"))
BACKUP_MIRROR_DIR = os.getenv("BACKUP_MIRROR_DIR", "")             # optional second copy, e.g. a OneDrive / USB folder
KEEP_AUTO_BACKUPS = int(os.getenv("KEEP_AUTO_BACKUPS", "30"))

# Friendly department names including custom cross-department disciplines
DEPARTMENT_NAMES = {
    "ACCT": "Accounting", "BUS": "Business", "ECON": "Economics", "ESHIP": "Entrepreneurship", "SCM": "Supply Chain Management", "SPMT": "Sports Management",
    "CMSCI": "Computer Science", "CYBER": "Cybersecurity", "DATA": "Data Science", "MATH": "Mathematics",
    "HIST": "History", "PHIL": "Philosophy", "PSCI": "Political Science", "THEOL": "Theology (CORE)",
    "HSRV": "Human Services", "PSYCH": "Psychology", "SOC": "Sociology",
    "CJUST": "Criminal Justice",
    "GNSCI": "General Science (CORE)", "FSYM": "First-Year Symposium (CORE)", "GENED": "General Education (CORE)", "GNSTD": "General Studies (CORE)",
    "AMER": "American In The World (CORE)", "WCIV": "Western Civilization (CORE)", 
    "ARMO": "Modernity in Visual Arts (CORE)", "ENMO": "Modernity in Literature (CORE)", "MUMO": "Modernity in Music (CORE)", "THMO": "Modernity in Theatre (CORE)",
    "ASL": "American Sign Language", "CZECH": "Czech", "ENGL": "English", "FREN": "French", "GERMN": "German", "ITALN": "Italian", "JAPN": "Japanese", "SPAN": "Spanish",
    "BIOCH": "Biochemistry", "BIOL": "Biology", "CHEM": "Chemistry", "NEURO": "Neuroscience", "PHYS": "Physics",
    "BUSGE": "Business Global Encounter (CORE)", "EDGE": "Education Global Encounter (CORE)", "HIGE": "History Global Encounter (CORE)", "PHIGE": "Philosophy Global Encounter (CORE)", "PHGE": "Philosophy Global Encounter (CORE)", "PSGE": "Political Science Global Encounter (CORE)",
    "COMM": "Communication",
    "ECED": "Early Childhood Education",  "EDUC": "Education", "SPED": "Special Education",
    "FAAR": "Fine Arts - Arts", "FAMU": "Fine Arts - Music", "FATH": "Fine Arts - Theatre",
    "HP": "Honors Project",
    "ETHLD": "Ethical Leadership (CORE)",
    "STDAB": "Study Abroad",
    "MSCI": "Military Science"
}