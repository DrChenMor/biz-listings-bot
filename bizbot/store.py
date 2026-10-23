"""Where the bot's data lives: a Google Sheet for real runs, or local files for testing.

Each kind of record has its own tab (Listings, Health businesses, ...). Two shared tabs log activity:
  Changes   one row per new record and per change (price, status, owner, ...).
  Runs      one row per source per run, so you can see the bot is alive.

On a record tab the bot owns the columns from A to the "Key" column. Add your own columns to the
right of those (e.g. "Contacted?") and the bot keeps them lined up with the right row.
"""
import csv
import json
import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Table:
    """One tab of records: its name, its (field, column header) pairs, and which fields are numbers."""

    tab: str
    columns: list[tuple[str, str]]
    numeric: frozenset[str] = frozenset()

    @property
    def headers(self) -> list[str]:
        return [header for _, header in self.columns]


# The order here is the column order in the sheet.
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
LISTINGS = Table("Listings", COLUMNS, frozenset({"price_aud", "turnover_aud", "profit_aud"}))
HEADERS = LISTINGS.headers

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


def _row(record: dict, columns: list[tuple[str, str]]) -> list:
    return ["" if record.get(field) is None else record[field] for field, _ in columns]


def _number(value) -> int | float | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", "").replace("$", ""))
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


class LocalStore:
    """JSON + CSV files in a folder. For testing without Google credentials."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)

    def load(self, table: Table) -> dict[str, dict]:
        path = self._path(table, ".json")
        return json.loads(path.read_text()) if path.exists() else {}

    def save(self, table: Table, records: dict[str, dict]) -> None:
        self._path(table, ".json").write_text(json.dumps(records, indent=1, ensure_ascii=False))
        ordered = sorted(records.values(), key=lambda r: (r.get("first_seen", ""), r.get("key", "")), reverse=True)
        self._write_csv(self._path(table, ".csv"), table.columns, ordered, mode="w")
        log.info("Saved %d rows to %s", len(records), self._path(table, ".csv"))

    def log(self, changes: list[dict], runs: list[dict]) -> None:
        self._write_csv(self.folder / "changes.csv", CHANGE_COLUMNS, changes, mode="a")
        self._write_csv(self.folder / "runs.csv", RUN_COLUMNS, runs, mode="a")

    def _path(self, table: Table, suffix: str) -> Path:
        return self.folder / (re.sub(r"[^a-z0-9]+", "-", table.tab.lower()).strip("-") + suffix)

    @staticmethod
    def _write_csv(path: Path, columns, records, mode: str) -> None:
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
        self._worksheets: dict[str, object] = {}
        # Which record sits on which row of each tab, so rows (and your own columns) stay in place.
        self._row_keys: dict[str, list[str]] = {}
        with self._explained():
            try:
                # The back-off client retries when Google says "too many requests" or has a hiccup.
                client = gspread.service_account_from_dict(credentials, http_client=gspread.BackOffHTTPClient)
            except ValueError:
                raise SheetError(
                    "GOOGLE_SERVICE_ACCOUNT_JSON isn't a complete service account key. Set it straight from the "
                    "key file: gh secret set GOOGLE_SERVICE_ACCOUNT_JSON < path/to/key.json"
                ) from None
            self.book = client.open_by_key(sheet_id_from(sheet_id))
            log.info("Opened Google Sheet %r", self.book.title)

    def load(self, table: Table) -> dict[str, dict]:
        with self._explained():
            values = self._worksheet(table.tab, table.headers).get_all_values(
                value_render_option=self._gspread.utils.ValueRenderOption.unformatted
            )
        if values and values[0][: len(table.columns)] != table.headers:
            log.warning("%s header row differs from the bot's columns; it will be rewritten", table.tab)
        records = {}
        row_keys = []
        for cells in values[1:]:
            cells = list(cells) + [""] * (len(table.columns) - len(cells))
            record = {field: cells[i] for i, (field, _) in enumerate(table.columns)}
            for field in record:
                record[field] = _number(record[field]) if field in table.numeric else str(record[field])
            row_keys.append(record["key"])
            if record["key"]:
                records[record["key"]] = record
        self._row_keys[table.tab] = row_keys
        log.info("Loaded %d rows from the %s tab", len(records), table.tab)
        return records

    def save(self, table: Table, records: dict[str, dict]) -> None:
        row_keys = self._row_keys.get(table.tab, [])
        known = set(row_keys)
        new_keys = sorted((k for k in records if k not in known), key=lambda k: (records[k].get("first_seen", ""), k), reverse=True)
        order = new_keys + row_keys
        body = [table.headers] + [_row(records[k], table.columns) if k in records else [""] * len(table.columns) for k in order]
        ws = self._worksheet(table.tab, table.headers)
        with self._explained():
            if new_keys:
                # Insert whole rows at the top so your own columns shift down with the bot's.
                ws.insert_rows([[""]] * len(new_keys), row=2)
            if ws.col_count < len(table.columns):
                ws.add_cols(len(table.columns) - ws.col_count)
            ws.update(values=body, range_name="A1", value_input_option="RAW")
        self._row_keys[table.tab] = order
        log.info("Saved %d rows (%d new) to the %s tab", len(records), len(new_keys), table.tab)

    def log(self, changes: list[dict], runs: list[dict]) -> None:
        with self._explained():
            if changes:
                ws = self._worksheet("Changes", [h for _, h in CHANGE_COLUMNS])
                ws.append_rows([_row(c, CHANGE_COLUMNS) for c in changes], value_input_option="RAW")
            if runs:
                ws = self._worksheet("Runs", [h for _, h in RUN_COLUMNS])
                ws.append_rows([_row(r, RUN_COLUMNS) for r in runs], value_input_option="RAW")

    def _worksheet(self, title: str, headers: list[str]):
        if title in self._worksheets:
            return self._worksheets[title]
        with self._explained():
            try:
                ws = self.book.worksheet(title)
            except self._gspread.WorksheetNotFound:
                ws = self.book.add_worksheet(title, rows=100, cols=len(headers))
                ws.update(values=[headers], range_name="A1", value_input_option="RAW")
                ws.freeze(rows=1)
        self._worksheets[title] = ws
        return ws

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
