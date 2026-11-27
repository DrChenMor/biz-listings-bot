#!/bin/bash
# The Mac-only bots, without anyone pressing a button: commercialrealestate, AnyBusiness, businessforsale.com.au and
# the SEEK searches, then the website update and the name finder. Started each evening by
# ~/Library/LaunchAgents/com.dealdesk.mac-check.plist, which opens this file in Terminal (macOS lets Terminal, not
# a background job, read the Desktop). Writes to logs/mac-check.log.
# "Check SEEK and CRE.command" still works for running it by hand.
cd "$(dirname "$0")" || exit 1
mkdir -p logs
exec >> logs/mac-check.log 2>&1
echo
echo "==== $(date '+%Y-%m-%d %H:%M') scheduled Mac check"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
# Keep the Mac awake while this runs, so closing the lid halfway doesn't leave it stuck.
caffeinate -i -w $$ &
.venv/bin/python -m bizbot run --store sheet --source commercialrealestate --limit 150
.venv/bin/python -m bizbot run --store sheet --source anybusiness --source businessforsale --limit 60
.venv/bin/python -m bizbot seek --store sheet
.venv/bin/python -m bizbot sync-db
.venv/bin/python -m bizbot names
echo "==== $(date '+%H:%M') done"
