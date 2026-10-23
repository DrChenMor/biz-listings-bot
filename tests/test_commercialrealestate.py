import json
from types import SimpleNamespace

import pytest

from bizbot import config
from bizbot.http import Unavailable
from bizbot.sources import commercialrealestate as cre

BASE = "https://www.commercialrealestate.com.au"


def card(ad_id, headline, category="Cleaning & Maintenance", price="59,000", state="WA", **over):
    return {
        "adID": ad_id, "seoUrl": f"/business-for-sale/listing-{ad_id}", "headline": headline, "shortDescription": "Short.",
        "suburb": "Perth", "state": state, "postcode": "6000", "region": "Perth Metropolitan - Central Suburbs",
        "displayablePrice": price, "mainCategory": category, "statusFlag": "New",
        "propertyTypeDetails": [{"name": category}], **over,
    }


def page(cards, pages=1, total=None):
    data = {"searchListings": {"totalPages": pages, "totalItemsCount": total if total is not None else len(cards), "pagedSearchResults": cards}}
    return SimpleNamespace(status_code=200, text=f'<script id="__NEXT_DATA__">{json.dumps({"props": {"pageProps": {"data": data}}})}</script>')


class FakeClient:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, **_):
        return self.pages[url]


def test_reads_every_results_page_and_leaves_food_out():
    cleaning, cafe, salon = card(1, "Carpet cleaning"), card(2, "Busy cafe", "Cafe & Coffee Shop"), card(3, "Hair salon", "Hairdresser")
    client = FakeClient({
        f"{BASE}/business-for-sale/wa/": page([cleaning, cafe], pages=2, total=3),
        f"{BASE}/business-for-sale/wa/?pn=2": page([salon, cleaning], pages=2, total=3),
    })
    entries = cre.list_entries(client, config.load())
    assert [e.listing_id for e in entries] == ["1", "3"]  # cafe skipped, repeat of 1 ignored
    assert entries[0].url == f"{BASE}/business-for-sale/listing-1"


def test_a_short_read_is_an_error_not_a_wave_of_removals():
    client = FakeClient({f"{BASE}/business-for-sale/wa/": page([card(1, "Carpet cleaning")], pages=1, total=50)})
    with pytest.raises(Unavailable, match="1 of 50"):
        cre.list_entries(client, config.load())


def test_card_change_changes_the_fingerprint():
    a = cre._fingerprint(card(1, "Carpet cleaning"))
    assert a == cre._fingerprint(card(1, "Carpet cleaning"))
    assert a != cre._fingerprint(card(1, "Carpet cleaning", price="49,000"))
    assert a != cre._fingerprint(card(1, "Carpet cleaning", statusFlag="Under Offer"))


def test_listing_page_fields():
    listing = {
        "adID": 2021271227, "headline": "Turnkey carpet cleaning business for sale with van",
        "description": "Chem-Dry franchise. Turnover $250,000 p.a. and net profit $95,000. Established since 2012. Owner retiring.\nCall 0400 111 222.",
        "displayablePrice": "59,000", "priceData": None, "suburb": "Perth", "state": "WA", "postcode": "6000",
        "mainCategory": "Cleaning & Maintenance", "isFranchise": True,
        "propertyTypeDetails": [{"name": "Cleaning & Maintenance"}, {"name": "Franchise Business"}],
        "agency": {"agencyName": "Johnston Business Sales", "generalPhoneNumber": "1300 88 9443",
                   "agents": [{"fullName": "JBS ", "telephone": "1300 889 443", "mobile": ""}]},
    }
    row = cre.parse_listing(listing, card(2021271227, "x", statusFlag="Under Offer"), config.load())
    assert (row["price_text"], row["price_aud"]) == ("$59,000", 59_000)
    assert (row["industry"], row["category"]) == ("Cleaning & Maintenance", "Cleaning & Maintenance, Franchise Business")
    assert (row["suburb"], row["postcode"], row["perth_metro"], row["region"]) == ("Perth", "6000", "Yes", "Perth Metropolitan - Central Suburbs")
    assert (row["turnover_aud"], row["profit_aud"], row["established"], row["sale_reason"]) == (250_000, 95_000, "2012", "Retirement")
    assert row["broker"] == "JBS / Johnston Business Sales"
    assert row["broker_phone"] == "1300 889 443; 0400 111 222"  # the agency number is the same as JBS's
    assert row["status"] == "Under offer"
    assert row["key_features"] == "Franchise"
