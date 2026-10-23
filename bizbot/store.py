"""Where listings live: a Google Sheet for real runs, or local files for testing.

The Google Sheet has three tabs:
  Listings  one row per listing. The bot owns columns A to the "Key" column; add your own
            columns to the right of those (e.g. "Contacted?") and the bot keeps them in line.
  Changes   one row per new listing, price change, status change, and so on.
  Runs      one row per source per run, so you can see the bot is alive.
"""
import csv
import json
import logging
import re
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)


class SheetError(Exception):
    """A Google Sheets problem, explained in plain words."""


_NOT_FOUND = (
    "Google can't find a sheet with that ID. Check SHEET_ID: use the sheet's link, or the part "
    "between /d/ and /edit (setup step 3)."
)


def sheet_id_from(value: str) -> str:
    """The sheet ID, given either the ID itself or the sheet's full link."""
    value = (value or "").strip()
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", value) or re.fullmatch(r"([A-Za-z0-9_-]{20,})(?:[/?#].*)?", value)
    if not match:
        raise SheetError("SHEET_ID doesn't look like a Google Sheet ID or link. Set it to the sheet's link, or the part between /d/ and /edit.")
    return match.group(1)

# (field, column header). The order here is the column order in the sheet.
COLUMNS = [
    ("status", "Status"),
    ("title", "Title"),
    ("notes", "Notes"),
    ("industry", "Industry"),
    ("category", "Category"),
    ("suburb", "Suburb"),
    ("postcode", "Postcode"),
    ("region", "Region"),
    ("perth_metro", "Perth metro"),
    ("price_text", "Asking price"),
    ("price_aud", "Price (AUD)"),
    ("price_basis", "Price basis"),
    ("turnover_aud", "Turnover (AUD/yr)"),
    ("profit_aud", "Profit (AUD/yr)"),
    ("profit_type", "Profit type"),
    ("established", "Established"),
    ("sale_reason", "Reason for sale"),
    ("broker", "Broker / seller"),
    ("broker_phone", "Broker phone"),
    ("url", "URL"),
    ("source", "Source"),
    ("listing_id", "Listing ID"),
    ("first_seen", "First seen"),
    ("last_seen", "Last seen"),
    ("last_changed", "Last changed"),
    ("sitemap_lastmod", "Site updated"),
    ("key_features", "Key features"),
    ("description", "Description"),
    ("fingerprint", "Fingerprint"),
    ("key", "Key"),
]
HEADERS = [header for _, header in COLUMNS]
NUMERIC = {"price_aud", "turnover_aud", "profit_aud"}

CHANGE_COLUMNS = [
    ("when", "When"),
    ("source", "Source"),
    ("listing_id", "Listing ID"),
    ("title", "Title"),
    ("what", "What changed"),
    ("old", "Old"),
    ("new", "New"),
    ("url", "URL"),
]
RUN_COLUMNS = [
    ("started", "Started"),
    ("source", "Source"),
    ("on_site", "Listings on site"),
    ("new", "New"),
    ("updated", "Updated"),
    ("removed", "Removed"),
    ("fetched", "Pages opened"),
    ("backlog", "Left for next run"),
    ("errors", "Errors"),
    ("result", "Result"),
]


def _row(record: dict, columns: list[tuple[str, str]]) -> list:
    return ["" if record.get(field) is None else record[field] for field, _ in columns]


def _number(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").replace("$", "")))
    except ValueError:
        return None


class LocalStore:
    """JSON + CSV files in a folder. For testing without Google credentials."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "listings.json"

    def load(self) -> dict[str, dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self, listings: dict[str, dict], changes: list[dict], runs: list[dict]) -> None:
        self.path.write_text(json.dumps(listings, indent=1, ensure_ascii=False))
        ordered = sorted(listings.values(), key=lambda l: (l.get("first_seen", ""), l.get("listing_id", "")), reverse=True)
        self._write_csv("listings.csv", COLUMNS, ordered, mode="w")
        self._write_csv("changes.csv", CHANGE_COLUMNS, changes, mode="a")
        self._write_csv("runs.csv", RUN_COLUMNS, runs, mode="a")
        log.info("Saved %d listings to %s", len(listings), self.folder)

    def _write_csv(self, name: str, columns, records, mode: str) -> None:
        path = self.folder / name
        new_file = mode == "w" or not path.exists()
        with path.open(mode, newline="") as f:
            writer = csv.writer(f)
            if new_file:
                writer.writerow([header for _, header in columns])
            writer.writerows(_row(r, columns) for r in records)


class SheetStore:
    """A Google Sheet, reached with a service account the sheet is shared with."""

    def __init__(self, sheet_id: str, credentials: dict):
        import gspread

        self._gspread = gspread
        self.service_account = credentials.get("client_email") or "the service account"
        self._row_keys: list[str] = []
        with self._explained():
            try:
                # The back-off client retries when Google says "too many requests" or has a hiccup.
                client = gspread.service_account_from_dict(credentials, http_client=gspread.BackOffHTTPClient)
            except ValueError:
                raise SheetError(
                    "GOOGLE_SERVICE_ACCOUNT_JSON isn't a complete service account key. Set it straight from the "
                    "key file: gh secret set GOOGLE_SERVICE_ACCOUNT_JSON < path/to/key.json"
                ) from None
            book = client.open_by_key(sheet_id_from(sheet_id))
            log.info("Opened Google Sheet %r", book.title)
            self.listings_ws = self._worksheet(book, "Listings", HEADERS)
            self.changes_ws = self._worksheet(book, "Changes", [h for _, h in CHANGE_COLUMNS])
            self.runs_ws = self._worksheet(book, "Runs", [h for _, h in RUN_COLUMNS])

    def load(self) -> dict[str, dict]:
        with self._explained():
            values = self.listings_ws.get_all_values(
                value_render_option=self._gspread.utils.ValueRenderOption.unformatted
            )
        if values and values[0][: len(HEADERS)] != HEADERS:
            log.warning("Listings header row differs from the bot's columns; it will be rewritten")
        listings = {}
        # Remember which listing sits on which row, so rows (and your own columns) stay in place.
        self._row_keys = []
        for cells in values[1:]:
            cells = list(cells) + [""] * (len(COLUMNS) - len(cells))
            listing = {field: cells[i] for i, (field, _) in enumerate(COLUMNS)}
            for field in listing:
                listing[field] = _number(listing[field]) if field in NUMERIC else str(listing[field])
            key = listing["key"]
            self._row_keys.append(key)
            if key:
                listings[key] = listing
        log.info("Loaded %d listings from the sheet", len(listings))
        return listings

    def save(self, listings: dict[str, dict], changes: list[dict], runs: list[dict]) -> None:
        known = set(self._row_keys)
        new_keys = sorted((k for k in listings if k not in known), key=lambda k: _number(listings[k].get("listing_id")) or 0, reverse=True)
        ws = self.listings_ws
        order = new_keys + self._row_keys
        body = [HEADERS] + [_row(listings[k], COLUMNS) if k in listings else [""] * len(COLUMNS) for k in order]
        with self._explained():
            if new_keys:
                # Insert whole rows at the top so your own columns shift down with the bot's.
                ws.insert_rows([[""]] * len(new_keys), row=2)
            if ws.col_count < len(HEADERS):
                ws.add_cols(len(HEADERS) - ws.col_count)
            ws.update(values=body, range_name="A1", value_input_option="RAW")
            if changes:
                self.changes_ws.append_rows([_row(c, CHANGE_COLUMNS) for c in changes], value_input_option="RAW")
            if runs:
                self.runs_ws.append_rows([_row(r, RUN_COLUMNS) for r in runs], value_input_option="RAW")
        self._row_keys = order
        log.info("Saved %d listings (%d new rows) and %d changes to the sheet", len(listings), len(new_keys), len(changes))

    @contextmanager
    def _explained(self):
        """Turn Google's errors (sometimes a whole HTML page) into one plain sentence."""
        from google.auth.exceptions import RefreshError, TransportError

        try:
            yield
        except self._gspread.exceptions.SpreadsheetNotFound:
            raise SheetError(_NOT_FOUND) from None
        except self._gspread.exceptions.APIError as e:
            raise SheetError(self._explain(e)) from None
        except RefreshError:
            raise SheetError(
                "Google refused the service account key; it may have been deleted or disabled. Create a new key "
                "(setup step 2) and update GOOGLE_SERVICE_ACCOUNT_JSON."
            ) from None
        except TransportError as e:
            raise SheetError(f"Couldn't reach Google ({e}). The next run will try again.") from None

    def _explain(self, error) -> str:
        message = str(error.error.get("message", ""))
        if error.code == -1:
            return (
                "Google answered with a web page instead of sheet data, which usually means SHEET_ID is wrong. "
                "Set it to the sheet's link, or the part between /d/ and /edit."
            )
        if error.code == 403 and ("has not been used" in message or "is disabled" in message):
            return "The Google Sheets API is turned off for this key's Google Cloud project. Turn it on (setup step 1), wait 5 minutes and run again."
        if error.code == 403:
            return f"The bot isn't allowed to open this sheet. Share the sheet with {self.service_account} as Editor (setup step 3)."
        if error.code == 404:
            return _NOT_FOUND
        if error.code == 429:
            return "Google's rate limit was still hit after retrying. The next run will carry on."
        return f"Google Sheets error {error.code}: {message[:300]}"

    def _worksheet(self, book, title: str, headers: list[str]):
        try:
            return book.worksheet(title)
        except self._gspread.WorksheetNotFound:
            ws = book.add_worksheet(title, rows=100, cols=len(headers))
            ws.update(values=[headers], range_name="A1", value_input_option="RAW")
            ws.freeze(rows=1)
            return ws
