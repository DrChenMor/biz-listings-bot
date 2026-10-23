#!/bin/bash
# Double-click to update the two sites that only work from your Mac:
#   1. commercialrealestate.com.au: WA businesses for sale -> "CRE listings" tab (plain page requests, no window)
#   2. SEEK Business: your searches in a visible Chromium window -> "SEEK listings" tab
# Both go at a person's pace and take a few minutes (the first CRE run, filling ~500 listings, takes longer).
# You can watch the SEEK window, or click into it and take over at any time.
cd "$(dirname "$0")" || exit 1
if [ -f .env ]; then set -a; . ./.env; set +a; fi
echo "== commercialrealestate.com.au"
.venv/bin/python -m bizbot run --store sheet --source commercialrealestate --limit 150
echo
echo "== SEEK Business"
.venv/bin/python -m bizbot seek --store sheet
echo
read -n 1 -s -r -p "Done. Press any key to close this window."
