"""business2sell.com.au: businesses for sale in one state.

The state's results pages (/businesses/wa?page=2 ...; 10 listings each) carry a card per listing. The bot reads all of
them each run, then opens a listing's own page only when the listing is new or its card changed. Food businesses are
left out from the cards, so their pages are never opened.
"""
import hashlib
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .. import extract
from ..config import Config
from ..http import PoliteClient, Unavailable

NAME = "business2sell"
BASE = "https://www.business2sell.com.au"

# Most links end in the advert's number, but about one in four is only words: then the words are the ID.
_LISTING_URL = re.compile(r"/businesses-details/(?P<slug>.+?)(?:-(?P<id>\d+))?\.php$")
_TOTAL = re.compile(r"^\s*([\d,]+) Business")
_SELLER = re.compile(r"Seller Name\s*:\s*([^\n]+)")


@dataclass
class Entry:
    listing_id: str
    url: str
    lastmod: str  # a fingerprint of the results card: it changes when the listing does


def list_entries(client: PoliteClient, cfg: Config) -> list[Entry]:
    entries: dict[str, Entry] = {}
    seen = expected = 0
    number = 1
    while True:
        url = f"{BASE}/businesses/{cfg.state}" + (f"?page={number}" if number > 1 else "")
        response = client.get(url)
        page = BeautifulSoup(response.text, "lxml")
        headings = page.select("h2.b2s_listing_heading a[href]")
        if response.status_code >= 400 or (number == 1 and not headings):
            raise Unavailable(f"business2sell sent a results page without listings (HTTP {response.status_code})")
        if number == 1 and page.title and (total := _TOTAL.match(page.title.get_text())):
            expected = int(total.group(1).replace(",", ""))
        for link in headings:
            match = _LISTING_URL.search(link["href"])
            if not match:
                continue
            seen += 1
            card = link.find_parent(class_="b2s_listing")
            if cfg.excluded(_text(card, "ul.b2s_listing_cat")):
                continue  # food business: never opened
            listing_id = match["id"] or match["slug"]
            entries.setdefault(listing_id, Entry(listing_id, BASE + link["href"], _fingerprint(card)))
        if not page.find("a", href=re.compile(rf"[?&]page={number + 1}\b")):
            break
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
    return parse_listing(response.text, cfg)


def parse_listing(html: str, cfg: Config) -> dict | None:
    page = BeautifulSoup(html, "lxml")
    heading = page.select_one("h2.b2s_standard_heading")
    if heading is None:
        return None
    title = heading.get_text(" ", strip=True)
    facts = _facts(page)
    price_text = facts.get("Asking Price", "")
    place = [part.strip() for part in facts.get("Location", "").split(",") if part.strip()]
    categories = [part.strip() for part in facts.get("Category", "").split(",") if part.strip()]
    wrapper = page.select_one(".business_description_wrapper")
    written = wrapper.get_text("\n", strip=True) if wrapper else ""
    seller = _SELLER.search(written)
    description = _SELLER.split(written)[0].removeprefix("Business description").strip()

    # In the same words as bsale's lines, so the same rules read them first.
    features = [f"Turnover: {facts.get('Sales revenue', 'Not disclosed')}", f"Net Profit: {facts.get('Net profit', 'Not disclosed')}"]
    text = "\n".join([title, *features, description])
    profit_aud, profit_type = extract.profit(text)
    row = {
        "title": title,
        "status": extract.status(title, price_text),
        "industry": categories[0] if categories else "",
        "category": ", ".join(categories),
        "suburb": place[0] if len(place) >= 3 else "",
        "postcode": "",
        "region": place[-2] if len(place) >= 2 else "",
        "perth_metro": "",
        "price_text": price_text,
        "price_aud": extract.price(price_text),
        "price_basis": extract.price_basis(price_text),
        "turnover_aud": extract.turnover(text),
        "profit_aud": profit_aud,
        "profit_type": profit_type,
        "established": extract.established(text),
        "sale_reason": extract.sale_reasons(text),
        "key_features": "\n".join(features),
        "broker": seller.group(1).strip() if seller else "",
        "broker_phone": "; ".join(extract.phones(description)[:3]),
        "description": description[: extract.DESCRIPTION_LIMIT],
        "fingerprint": hashlib.sha1(description.encode()).hexdigest()[:12],
    }
    row["notes"] = extract.build_notes(row)
    return row


def _facts(page: BeautifulSoup) -> dict[str, str]:
    """The labelled lines at the top of a listing, such as "Asking Price: $240,000"."""
    facts = {}
    for label in page.select("ul li > span"):
        name = label.get_text(strip=True)
        if name.endswith(":"):
            facts.setdefault(name.rstrip(": "), label.next_sibling.strip() if isinstance(label.next_sibling, str) else "")
    return facts


def _fingerprint(card) -> str:
    parts = [_text(card, ".b2s_listing_heading"), _text(card, ".b2s_listing_price"), _text(card, ".b2s_listing_subheading")]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def _text(card, selector: str) -> str:
    element = card.select_one(selector) if card else None
    return element.get_text(" ", strip=True) if element else ""
