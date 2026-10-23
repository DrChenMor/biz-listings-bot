"""Command line:

  python -m bizbot run      businesses for sale (bsale) -> Listings tab
  python -m bizbot health   health practices by suburb (healthdirect + ABN) -> Health businesses tab
  python -m bizbot seek     your SEEK Business searches, in a visible window on your Mac -> SEEK listings tab
  python -m bizbot seek-alerts   SEEK's alert emails in your Gmail (runs on GitHub) -> SEEK listings tab

All take [--store sheet|local] [--limit N] [--jitter]. For seek, --limit is result pages per search.
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import config, health, seek, seek_alerts
from .run import run
from .sources import SOURCES
from .store import LocalStore, SheetError, SheetStore

log = logging.getLogger("bizbot")


def main() -> int:
    options = argparse.ArgumentParser(add_help=False)
    options.add_argument(
        "--store",
        choices=["sheet", "local"],
        default="sheet" if os.environ.get("SHEET_ID") else "local",
        help="sheet = Google Sheet (needs SHEET_ID), local = files in data/ (default when SHEET_ID is not set)",
    )
    options.add_argument("--limit", type=int, help="Most pages to open this run (default: config.toml)")
    options.add_argument("--jitter", action="store_true", help="Wait a random time first (for scheduled runs)")
    options.add_argument("--source", action="append", help="run: only this listing site (repeatable), e.g. --source bsale")
    options.add_argument("-v", "--verbose", action="store_true")
    parser = argparse.ArgumentParser(prog="bizbot", description="Collect businesses into a Google Sheet.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", parents=[options], help="Businesses for sale (bsale) -> Listings tab")
    commands.add_parser("health", parents=[options], help="Health practices by suburb, with ABN owners -> Health businesses tab")
    commands.add_parser("seek", parents=[options], help="Your SEEK Business searches, in a visible window on your Mac -> SEEK listings tab")
    commands.add_parser("seek-alerts", parents=[options], help="SEEK alert emails in your Gmail (runs on GitHub) -> SEEK listings tab")
    args = parser.parse_args()
    job = {"run": run, "health": health.run, "seek": seek.run, "seek-alerts": seek_alerts.run}[args.command]

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    cfg = config.load()
    if args.source:
        unknown = set(args.source) - set(SOURCES)
        if unknown:
            parser.error(f"unknown source {', '.join(sorted(unknown))}; choose from {', '.join(SOURCES)}")
        cfg.sources = args.source
    try:
        if args.store == "sheet":
            if not os.environ.get("SHEET_ID"):
                raise SheetError("SHEET_ID is not set. Use --store local to test without a Google Sheet.")
            store = SheetStore(os.environ["SHEET_ID"], _google_credentials())
        else:
            store = LocalStore(config.ROOT / "data")
        results = job(cfg, store, limit=args.limit, jitter=args.jitter)
    except SheetError as e:
        log.error("%s", e)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::error title=Google Sheet::{e}")  # shows on the run's summary page
        return 1

    for r in results:
        log.info(
            "%s: %d new, %d updated, %d removed, %d pages opened, %d left for next run, %d errors -> %s",
            r["source"], r["new"], r["updated"], r["removed"], r["fetched"], r["backlog"], r["errors"], r["result"],
        )
        # A site having a bad moment is not a failed run: it's in the Runs tab and retried next run.
        # Only setup problems (sheet, keys) fail the run, so GitHub's failure emails mean "fix something".
        if r["result"] != "ok" and os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title={r['source']}::{r['result']}")
    return 0


def _google_credentials() -> dict:
    raw, path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"), os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not raw and path:
        try:
            raw = Path(path).expanduser().read_text()
        except OSError as e:
            raise SheetError(f"Can't read the key file in GOOGLE_SERVICE_ACCOUNT_FILE: {e}") from None
    if not raw:
        raise SheetError("Set GOOGLE_SERVICE_ACCOUNT_JSON (the key's JSON text) or GOOGLE_SERVICE_ACCOUNT_FILE (its path).")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise SheetError(
            "GOOGLE_SERVICE_ACCOUNT_JSON isn't valid JSON. Set it straight from the key file: "
            "gh secret set GOOGLE_SERVICE_ACCOUNT_JSON < path/to/key.json"
        ) from None


if __name__ == "__main__":
    sys.exit(main())
