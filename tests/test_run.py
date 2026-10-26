from dataclasses import dataclass

import pytest

from bizbot import config
from bizbot.http import Blocked
from bizbot.run import sync_source


@dataclass(frozen=True)
class Entry:
    listing_id: str
    url: str
    lastmod: str


class FakeSite:
    """Stands in for a source module: a listing index plus pages, both editable by the test."""

    NAME = "fake"

    def __init__(self):
        self.index: dict[str, str] = {}  # listing id -> lastmod
        self.pages: dict[str, dict] = {}  # listing id -> fields
        self.opened: list[str] = []
        self.block_after: int | None = None

    def add(self, listing_id, lastmod, **fields):
        self.index[listing_id] = lastmod
        self.pages[listing_id] = {"title": f"Listing {listing_id}", "price_text": "$100,000", "status": "Active", **fields}

    def list_entries(self, client, cfg):
        return [Entry(i, f"https://example.test/{i}", m) for i, m in self.index.items()]

    def fetch_listing(self, client, entry, cfg):
        if self.block_after is not None and len(self.opened) >= self.block_after:
            raise Blocked("HTTP 429")
        self.opened.append(entry.listing_id)
        return dict(self.pages[entry.listing_id])


def sync(site, listings, changes, limit=100):
    return sync_source(site, config.load(), None, listings, changes, limit)


def test_new_unchanged_updated_removed_and_returning_listings():
    site, listings, changes = FakeSite(), {}, []
    site.add("1", "t1")
    site.add("2", "t1")

    stats = sync(site, listings, changes)
    assert (stats["new"], stats["fetched"]) == (2, 2)
    assert [c["what"] for c in changes] == ["New listing", "New listing"]

    # Nothing changed on the site: nothing is opened again.
    changes.clear()
    site.opened.clear()
    stats = sync(site, listings, changes)
    assert (stats["fetched"], changes) == (0, [])

    # Listing 1 is updated with a price drop; listing 2 leaves the site.
    site.add("1", "t2", price_text="$90,000")
    del site.index["2"]
    stats = sync(site, listings, changes)
    assert (stats["updated"], stats["removed"], site.opened) == (1, 1, ["1"])
    assert {(c["listing_id"], c["what"], c["old"], c["new"]) for c in changes} == {
        ("1", "Asking price", "$100,000", "$90,000"),
        ("2", "Status", "Active", "Removed"),
    }
    assert listings["fake:2"]["status"] == "Removed"

    # Listing 2 comes back with the same timestamp: it is opened again and reactivated.
    changes.clear()
    site.index["2"] = "t1"
    stats = sync(site, listings, changes)
    assert stats["updated"] == 1
    assert [(c["what"], c["old"], c["new"]) for c in changes] == [("Status", "Removed", "Active")]


def test_page_limit_leaves_a_backlog_and_newest_go_first():
    site, listings, changes = FakeSite(), {}, []
    for i in ("10", "11", "12"):
        site.add(i, "t1")
    stats = sync(site, listings, changes, limit=2)
    assert (stats["fetched"], stats["backlog"]) == (2, 1)
    assert sorted(site.opened) == ["11", "12"]


def test_a_listing_index_that_is_a_web_page_is_skipped_not_a_crash():
    import httpx

    from bizbot.http import Unavailable, parse_xml

    busy = httpx.Response(200, text="<html><head><title>Server busy</title></head><body><p>try later</body></html>")
    with pytest.raises(Unavailable, match="Server busy"):
        parse_xml(busy, "bsale's listing index")

    class BusySite(FakeSite):
        def list_entries(self, client, cfg):
            parse_xml(busy, "bsale's listing index")

    listings = {"fake:1": {"key": "fake:1", "source": "fake", "status": "Active"}}
    stats = sync(BusySite(), listings, [])
    assert stats["result"].startswith("listing index unavailable")
    assert listings["fake:1"]["status"] == "Active"  # nothing marked removed


def test_food_businesses_are_skipped_remembered_and_removed_from_the_sheet():
    site, listings, changes, skipped = FakeSite(), {}, [], {}
    site.add("1", "t1", category="Hair Salon", industry="Beauty and Health")
    site.add("2", "t1", category="Cafe, Restaurant", industry="Food Hospitality")
    cfg = config.load()
    stats = sync_source(site, cfg, None, listings, changes, 100, skipped)
    assert set(listings) == {"fake:1"}
    assert set(skipped) == {"fake:2"} and skipped["fake:2"]["reason"] == "Excluded category (food): Cafe, Restaurant"
    assert stats["skipped"] == 1

    # Not opened again while the site hasn't updated it.
    site.opened.clear()
    sync_source(site, cfg, None, listings, changes, 100, skipped)
    assert site.opened == []

    # A food listing collected before the rule existed leaves the sheet on the next run.
    listings["fake:3"] = {"key": "fake:3", "source": "fake", "category": "Bakery", "sitemap_lastmod": "t1", "status": "Active"}
    site.add("3", "t1", category="Bakery")
    sync_source(site, cfg, None, listings, changes, 100, skipped)
    assert "fake:3" not in listings and "fake:3" in skipped
    assert site.opened == []


def test_sold_listings_are_skipped_and_a_listing_that_sells_is_logged():
    site, listings, changes, skipped = FakeSite(), {}, [], {}
    site.add("1", "t1", price_text="SOLD", status="Sold")
    site.add("2", "t1", price_text="$90,000")
    cfg = config.load()
    sync_source(site, cfg, None, listings, changes, 100, skipped)
    assert set(listings) == {"fake:2"} and skipped["fake:1"]["reason"] == "Sold"

    # Listing 2 sells later: a line in Changes, then it moves to Skipped.
    changes.clear()
    site.add("2", "t2", price_text="SOLD", status="Sold")
    sync_source(site, cfg, None, listings, changes, 100, skipped)
    assert "fake:2" not in listings and skipped["fake:2"]["reason"] == "Sold"
    assert [(c["what"], c["old"], c["new"]) for c in changes] == [("Status", "Active", "Sold (moved to Skipped)")]


def test_rows_wrongly_marked_sold_earlier_are_corrected_not_skipped():
    site, changes, skipped = FakeSite(), [], {}
    site.add("1", "t1", title="New franchise", price_text="Intro offer, first 10 locations sold")
    site.add("2", "t1", title="Nails Salon", price_text="SOLD")
    listings = {
        "fake:1": {"key": "fake:1", "source": "fake", "title": "New franchise", "price_text": "Intro offer, first 10 locations sold", "status": "Sold", "sitemap_lastmod": "t1"},
        "fake:2": {"key": "fake:2", "source": "fake", "title": "Nails Salon", "price_text": "SOLD", "status": "Sold", "sitemap_lastmod": "t1"},
    }
    sync_source(site, config.load(), None, listings, changes, 100, skipped)
    assert listings["fake:1"]["status"] == "Active"
    assert set(skipped) == {"fake:2"}
    assert site.opened == []  # nothing needed re-opening


def test_exclusion_matches_whole_words_only():
    cfg = config.load()
    assert cfg.excluded("Pubs, Bars & Clubs")
    assert cfg.excluded("Food & Drink > Coffee, Cafes & Restaurants")
    assert not cfg.excluded("Barber", "Health, Beauty & Fitness > Hair, Beauty & Spa")
    assert not cfg.excluded("Beauty and Health", "Hair Salon")


def test_each_site_writes_only_its_own_tab(tmp_path, monkeypatch):
    from bizbot import run as run_module
    from bizbot.store import COLUMNS, LISTINGS, LocalStore, Table

    other_tab = Table("Other listings", COLUMNS)
    main_site, mac_site = FakeSite(), FakeSite()
    main_site.NAME, mac_site.NAME, mac_site.TABLE = "main", "mac", other_tab
    main_site.add("1", "t1")
    mac_site.add("2", "t1")
    monkeypatch.setitem(run_module.SOURCES, "main", main_site)
    monkeypatch.setitem(run_module.SOURCES, "mac", mac_site)
    store, cfg = LocalStore(tmp_path), config.load()

    cfg.sources = ["mac"]
    run_module.run(cfg, store, limit=10)
    assert set(store.load(other_tab)) == {"mac:2"}
    assert not (tmp_path / "listings.json").exists() and not (tmp_path / "skipped.json").exists()

    cfg.sources = ["main"]
    run_module.run(cfg, store, limit=10)
    assert set(store.load(LISTINGS)) == {"main:1"}
    assert (tmp_path / "skipped.json").exists()


def test_blocking_stops_the_source_and_keeps_what_was_collected():
    site, listings, changes = FakeSite(), {}, []
    for i in ("1", "2", "3"):
        site.add(i, "t1")
    site.block_after = 1
    stats = sync(site, listings, changes)
    assert stats["result"].startswith("blocked after 1 pages")
    assert (stats["fetched"], stats["backlog"], len(listings)) == (1, 2, 1)
