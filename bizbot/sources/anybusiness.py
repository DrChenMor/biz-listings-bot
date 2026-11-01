"""anybusiness.com.au: businesses for sale in one state.

The state's results pages (/business-for-sale/wa?page=2 ...; about 25 listings each) link every listing, and each
link spells out the listing's categories. The bot reads all of them each run, then opens a listing's own page only
when the listing is new or its card changed. Food businesses are left out from the links, so their pages are never
opened.
"""
import hashlib
import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .. import extract
from ..config import Config
from ..http import PoliteClient, Unavailable

NAME = "anybusiness"
BASE = "https://www.anybusiness.com.au"

_LISTING_URL = re.compile(r"^/listings/(?P<slug>.+)-(?P<id>\d+)$")
_TOTAL = re.compile(r"([\d,]+) results")
_PLACE = re.compile(r"/listings/(?P<suburb>[a-z-]+?)-wa-(?P<postcode>\d{4})-")


@dataclass
class Entry:
    listing_id: str
    url: str
    lastmod: str  # a fingerprint of the results card: it changes when the listing does


def list_entries(client: PoliteClient, cfg: Config) -> list[Entry]:
    entries: dict[str, Entry] = {}
    seen: set[str] = set()
    expected = 0
    number = 1
    while True:
        url = f"{BASE}/business-for-sale/{cfg.state}" + (f"?page={number}" if number > 1 else "")
        response = client.get(url)
        page = BeautifulSoup(response.text, "lxml")
        links = [(a["href"], _LISTING_URL.match(a["href"])) for a in page.select('a[href^="/listings/"]')]
        if response.status_code >= 400 or (number == 1 and not links):
            raise Unavailable(f"AnyBusiness sent a results page without listings (HTTP {response.status_code})")
        if number == 1 and (total := _TOTAL.search(response.text)):
            expected = int(total.group(1).replace(",", ""))
        for href, match in links:
            if not match or match["id"] in seen:
                continue
            seen.add(match["id"])
            if cfg.excluded(match["slug"].replace("-", " ")):
                continue  # food business: never opened
            link = page.find("a", href=href)
            entries[match["id"]] = Entry(match["id"], BASE + href, _fingerprint(link.find_parent(class_="uk-grid") or link))
        if not page.find("a", href=re.compile(rf"[?&]page={number + 1}\b")):
            break
        number += 1
    # A short read (a page that failed quietly) must not make listings look removed.
    if expected and len(seen) < 0.9 * expected:
        raise Unavailable(f"read only {len(seen)} of {expected} listings from the results pages")
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
    heading = page.find("h1")
    if heading is None:
        return None
    title = heading.get_text(" ", strip=True)
    summary = heading.find_next_sibling("div")
    # "Amusements | Business for Sale | 120 Hector St W, Osborne Park, WA, 6017"
    parts = [part.strip() for part in summary.get_text(" ", strip=True).split("|")] if summary else []
    category = parts[0] if parts else ""
    address = parts[-1] if len(parts) > 1 else ""
    # The page's own address for itself spells out the place: /listings/osborne-park-wa-6017-...
    canonical = page.find("link", rel="canonical")
    place = _PLACE.search(canonical.get("href", "")) if canonical else None
    postcode = place["postcode"] if place else ""
    suburb = place["suburb"].replace("-", " ").title() if place else ""
    price_text = _prop(page, "price")
    state_on_site = _labelled(page, "Status")
    description_el = page.find(attrs={"itemprop": "description"})
    description = description_el.get_text("\n", strip=True) if description_el else ""
    phone = page.select_one(".view-agent-mobile-btn[data-react-props]")

    text = "\n".join([title, description])
    profit_aud, profit_type = extract.profit(text)
    row = {
        "title": title,
        "status": extract.status(f"{title} - {state_on_site}", price_text),
        "industry": category,
        "category": category,
        "suburb": suburb,
        "postcode": postcode,
        "region": "",
        "perth_metro": extract.perth_metro(postcode, cfg.perth_postcodes),
        "price_text": price_text,
        "price_aud": extract.price(price_text),
        "price_basis": extract.price_basis(price_text),
        "turnover_aud": extract.turnover(text),
        "profit_aud": profit_aud,
        "profit_type": profit_type,
        "established": extract.established(text),
        "sale_reason": extract.sale_reasons(text),
        "key_features": f"Address in the ad: {address}" if address else "",
        "broker": _seller(page),
        "broker_phone": _phone(phone) or "; ".join(extract.phones(description)[:3]),
        "description": description[: extract.DESCRIPTION_LIMIT],
        "fingerprint": hashlib.sha1(description.encode()).hexdigest()[:12],
    }
    row["notes"] = extract.build_notes(row)
    return row


def _prop(page: BeautifulSoup, name: str) -> str:
    element = page.find(attrs={"itemprop": name})
    return (element.get("content") or element.get_text(" ", strip=True)) if element else ""


def _labelled(page: BeautifulSoup, label: str) -> str:
    """The value beside a label such as "Status:" in the box above the title."""
    name = page.find(string=re.compile(rf"^\s*{label}:\s*$"))
    following = name.find_parent().find_next_sibling() if name else None
    return following.get_text(" ", strip=True) if following else ""


def _seller(page: BeautifulSoup) -> str:
    """An owner's own ad says "Vendor details"; a broker's gives the agency, its address, then the agent."""
    element = page.find(attrs={"itemprop": "seller"})
    lines = list(element.stripped_strings) if element else []
    if not lines:
        return ""
    if lines[0].lower().startswith("vendor"):
        name = next((line for line in lines[1:] if not line.endswith(":")), "")
        return f"Private Seller: {name}" if name else "Private Seller"
    return " / ".join(dict.fromkeys([lines[-1], lines[0]]))


def _phone(button) -> str:
    try:
        return json.loads(button["data-react-props"]).get("defaultContactNO") or ""
    except (TypeError, ValueError):
        return ""


def _fingerprint(card) -> str:
    return hashlib.sha1(card.get_text(" ", strip=True).encode()).hexdigest()[:12]
