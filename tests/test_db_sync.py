from bizbot import config, db_sync


def test_a_listing_gets_its_route_type_and_only_a_believable_profit():
    row = db_sync.sale_row(config.load(), {
        "key": "anybusiness:1", "title": "Hair Salon", "industry": "Hair Salon", "category": "", "suburb": "Morley", "postcode": "6062", "perth_metro": "Yes",
        "broker": "Private Seller: Sam", "turnover_aud": 300_000, "profit_aud": 300_000, "price_aud": 95_000, "price_text": "$95,000", "first_seen": "2026-10-31 18:47",
    }, "anybusiness")
    assert (row["route"], row["site"], row["perth"], row["profit"]) == ("Private seller", "AnyBusiness", True, None)
    assert row["types"] == ["Beauty and hair"] and row["first_seen"] == "2026-10-31T18:47:00+08:00"
    assert {"label": "Asking price", "value": "$95,000", "source": "AnyBusiness", "date": "2026-10-31"} in row["facts"]


def test_listings_without_a_postcode_count_as_perth_from_their_region():
    row = db_sync.sale_row(config.load(), {"key": "business2sell:1", "title": "Shop", "region": "Perth", "broker": ""}, "business2sell")
    assert row["perth"] is True and row["route"] == "Site enquiry"


def test_a_pharmacy_is_flagged_and_a_practice_is_not_scored_yet():
    cfg = config.load()
    pharmacy = db_sync.practice_row(cfg, {"key": "hd:1", "name": "Bicton Pharmacy", "sector": "Pharmacy", "postcode": "6157", "map": "https://maps.example"})
    dentist = db_sync.practice_row(cfg, {"key": "hd:2", "name": "Albany Dental", "sector": "Dental", "postcode": "6330"})
    assert (pharmacy["route"], pharmacy["perth"], pharmacy["map_url"]) == ("Needs a pharmacist", True, "https://maps.example")
    assert (dentist["route"], dentist["perth"]) == ("Not scored yet", False)


def test_every_row_sends_the_same_columns():
    cfg = config.load()
    rows = [db_sync.sale_row(cfg, {"key": "a:1"}, "bsale"), db_sync.seek_row({"key": "seek:1"}), db_sync.practice_row(cfg, {"key": "hd:1"})]
    assert rows[0].keys() == rows[1].keys() == rows[2].keys()


def test_seek_price_of_one_dollar_is_not_a_price():
    assert db_sync.seek_row({"key": "seek:1", "price_aud": 1})["price"] is None


def listing(id, site, name, price=None, suburb="", first_seen="2026-11-01T08:00:00+08:00"):
    return {"id": id, "kind": "sale", "status": "Active", "site": site, "name": name, "price": price, "suburb": suburb,
            "first_seen": first_seen, "url": f"https://{site}/{id}", "tags": [f"On {site}"]}


def test_the_same_listing_on_two_sites_is_shown_once():
    rows = [listing("bsale:1", "bsale", "Turnkey Carpet Cleaning Business For Sale", 59000, first_seen="2026-11-02T08:00:00+08:00"),
            listing("cre:1", "commercialrealestate.com.au", "Turnkey carpet cleaning business for sale", 59000)]
    db_sync.mark_copies(rows, set())
    assert rows[0]["same_as"] == "cre:1" and rows[1]["same_as"] is None
    assert rows[1]["also_on"] == [{"site": "bsale", "url": "https://bsale/bsale:1", "id": "bsale:1", "where": ""}]
    assert "Also on bsale" in rows[1]["tags"]


def test_a_business_in_the_pipeline_is_the_one_shown():
    rows = [listing("bsale:1", "bsale", "Turnkey Carpet Cleaning", 59000), listing("b2s:1", "business2sell", "Turnkey Carpet Cleaning", 59000, first_seen="2026-11-05T08:00:00+08:00")]
    assert db_sync.same_business(rows, {"b2s:1"}) == {"bsale:1": "b2s:1"}


def test_different_listing_numbers_are_different_businesses():
    rows = [listing("seek:1", "SEEK Business", "36477 Established Beauty Clinic", 250000), listing("bsale:1", "bsale", "36662 Established Beauty Clinic", 250000)]
    assert db_sync.same_business(rows, set()) == {}


def test_the_same_listing_number_is_the_same_business_even_with_another_title():
    rows = [listing("bsale:1", "bsale", "37081 - Agritourism Booking Platform With National Reach"), listing("cre:1", "commercialrealestate.com.au", "37081 - Agritourism Booking Platform, National")]
    assert db_sync.same_business(rows, set()) == {"cre:1": "bsale:1"}


def test_a_different_price_is_a_different_business():
    rows = [listing("bsale:1", "bsale", "Established Hair Salon", 90000), listing("b2s:1", "business2sell", "Established Hair Salon", 150000)]
    assert db_sync.same_business(rows, set()) == {}


def test_franchise_towns_at_one_price_are_shown_once():
    rows = [listing("bsale:1", "bsale", "Black Optix Tint Franchise", 200000, "Joondalup"), listing("bsale:2", "bsale", "Black Optix Tint Franchise", 200000, "Rockingham"),
            listing("b2s:1", "business2sell", "Black Optix Tint Franchise", 200000, "Rockingham", "2026-11-03T08:00:00+08:00")]
    assert db_sync.same_business(rows, set()) == {"bsale:2": "bsale:1", "b2s:1": "bsale:1"}


def test_an_ad_posted_again_on_one_site_is_shown_once():
    rows = [listing(f"b2s:3340{n}", "business2sell", "Growing home based service business in Garden Maintenance", 92000, "Morley") for n in range(19, 24)]
    db_sync.mark_copies(rows, set())
    assert [r["same_as"] for r in rows] == [None] + ["b2s:334019"] * 4
    assert len(rows[0]["also_on"]) == 4 and rows[0]["also_on"][0]["where"] == "Morley"
    assert "Posted more than once" in rows[0]["tags"] and not any(t.startswith("Also on") for t in rows[0]["tags"])


def test_one_site_with_the_same_title_at_another_price_is_another_business():
    rows = [listing("bsale:1", "bsale", "Chem-dry Carpet Cleaning Franchise", 24900, "Bunbury"), listing("bsale:2", "bsale", "Chem-dry Carpet Cleaning Franchise", 185000, "Perth")]
    assert db_sync.same_business(rows, set()) == {}


def test_a_group_never_holds_two_listings_from_one_site():
    rows = [listing("cre:1", "commercialrealestate.com.au", "Fully Promoted Franchise Opportunity", 170000),
            listing("bsale:1", "bsale", "Exclusive Fully Promoted Franchise Opportunity", 170000, first_seen="2026-11-02T08:00:00+08:00"),
            listing("bsale:2", "bsale", "Fully Promoted Franchise Opportunity Premium", 170000, first_seen="2026-11-02T08:00:00+08:00")]
    copies = db_sync.same_business(rows, set())
    assert len(copies) == 1 and set(copies.values()) == {"cre:1"}


def test_a_price_drop_is_noted_and_kept():
    rows = [{"id": "bsale:1", "price": 400000, "status": "Active"}, {"id": "bsale:2", "price": 299000, "status": "Active"},
            {"id": "bsale:3", "price": 500000, "status": "Active"}]
    existing = {"bsale:1": {"price": 450000, "status": "Active"}, "bsale:2": {"price": 300000, "status": "Active"},
                "bsale:3": {"price": 500000, "status": "Active", "previous_price": 600000, "price_dropped_at": "2026-11-01"}}
    db_sync.note_changes(rows, existing, "2026-11-27T12:00:00+00:00")
    assert (rows[0]["previous_price"], rows[0]["price_dropped_at"]) == (450000, "2026-11-27T12:00:00+00:00")
    assert rows[1]["price_dropped_at"] is None  # $1,000 less is not a drop
    assert (rows[2]["previous_price"], rows[2]["price_dropped_at"]) == (600000, "2026-11-01")  # an earlier drop stays


def test_a_listing_ending_now_gets_a_date_but_old_ones_do_not():
    rows = [{"id": "a", "status": "Removed"}, {"id": "b", "status": "Removed"}, {"id": "c", "status": "Removed"}, {"id": "d", "status": "Active"}]
    existing = {"a": {"status": "Active"}, "b": {"status": "Removed"}, "c": {"status": "Removed", "ended_at": "2026-11-20"},
                "d": {"status": "Removed", "ended_at": "2026-11-20"}}
    db_sync.note_changes(rows, existing, "now")
    assert [r["ended_at"] for r in rows] == ["now", None, "2026-11-20", None]
