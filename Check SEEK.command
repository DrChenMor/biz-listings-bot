#!/bin/bash
# Double-click to check your SEEK Business searches (config.toml [seek]) for new listings.
# A Chromium window opens and reads the newest pages at a person's pace; it takes a few minutes.
# You can watch it, or click into the window and take over at any time.
cd "$(dirname "$0")" || exit 1
if [ -f .env ]; then set -a; . ./.env; set +a; fi
.venv/bin/python -m bizbot seek --store sheet "$@"
echo
read -n 1 -s -r -p "Done. Press any key to close this window."
