"""commercialrealestate.com.au (run by Domain): businesses for sale in one state.

The state's results pages (/business-for-sale/wa/?pn=2 ...; 20 listings each) carry every listing's data in the
page. The bot reads all of them each run, then opens a listing's own page only when the listing is new or its
card changed (headline, price, status or summary), for the full description and the agents' phone numbers.
Food businesses are left out from the cards, so their pages are never opened.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field

from .. import extract
from ..config import Config
from ..http import PoliteClient, Unavailable

NAME = "commercialrealestate"
BASE = "https://www.commercialrealestate.com.au"

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


@dataclass
class Entry:
    listing_id: str
    url: str
    lastmod: str  # a fingerprint of the results card: it changes when the listing does
    card: dict = field(repr=False)


def list_entries(client: PoliteClient, cfg: Config) -> list[Entry]:
    entries: dict[str, Entry] = {}
    seen = 0
    number, pages, expected = 1, 1, 0
    while number <= pages:
        url = f"{BASE}/business-for-sale/{cfg.state}/" + (f"?pn={number}" if number > 1 else "")
        results = _page_data(client.get(url), "a results page")["searchListings"]
        pages = results.get("totalPages") or 1
        expected = results.get("totalItemsCount") or expected
        for card in results.get("pagedSearchResults") or []:
            if str(card.get("state", "")).lower() != cfg.state or not card.get("adID"):
                continue
            seen += 1
            if cfg.excluded(card.get("mainCategory"), _categories(card)):
                continue  # food business: never opened
            listing_id = str(card["adID"])
            entries.setdefault(listing_id, Entry(listing_id, _absolute(card.get("seoUrl", "")), _fingerprint(card), card))
        number += 1
    # A short read (a page that failed quietly) must not make listings look removed.
    if expected and seen < 0.9 * expected:
        raise Unavailable(f"read only {seen} of {expected} listings from the results pages")
    return list(entries.values())


def fetch_listing(client: PoliteClient, entry: Entry, cfg: Config) -> dict | None:
    """Listing fields, or None when the listing is gone."""
    response = client.get(entry.url)
    if response.status_code in (404, 410):
        return None
    response.raise_for_status()
    results = _page_data(response, "a listing page")["searchListings"].get("pagedSearchResults") or []
    listing = next((r for r in results if str(r.get("adID")) == entry.listing_id), None)
    return parse_listing(listing, entry.card, cfg) if listing else None


def parse_listing(listing: dict, card: dict, cfg: Config) -> dict:
    """A listing page's record (plus its results card, which has the region) -> the Listings tab's fields."""
    title = (listing.get("headline") or card.get("headline") or "").strip()
    price_text = _price_text(listing.get("displayablePrice") or card.get("displayablePrice") or "")
    description = (listing.get("description") or card.get("shortDescription") or "").replace(" ", " ").strip()
    agency = listing.get("agency") or card.get("agency") or {}
    agents = agency.get("agents") or []
    postcode = str(listing.get("postcode") or card.get("postcode") or "")
    text = "\n".join([title, description])
    profit_aud, profit_type = extract.profit(text)
    flag = str(card.get("statusFlag") or "")
    status = extract.status(f"{title} {flag}", price_text)
    names = [a.get("fullName", "").strip() for a in agents if a.get("fullName", "").strip()]
    phones = []
    for number in [a.get("mobile") for a in agents] + [a.get("telephone") for a in agents] + [agency.get("generalPhoneNumber")] + extract.phones(description):
        if number and re.sub(r"\D", "", number) not in {re.sub(r"\D", "", p) for p in phones}:
            phones.append(number.strip())
    price_data = listing.get("priceData") or {}
    row = {
        "title": title,
        "status": status,
        "industry": listing.get("mainCategory") or card.get("mainCategory") or "",
        "category": _categories(listing) or _categories(card),
        "suburb": (listing.get("suburb") or card.get("suburb") or "").strip(),
        "postcode": postcode,
        "region": card.get("region") or card.get("area") or "",
        "perth_metro": extract.perth_metro(postcode, cfg.perth_postcodes),
        "price_text": price_text,
        "price_aud": extract.price(price_text) or price_data.get("price") or price_data.get("priceFrom"),
        "price_basis": extract.price_basis(price_text),
        "turnover_aud": extract.turnover(text),
        "profit_aud": profit_aud,
        "profit_type": profit_type,
        "established": extract.established(text),
        "sale_reason": extract.sale_reasons(text),
        "key_features": "Franchise" if listing.get("isFranchise") else "",
        "broker": " / ".join(filter(None, [", ".join(names), agency.get("agencyName", "")])),
        "broker_phone": "; ".join(phones[:3]),
        "description": description[:5000],
        "fingerprint": hashlib.sha1(description.encode()).hexdigest()[:12],
    }
    row["notes"] = extract.build_notes(row)
    return row


def _page_data(response, what: str) -> dict:
    match = _NEXT_DATA.search(response.text)
    if response.status_code >= 400 or not match:
        raise Unavailable(f"commercialrealestate.com.au sent {what} without its listing data (HTTP {response.status_code})")
    return json.loads(match.group(1))["props"]["pageProps"]["data"]


def _categories(record: dict) -> str:
    return ", ".join(c.get("name", "") for c in record.get("propertyTypeDetails") or [] if c.get("name"))


def _fingerprint(card: dict) -> str:
    parts = [card.get("headline"), card.get("displayablePrice"), card.get("statusFlag"), card.get("shortDescription")]
    return hashlib.sha1("|".join(str(p or "") for p in parts).encode()).hexdigest()[:12]


def _price_text(text: str) -> str:
    text = " ".join(text.split())
    return f"${text}" if re.match(r"^\d", text) else text


def _absolute(url: str) -> str:
    return url if url.startswith("http") else BASE + url
