import gspread

from bizbot.store import HEADERS, SheetStore


class FakeWorksheet:
    """In-memory grid with the few gspread methods SheetStore uses."""

    def __init__(self, grid=None):
        self.grid = grid or []
        self.col_count = len(HEADERS)

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
    store.listings_ws, store.changes_ws, store.runs_ws = FakeWorksheet([list(HEADERS)]), FakeWorksheet(), FakeWorksheet()
    store._row_keys = []
    return store


def listing(i, price=100_000):
    return {"key": f"bsale:{i}", "source": "bsale", "listing_id": str(i), "title": f"Business {i}", "price_aud": price, "status": "Active"}


def test_new_rows_go_on_top_and_your_own_columns_stay_with_their_listing():
    store = make_store()
    assert store.load() == {}
    store.save({"bsale:1": listing(1), "bsale:2": listing(2)}, [], [])
    grid = store.listings_ws.grid
    title = HEADERS.index("Title")
    assert [row[title] for row in grid[1:]] == ["Business 2", "Business 1"]

    # You add a "Contacted?" column and mark Business 1.
    grid[0].append("Contacted?")
    grid[2].append("yes")

    listings = store.load()
    assert listings["bsale:1"]["price_aud"] == 100_000  # numbers come back as numbers
    listings["bsale:3"] = listing(3)
    listings["bsale:1"]["price_aud"] = 90_000
    store.save(listings, [{"when": "now", "what": "Asking price"}], [{"source": "bsale", "result": "ok"}])

    rows = {row[title]: row for row in store.listings_ws.grid[1:]}
    assert [row[title] for row in store.listings_ws.grid[1:]] == ["Business 3", "Business 2", "Business 1"]
    assert rows["Business 1"][len(HEADERS)] == "yes"
    assert rows["Business 1"][HEADERS.index("Price (AUD)")] == 90_000
    assert len(store.changes_ws.grid) == 1 and len(store.runs_ws.grid) == 1
