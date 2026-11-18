#!/bin/bash
# Double-click to update the sites that turn away GitHub's cloud servers, so only work from your Mac:
#   1. commercialrealestate.com.au: WA businesses for sale -> "CRE listings" tab (plain page requests, no window)
#   2. AnyBusiness and businessforsale.com.au -> "Listings" tab (plain page requests, no window)
#   3. SEEK Business: your searches in a visible Chromium window -> "SEEK listings" tab
# Then it updates the Deal desk website.
# Both go at a person's pace and take a few minutes (the first CRE run, filling ~500 listings, takes longer).
# You can watch the SEEK window, or click into it and take over at any time.
cd "$(dirname "$0")" || exit 1
if [ -f .env ]; then set -a; . ./.env; set +a; fi
echo "== commercialrealestate.com.au"
.venv/bin/python -m bizbot run --store sheet --source commercialrealestate --limit 150
echo
echo "== AnyBusiness and businessforsale.com.au"
.venv/bin/python -m bizbot run --store sheet --source anybusiness --source businessforsale --limit 60
echo
echo "== SEEK Business"
.venv/bin/python -m bizbot seek --store sheet
echo
echo "== Updating the Deal desk website"
.venv/bin/python -m bizbot sync-db
echo
read -n 1 -s -r -p "Done. Press any key to close this window."
