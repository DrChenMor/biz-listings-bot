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
from pathlib import Path

log = logging.getLogger(__name__)

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
        book = gspread.service_account_from_dict(credentials).open_by_key(sheet_id)
        self.listings_ws = self._worksheet(book, "Listings", HEADERS)
        self.changes_ws = self._worksheet(book, "Changes", [h for _, h in CHANGE_COLUMNS])
        self.runs_ws = self._worksheet(book, "Runs", [h for _, h in RUN_COLUMNS])
        self._row_keys: list[str] = []

    def load(self) -> dict[str, dict]:
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
        if new_keys:
            # Insert whole rows at the top so your own columns shift down with the bot's.
            ws.insert_rows([[""]] * len(new_keys), row=2)
        if ws.col_count < len(HEADERS):
            ws.add_cols(len(HEADERS) - ws.col_count)
        order = new_keys + self._row_keys
        body = [HEADERS] + [_row(listings[k], COLUMNS) if k in listings else [""] * len(COLUMNS) for k in order]
        ws.update(values=body, range_name="A1", value_input_option="RAW")
        if changes:
            self.changes_ws.append_rows([_row(c, CHANGE_COLUMNS) for c in changes], value_input_option="RAW")
        if runs:
            self.runs_ws.append_rows([_row(r, RUN_COLUMNS) for r in runs], value_input_option="RAW")
        self._row_keys = order
        log.info("Saved %d listings (%d new rows) and %d changes to the sheet", len(listings), len(new_keys), len(changes))

    def _worksheet(self, book, title: str, headers: list[str]):
        try:
            return book.worksheet(title)
        except self._gspread.WorksheetNotFound:
            ws = book.add_worksheet(title, rows=100, cols=len(headers))
            ws.update(values=[headers], range_name="A1", value_input_option="RAW")
            ws.freeze(rows=1)
            return ws
