#!/usr/bin/env bash
# Starts the MySQL database (Docker) and then the Degree Tracker (macOS / Linux).
#   ./start-degree-tracker.sh          empty database
#   ./start-degree-tracker.sh --demo   also load FICTIONAL demo students (sign in as advisor@example.edu)
set -e
cd "$(dirname "$0")"
echo "Starting the database (the first time downloads MySQL, about a minute)..."
if ! docker compose up -d --wait; then
  echo "Could not start the database. Is Docker installed and running?" >&2
  exit 1
fi
if [ -d DegreeTracker.app ]; then
  xattr -dr com.apple.quarantine DegreeTracker.app 2>/dev/null || true   # unsigned app downloaded from the internet
  exec DegreeTracker.app/Contents/MacOS/DegreeTracker "$@"
else
  exec ./DegreeTracker "$@"
fi
