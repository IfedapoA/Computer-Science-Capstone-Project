# Degree Tracker - Quick start for reviewers

This folder contains the **Degree Tracker** desktop application. It needs **Docker** for its MySQL database (nothing else to install).

## 1. One-time: install Docker
Docker Desktop (Windows / macOS) or Docker Engine (Linux): https://docs.docker.com/get-docker/ - then start it.

## 2. Start the application
| System | Do this |
|---|---|
| Windows | Double-click **`Start-DegreeTracker-DEMO.bat`** |
| macOS / Linux | Terminal: `./start-degree-tracker.sh --demo` |

The first start downloads MySQL (about a minute). `--demo` loads **fictional** students so every screen has something to show.
Leave `--demo` out (use `Start-DegreeTracker.bat`) to start with an empty database.

> Windows may show "Windows protected your PC" because the program is not code-signed: choose **More info -> Run anyway**.
> macOS: right-click the app -> **Open** the first time.

## 3. Sign in
E-mail **`advisor@example.edu`** (no password). To create your own advisor: *Create advisor account...*

## 4. A 5-minute tour
The demo loads three fictional students: *Lovelace-Sample, Ada* (Computer Science), *Byte, Ben* (Cybersecurity + Computer Science)
and *Politics, Pia* (Data Science + a Political Science minor from outside the department).

1. **Advisees** -> select *Byte, Ben*. **Degree Progress**: both majors and the CORE, with what is done, in progress and needed.
2. **Semester Plan**: Ben's courses semester by semester, plus the suggested remaining semesters.
3. **Schedule Editor**: add a course and tick *Transfer credit*; then **Transfer Credit** lets you decide what it counts as (with title-based suggestions).
4. **Graduation & What-If**: add a minor or a course and compare projected graduation.
5. **Print advising report...** (top right): choose the next semester, type a note, **Save PDF**. This is what the student takes home.
6. **CSV Import** -> **Save CSV template...** shows the format of each import (transcripts, roster, programs, class schedule).
7. **J1 PDF to CSV**: turns a transcript PDF into course rows you review before importing.
8. **Backup** tab: automatic safety copies and one-click restore.

## 5. If something does not start
- *"Cannot reach MySQL"*: Docker is not running. Start Docker Desktop and run the launcher again.
- To use your own MySQL server, create a file `degree_tracker.env` next to the program: `DB_HOST=...`, `DB_USER=...`, `DB_PASSWORD=...`.
- Check the installation without opening a window: `DegreeTracker --selftest` (writes `~/DegreeTracker/degree_tracker_selftest.txt`).

All data stays on this computer. The demo students are fictional.
