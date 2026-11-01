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
