"""Command line: python -m bizbot run [--store sheet|local] [--limit N] [--jitter]"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import config
from .run import run
from .store import LocalStore, SheetStore

log = logging.getLogger("bizbot")


def main() -> int:
    parser = argparse.ArgumentParser(prog="bizbot", description="Collect businesses for sale into a Google Sheet.")
    commands = parser.add_subparsers(dest="command", required=True)
    run_cmd = commands.add_parser("run", help="Run the bot once")
    run_cmd.add_argument(
        "--store",
        choices=["sheet", "local"],
        default="sheet" if os.environ.get("SHEET_ID") else "local",
        help="sheet = Google Sheet (needs SHEET_ID), local = files in data/ (default when SHEET_ID is not set)",
    )
    run_cmd.add_argument("--limit", type=int, help="Most listing pages to open this run (default: config.toml)")
    run_cmd.add_argument("--jitter", action="store_true", help="Wait a random time first (for scheduled runs)")
    run_cmd.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    cfg = config.load()
    if args.store == "sheet":
        if not os.environ.get("SHEET_ID"):
            sys.exit("SHEET_ID is not set. Use --store local to test without a Google Sheet.")
        store = SheetStore(os.environ["SHEET_ID"], _google_credentials())
    else:
        store = LocalStore(config.ROOT / "data")

    results = run(cfg, store, limit=args.limit, jitter=args.jitter)
    for r in results:
        log.info(
            "%s: %d new, %d updated, %d removed, %d pages opened, %d left for next run, %d errors -> %s",
            r["source"], r["new"], r["updated"], r["removed"], r["fetched"], r["backlog"], r["errors"], r["result"],
        )
    return 0 if all(r["result"] == "ok" for r in results) else 1


def _google_credentials() -> dict:
    if raw := os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
        return json.loads(raw)
    if path := os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE"):
        return json.loads(Path(path).expanduser().read_text())
    sys.exit("Set GOOGLE_SERVICE_ACCOUNT_JSON (the key's JSON text) or GOOGLE_SERVICE_ACCOUNT_FILE (its path).")


if __name__ == "__main__":
    sys.exit(main())
