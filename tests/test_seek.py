from bizbot import config, seek


def raw(**over):
    return {
        "id": "794248",
        "url": "https://www.seekbusiness.com.au/business-listing/mount-pleasant-stunning-hair-salon-for-sale/794248",
        "title": "Mount Pleasant Stunning Hair Salon for Sale",
        "advertiser": "Benchmark Business Sales and Valuations",
        "location": "Perth - Greater, Mount Pleasant, WA 6153",
        "industry": "Health, Beauty & Fitness > Hair, Beauty & Spa",
        "price_text": "$87,000 + SAV",
        "price_min": 87000,
        "opportunity_type": "Business",
        "summary": "Established 23+ years, this salon delivers $13K weekly sales and ~$160K net profit.",
        "refreshed": "2026-10-23T03:31:33.370Z",
        **over,
    }


def stats():
    return dict(new=0, updated=0, skipped=0)


def test_normalise_matches_the_bookmark_rules():
    row = seek.normalise(raw(), "2026-10-23 15:00")
    assert row["key"] == "seek:794248"
    assert (row["price_aud"], row["price_basis"]) == (87000, "+ stock (SAV)")
    assert (row["turnover_aud"], row["profit_aud"]) == (13000 * 52, 160000)
    assert row["seek_updated"] == "2026-10-23 11:31"  # Perth time
    assert seek.SEEK.headers[-1] == "Key"


def test_same_columns_as_the_apps_script():
    source = (config.ROOT / "seek" / "SaveToSheet.gs").read_text()
    for field, header in seek.SEEK.columns:
        assert f'["{field}", "{header}"]' in source


def test_listing_page_adds_description_and_results_page_keeps_it():
    rows, changes, counts = {}, [], stats()
    seek.merge(rows, seek.normalise(raw(), "t1"), "t1", changes, counts)
    detail = raw(description="Contact John Kasapi M: 0422 930 549 T: 1300 366 521")
    seek.merge(rows, seek.normalise(detail, "t1"), "t1", changes, counts)
    seek.merge(rows, seek.normalise(raw(), "t2"), "t2", changes, counts)
    row = rows["seek:794248"]
    assert row["phones"] == "0422 930 549; 1300 366 521"
    assert "John Kasapi" in row["description"]
    assert counts == {"new": 1, "updated": 0, "skipped": 0}
    assert [c["what"] for c in changes] == ["New listing"]


def test_price_drop_and_under_offer_are_logged():
    rows, changes, counts = {}, [], stats()
    seek.merge(rows, seek.normalise(raw(), "t1"), "t1", changes, counts)
    changes.clear()
    seek.merge(rows, seek.normalise(raw(title="UNDER OFFER Mount Pleasant Salon", price_text="$79,000 + SAV", price_min=79000), "t2"), "t2", changes, counts)
    assert [(c["what"], c["old"], c["new"]) for c in changes] == [
        ("Status", "Active", "Under offer"),
        ("Title", "Mount Pleasant Stunning Hair Salon for Sale", "UNDER OFFER Mount Pleasant Salon"),
        ("Asking price", "$87,000 + SAV", "$79,000 + SAV"),
    ]
    assert rows["seek:794248"]["last_changed"] == "t2"


def test_food_listings_are_skipped():
    cfg, rows, counts = config.load(), {}, stats()
    seek._save(cfg, rows, raw(id="1", industry="Food & Drink > Coffee, Cafes & Restaurants > Cafe"), "t", [], counts)
    assert rows == {} and counts["skipped"] == 1


def test_page_urls_and_reader_code():
    search = "https://www.seekbusiness.com.au/businesses-for-sale/within-health-beauty-fitness-or-personal-services/in-perth-wa?rad=50&sort=1"
    assert seek._page_url(search, 1) == search
    assert seek._page_url(search, 3).endswith("?rad=50&sort=1&pg=3")
    source = seek.bookmarklet_source()
    assert source.startswith("function seekBookmarklet(") and source.rstrip().endswith("}")


class Page:
    """Just enough of a browser page for recheck."""

    def __init__(self, status, title):
        self.status, self._title = status, title

    def goto(self, url, **kwargs):
        return type("Response", (), {"status": self.status})()

    def wait_for_timeout(self, ms):
        pass

    def title(self):
        return self._title


def rechecked(status, title):
    row, changes, counts = {"key": "seek:1", "url": "https://seek.example/1", "status": "Active", "last_seen": "2026-11-01 08:00"}, [], dict(removed=0, fetched=0)
    seek.recheck(Page(status, title), row, "2026-11-18 09:00", changes, counts)
    return row, changes, counts


def test_a_listing_seek_no_longer_has_is_marked_removed():
    row, changes, counts = rechecked(404, "Page Not Found")
    assert row["status"] == "Removed" and counts["removed"] == 1 and changes


def test_a_live_listing_is_marked_as_seen():
    row, changes, counts = rechecked(200, "Hair Salon in Perth - SEEK Business")
    assert (row["status"], row["last_seen"], changes) == ("Active", "2026-11-18 09:00", [])


def test_a_security_check_stops_the_recheck():
    import pytest
    with pytest.raises(seek.SecurityCheck):
        rechecked(403, "Just a moment...")
