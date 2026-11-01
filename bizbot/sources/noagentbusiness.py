"""noagentbusiness.com.au (No Agent Property's site for businesses): owners selling for themselves.

The state's sitemap gives every ad's last-updated time, so the bot only opens pages that are new or have changed. It
also lists ads sold years ago: those are opened once, then remembered in the Skipped tab. Food businesses are left out
from the link, so their pages are never opened. Every ad here is a private seller, reached through the site's Contact
Owner form, so a phone number is only kept when the owner wrote it in the ad.
"""
import hashlib
import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .. import extract
from ..config import Config
from ..http import PoliteClient, parse_xml

NAME = "noagentbusiness"
BASE = "https://www.noagentbusiness.com.au"

_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_LISTING_URL = re.compile(r"/business-(?P<kind>.+)-[a-z]{2,3}-(?P<suburb>[a-z0-9_-]+?)-(?P<id>\d+)/?$")
_PLACE = re.compile(r"^(?P<suburb>.+?)\s+(?P<postcode>\d{4})\s+[A-Z]{2,3}$")
_PRICE = re.compile(r"^(\$[\d,]+|POA|P\.O\.A\.?|Contact)", re.I)


@dataclass(frozen=True)
class Entry:
    listing_id: str
    url: str
    lastmod: str


def list_entries(client: PoliteClient, cfg: Config) -> list[Entry]:
    root = parse_xml(client.get(f"{BASE}/{cfg.state}-sitemap.xml"), "No Agent Business's listing index")
    entries = []
    for node in root.iter(f"{_SITEMAP_NS}url"):
        url = (node.findtext(f"{_SITEMAP_NS}loc") or "").strip()
        match = _LISTING_URL.search(url)
        if match and not cfg.excluded(match["kind"].replace("-_-", " ").replace("-", " ")):
            entries.append(Entry(match["id"], url, (node.findtext(f"{_SITEMAP_NS}lastmod") or "").strip()))
    return entries


def fetch_listing(client: PoliteClient, entry: Entry, cfg: Config) -> dict | None:
    """Listing fields, or None when the listing is gone."""
    response = client.get(entry.url)
    if response.status_code in (404, 410):
        return None
    response.raise_for_status()
    row = parse_listing(response.text, cfg)
    if row and not row["suburb"] and (match := _LISTING_URL.search(entry.url)):
        # A few ads hide their place on the page, but their link still names it.
        row["suburb"] = row["region"] = match["suburb"].replace("_", " ").replace("-", " ").title()
        row["notes"] = extract.build_notes(row)
    return row


def parse_listing(html: str, cfg: Config) -> dict | None:
    page = BeautifulSoup(html, "lxml")
    listing = _listing_record(page)
    if not listing:
        return None
    heading = page.find("h1")
    headline = heading.get_text(" ", strip=True) if heading else ""
    sold = " sold " in f" {headline} ".lower()
    for element in page(["script", "style", "noscript", "nav", "footer", "header"]):
        element.decompose()
    lines = [line.strip() for line in page.get_text("\n").split("\n") if line.strip()]
    place_at = next((i for i, line in enumerate(lines) if _PLACE.match(line)), None)
    place = _PLACE.match(lines[place_at]) if place_at is not None else None
    # Above the place: the price, then the kind of business, as "$250,000", "Retail Sold:", "Denmark 6333 WA".
    above = lines[max(0, place_at - 2): place_at] if place_at is not None else []
    price_text = next((line for line in above if _PRICE.match(line)), "")
    category = re.sub(r"\s+(For Sale|Sold|Under Offer|Under Contract).*$", "", above[-1], flags=re.I).rstrip(": ") if above else ""
    title = str(listing.get("name") or "").strip() or headline
    description = str(listing.get("description") or "").strip()
    postcode = place["postcode"] if place else ""

    text = "\n".join([title, description])
    profit_aud, profit_type = extract.profit(text)
    row = {
        "title": title,
        "status": "Sold" if sold else extract.status(title, price_text),
        "industry": category,
        "category": category,
        "suburb": place["suburb"] if place else "",
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
        "key_features": "",
        "broker": "Private Seller",
        "broker_phone": "; ".join(extract.phones(description)[:3]),
        "description": description[: extract.DESCRIPTION_LIMIT],
        "fingerprint": hashlib.sha1(description.encode()).hexdigest()[:12],
    }
    row["notes"] = extract.build_notes(row)
    return row


def _listing_record(page: BeautifulSoup) -> dict:
    """The ad's structured record, which the page carries for search engines."""
    for script in page.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.get_text())
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "RealEstateListing":
            return data
    return {}
