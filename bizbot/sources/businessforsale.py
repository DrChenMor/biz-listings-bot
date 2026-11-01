"""businessforsale.com.au: businesses for sale in one state.

The state's results pages (/for-sale/wa/?page=2 ...; 20 listings each) carry a card per listing. The bot reads all of
them each run, then opens a listing's own page only when the listing is new or its card changed. A listing's category
is only on its own page, so food businesses are left out after opening and remembered in the Skipped tab.

Sellers are reached through the site's enquiry form, so there are no phone numbers. Ads marked OWNER DIRECT or "in
the seller's words" are private sellers. Revenue and profit are bands such as "$250k - 500k": the number columns hold the low end.
"""
import hashlib
import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .. import extract
from ..config import Config
from ..http import PoliteClient, Unavailable

NAME = "businessforsale"
BASE = "https://www.businessforsale.com.au"

_LISTING_URL = re.compile(r"/australia/(?P<id>[^/]+)/[^/]+/?$")
_TOTAL = re.compile(r"([\d,]+) businesses listed for sale")


@dataclass
class Entry:
    listing_id: str
    url: str
    lastmod: str  # a fingerprint of the results card: it changes when the listing does


def list_entries(client: PoliteClient, cfg: Config) -> list[Entry]:
    entries: dict[str, Entry] = {}
    expected = 0
    number = 1
    while True:
        url = f"{BASE}/for-sale/{cfg.state}/" + (f"?page={number}" if number > 1 else "")
        response = client.get(url)
        page = BeautifulSoup(response.text, "lxml")
        cards = page.select("div.result.listing")
        if response.status_code >= 400 or (number == 1 and not cards):
            raise Unavailable(f"businessforsale.com.au sent a results page without listings (HTTP {response.status_code})")
        if number == 1 and (total := _TOTAL.search(response.text)):
            expected = int(total.group(1).replace(",", ""))
        for card in cards:
            link = next((a for a in card.find_all("a", href=True) if _LISTING_URL.search(a["href"])), None)
            if link:
                listing_id = _LISTING_URL.search(link["href"])["id"]
                address = link["href"] if link["href"].startswith("http") else BASE + link["href"]
                entries.setdefault(listing_id, Entry(listing_id, address, _fingerprint(card)))
        if not page.find("a", href=re.compile(rf"[?&]page={number + 1}\b")):
            break
        number += 1
    # A short read (a page that failed quietly) must not make listings look removed.
    if expected and len(entries) < 0.9 * expected:
        raise Unavailable(f"read only {len(entries)} of {expected} listings from the results pages")
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
    product = _product(page)
    if not product:
        return None
    text_on_page = page.get_text()
    private = "OWNER DIRECT" in text_on_page or "In the seller's words" in text_on_page
    for element in page(["script", "style", "noscript", "nav", "footer", "header"]):
        element.decompose()
    lines = [line.strip() for line in page.get_text("\n").split("\n") if line.strip()]
    title = product.get("name", "").strip()
    area, _, kind = str(product.get("category", "")).partition(">")
    region = re.sub(r",?\s*WA$", "", _after(lines, "Location")).strip()
    price_text = _after(lines, "Asking price")
    basis = _after(lines, "Asking price", 2)
    if basis.startswith(("+", "Negotiable")):
        price_text = f"{price_text} {basis}"
    description = _description(lines) or str(product.get("description", ""))

    # In the same words as bsale's lines, so the same rules read them first.
    features = [f"Turnover: {_after(lines, 'Revenue') or 'Not disclosed'}", f"Net Profit: {_after(lines, 'Profit') or 'Not disclosed'}"]
    text = "\n".join([title, *features, description])
    profit_aud, profit_type = extract.profit(text)
    row = {
        "title": title,
        "status": extract.status(title, price_text),
        "industry": area.strip(),
        "category": kind.strip() or area.strip(),
        "suburb": "" if "region" in region.lower() else region,
        "postcode": "",
        "region": region,
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
        "broker": "Private Seller" if private else "",
        "broker_phone": "; ".join(extract.phones(description)[:3]),
        "description": description[: extract.DESCRIPTION_LIMIT],
        "fingerprint": hashlib.sha1(description.encode()).hexdigest()[:12],
    }
    row["notes"] = extract.build_notes(row)
    return row


def _product(page: BeautifulSoup) -> dict:
    """The listing's structured record, which the page carries for search engines."""
    for script in page.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.get_text())
        except ValueError:
            continue
        for item in data.get("@graph", [data]) if isinstance(data, dict) else []:
            if item.get("@type") == "Product":
                return item
    return {}


def _after(lines: list[str], label: str, step: int = 1) -> str:
    """The line `step` lines below the first line that is exactly `label`."""
    if label not in lines:
        return ""
    index = lines.index(label) + step
    return lines[index] if index < len(lines) else ""


def _description(lines: list[str]) -> str:
    """The seller's own words: from the line that introduces them to the next numbered section."""
    start = next((i for i, line in enumerate(lines) if line.startswith("Full description, as written by")), None)
    if start is None:
        return ""
    body = lines[start + 1:]
    end = next((i for i, line in enumerate(body) if re.match(r"^0\d\s*·", line)), len(body))
    return "\n".join(body[:end])


def _fingerprint(card) -> str:
    return hashlib.sha1(card.get_text(" ", strip=True).encode()).hexdigest()[:12]
