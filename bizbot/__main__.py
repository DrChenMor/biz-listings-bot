"""Command line:

  python -m bizbot run      businesses for sale (bsale) -> Listings tab
  python -m bizbot health   health practices by suburb (healthdirect + ABN) -> Health businesses tab
  python -m bizbot seek     your SEEK Business searches, in a visible browser window -> SEEK listings tab
  python -m bizbot seek-alerts   SEEK's alert emails in your Gmail (runs on GitHub) -> SEEK listings tab
  python -m bizbot setup    connect this computer to the Google Sheet (asks for the key file and sheet link)

All but setup take [--store sheet|local] [--limit N] [--jitter]. For seek, --limit is result pages per search.
Settings for this computer (SHEET_ID, GOOGLE_SERVICE_ACCOUNT_FILE, ...) can live in a .env file in the project folder.
"""
import argparse
import contextlib
import json
import logging
import os
import platform
import shutil
import sys
from pathlib import Path

from . import config, health, seek, seek_alerts
from .run import run
from .sources import SOURCES
from .store import LocalStore, SheetError, SheetStore, sheet_id_from

log = logging.getLogger("bizbot")
KEY_FILE = "google-service-account.json"


def main() -> int:
    load_env_file(config.ROOT / ".env")
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
    commands.add_parser("seek", parents=[options], help="Your SEEK Business searches, in a visible browser window -> SEEK listings tab")
    commands.add_parser("seek-alerts", parents=[options], help="SEEK alert emails in your Gmail (runs on GitHub) -> SEEK listings tab")
    commands.add_parser("setup", help="Connect this computer to the Google Sheet")
    args = parser.parse_args()
    if args.command == "setup":
        return setup()
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
    on_github = os.environ.get("GITHUB_ACTIONS") == "true"
    try:
        if args.store == "sheet":
            if not os.environ.get("SHEET_ID"):
                raise SheetError("SHEET_ID is not set. Run setup first (or use --store local to test without a Google Sheet).")
            store = SheetStore(os.environ["SHEET_ID"], _google_credentials())
            # Runs from people's computers (CRE, SEEK) take turns, so two never rewrite the same tab at once.
            turn = contextlib.nullcontext() if on_github else store.busy(computer_name(), args.command)
        else:
            store, turn = LocalStore(config.ROOT / "data"), contextlib.nullcontext()
        with turn:
            results = job(cfg, store, limit=args.limit, jitter=args.jitter)
    except SheetError as e:
        log.error("%s", e)
        if on_github:
            print(f"::error title=Google Sheet::{e}")  # shows on the run's summary page
        return 1

    for r in results:
        log.info(
            "%s: %d new, %d updated, %d removed, %d pages opened, %d left for next run, %d errors -> %s",
            r["source"], r["new"], r["updated"], r["removed"], r["fetched"], r["backlog"], r["errors"], r["result"],
        )
        # A site having a bad moment is not a failed run: it's in the Runs tab and retried next run.
        # Only setup problems (sheet, keys) fail the run, so GitHub's failure emails mean "fix something".
        if r["result"] != "ok" and on_github:
            print(f"::warning title={r['source']}::{r['result']}")
    return 0


def setup() -> int:
    """Connect this computer to the Google Sheet: copy in the key file, save the sheet ID, test the connection."""
    print("Connect this computer to the Google Sheet.\n")
    answer = input("1. Drag your Google key file (the .json) into this window, then press Enter:\n> ")
    path = Path(clean_dropped_path(answer)).expanduser()
    try:
        credentials = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"\nCouldn't read {path} as a Google key file. Check the file and try again.")
        return 1
    if not credentials.get("client_email") or not credentials.get("private_key"):
        print("\nThat file isn't a Google service account key (it has no client_email or private_key).")
        return 1
    key_path = config.ROOT / KEY_FILE
    if path.resolve() != key_path.resolve():
        shutil.copyfile(path, key_path)

    link = input("\n2. Paste the Google Sheet's link (or its ID), then press Enter:\n> ")
    try:
        sheet_id = sheet_id_from(link)
        book = SheetStore(sheet_id, credentials).book
    except SheetError as e:
        print(f"\n{e}")
        return 1
    (config.ROOT / ".env").write_text(
        "# Settings for this computer only. Made by setup; not shared.\n"
        f"SHEET_ID={sheet_id}\nGOOGLE_SERVICE_ACCOUNT_FILE={key_path}\n",
        encoding="utf-8",
    )
    print(f"\nDone: this computer is connected to the sheet '{book.title}'.")
    return 0


def load_env_file(path: Path) -> None:
    """KEY=value lines from a .env file into the environment, without overriding what's already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def clean_dropped_path(text: str) -> str:
    """A path dragged into a terminal: Windows wraps it in quotes, macOS escapes spaces with backslashes."""
    text = text.strip().strip('"').strip("'")
    return text.replace("\\ ", " ") if os.sep == "/" else text


def computer_name() -> str:
    return os.environ.get("BIZBOT_COMPUTER") or platform.node().split(".")[0] or "a computer"


def _google_credentials() -> dict:
    raw, path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"), os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not raw and path:
        try:
            raw = Path(path).expanduser().read_text(encoding="utf-8")
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
