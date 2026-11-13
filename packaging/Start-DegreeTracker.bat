@echo off
rem Starts the MySQL database (Docker) and then the Degree Tracker. Keep this file next to DegreeTracker.exe.
cd /d "%~dp0"
echo Starting the database (the first time downloads MySQL, about a minute)...
docker compose up -d --wait
if errorlevel 1 (
  echo.
  echo Could not start the database. Is Docker Desktop installed and running?
  pause
  exit /b 1
)
start "" "%~dp0DegreeTracker.exe" %*
