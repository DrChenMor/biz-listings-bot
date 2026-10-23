import json

import gspread
import pytest

from bizbot.store import HEADERS, LISTINGS, SheetError, SheetStore, sheet_id_from

SHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcd"


class FakeSpreadsheet:
    def __init__(self, ws):
        self.ws = ws

    def batch_update(self, body):
        for request in body["requests"]:
            r = request["deleteDimension"]["range"]
            assert r["dimension"] == "ROWS"
            del self.ws.grid[r["startIndex"]: r["endIndex"]]


class FakeWorksheet:
    """In-memory grid with the few gspread methods SheetStore uses."""

    def __init__(self, grid=None):
        self.grid = grid or []
        self.col_count = len(HEADERS)
        self.id = 0
        self.spreadsheet = FakeSpreadsheet(self)

    def get_all_values(self, value_render_option=None):
        rows = [list(r) for r in self.grid]
        while rows and not any(str(c) for c in rows[-1]):
            rows.pop()
        width = max((len(r) for r in rows), default=0)
        return [r + [""] * (width - len(r)) for r in rows]

    def insert_rows(self, values, row=1, value_input_option=None):
        for i, v in enumerate(values):
            self.grid.insert(row - 1 + i, list(v))

    def add_cols(self, n):
        self.col_count += n

    def update(self, values, range_name="A1", value_input_option=None):
        assert range_name == "A1"
        for r, vals in enumerate(values):
            while len(self.grid) <= r:
                self.grid.append([])
            row = self.grid[r]
            row.extend([""] * (len(vals) - len(row)))
            row[: len(vals)] = vals

    def append_rows(self, values, value_input_option=None):
        self.grid.extend(list(v) for v in values)


def make_store():
    store = SheetStore.__new__(SheetStore)
    store._gspread = gspread
    store._worksheets = {"Listings": FakeWorksheet([list(HEADERS)]), "Changes": FakeWorksheet(), "Runs": FakeWorksheet()}
    store._row_keys = {}
    return store


def listing(i, price=100_000):
    return {"key": f"bsale:{i}", "source": "bsale", "listing_id": str(i), "title": f"Business {i}", "price_aud": price, "status": "Active"}


def test_new_rows_go_on_top_and_your_own_columns_stay_with_their_listing():
    store = make_store()
    assert store.load(LISTINGS) == {}
    store.save(LISTINGS, {"bsale:1": listing(1), "bsale:2": listing(2)})
    grid = store._worksheets["Listings"].grid
    title = HEADERS.index("Title")
    assert [row[title] for row in grid[1:]] == ["Business 2", "Business 1"]

    # You add a "Contacted?" column and mark Business 1.
    grid[0].append("Contacted?")
    grid[2].append("yes")

    listings = store.load(LISTINGS)
    assert listings["bsale:1"]["price_aud"] == 100_000  # numbers come back as numbers
    listings["bsale:3"] = listing(3)
    listings["bsale:1"]["price_aud"] = 90_000
    store.save(LISTINGS, listings)
    store.log([{"when": "now", "what": "Asking price"}], [{"source": "bsale", "result": "ok"}])

    rows = {row[title]: row for row in store._worksheets["Listings"].grid[1:]}
    assert [row[title] for row in store._worksheets["Listings"].grid[1:]] == ["Business 3", "Business 2", "Business 1"]
    assert rows["Business 1"][len(HEADERS)] == "yes"
    assert rows["Business 1"][HEADERS.index("Price (AUD)")] == 90_000
    assert len(store._worksheets["Changes"].grid) == 1 and len(store._worksheets["Runs"].grid) == 1


def test_dropped_records_are_deleted_with_your_columns_and_the_rest_stay_aligned():
    store = make_store()
    store.load(LISTINGS)
    store.save(LISTINGS, {f"bsale:{i}": listing(i) for i in (1, 2, 3, 4)})
    grid = store._worksheets["Listings"].grid
    title = HEADERS.index("Title")
    grid[0].append("Contacted?")
    for row in grid[1:]:
        row.append("note for " + row[title])

    records = store.load(LISTINGS)
    del records["bsale:3"], records["bsale:1"]  # e.g. food businesses
    store.save(LISTINGS, records)

    rows = store._worksheets["Listings"].grid[1:]
    assert [(r[title], r[len(HEADERS)]) for r in rows] == [("Business 4", "note for Business 4"), ("Business 2", "note for Business 2")]


@pytest.mark.parametrize(
    "value",
    [
        SHEET_ID,
        f"  {SHEET_ID}\n",
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0",
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?usp=sharing",
        f"{SHEET_ID}/edit#gid=0",
    ],
)
def test_sheet_id_accepts_the_id_or_the_whole_link(value):
    assert sheet_id_from(value) == SHEET_ID


def test_sheet_id_rejects_anything_else():
    with pytest.raises(SheetError):
        sheet_id_from("my sheet")


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not JSON")
        return self._body


def explain(status, body):
    store = make_store()
    store.service_account = "bot@listings-bot.iam.gserviceaccount.com"
    with pytest.raises(SheetError) as caught, store._explained():
        raise gspread.exceptions.APIError(FakeResponse(status, body))
    return str(caught.value)


def google_error(code, message):
    return {"error": {"code": code, "message": message, "status": "X"}}


def test_google_errors_become_one_plain_sentence():
    assert "web page instead of sheet data" in explain(404, "<!DOCTYPE html><html>Page Not Found</html>")
    assert "turned off" in explain(403, google_error(403, "Google Sheets API has not been used in project 1 before or it is disabled."))
    assert "Share the sheet with bot@listings-bot.iam.gserviceaccount.com" in explain(403, google_error(403, "The caller does not have permission"))
    assert "can't find a sheet" in explain(404, google_error(404, "Requested entity was not found."))
    assert explain(500, google_error(500, "Internal error")) == "Google Sheets error 500: Internal error"
