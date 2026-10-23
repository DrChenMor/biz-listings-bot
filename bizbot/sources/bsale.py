"""bsale.com.au: listing URLs come from the public sitemap, details from each listing page.

The sitemap gives every listing's last-updated time, so the bot only opens pages that are new
or have changed since the last run.
"""
import hashlib
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .. import extract
from ..config import Config
from ..http import PoliteClient, parse_xml

NAME = "bsale"
SITEMAP = "https://bsale.com.au/sitemap-businesses.php"

_LISTING_URL = re.compile(r"^https://bsale\.com\.au/(?:listing|franchise-for-sale)/.+-(?P<state>[a-z]{2,3})-(?P<id>\d+)$")
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_LOCATION = re.compile(r"^(?:(?P<suburb>[^,]+),\s*)?(?P<state>[A-Za-z ]+?)\s*(?P<postcode>\d{4})?$")
_DESCRIPTION_LIMIT = 5000

# Category link -> industry, read once from the site's own menu.
_industries: dict[str, str] = {}


@dataclass(frozen=True)
class Entry:
    listing_id: str
    url: str
    lastmod: str


def list_entries(client: PoliteClient, cfg: Config) -> list[Entry]:
    root = parse_xml(client.get(SITEMAP), "bsale's listing index")
    entries = []
    for node in root.iter(f"{_SITEMAP_NS}url"):
        url = (node.findtext(f"{_SITEMAP_NS}loc") or "").strip()
        match = _LISTING_URL.match(url)
        if match and match["state"] == cfg.state:
            entries.append(Entry(match["id"], url, (node.findtext(f"{_SITEMAP_NS}lastmod") or "").strip()))
    return entries


def fetch_listing(client: PoliteClient, entry: Entry, cfg: Config) -> dict | None:
    """Listing fields, or None when the listing is gone."""
    response = client.get(entry.url)
    if response.status_code in (404, 410):
        return None
    response.raise_for_status()
    return parse_listing(response.text, cfg)


def parse_listing(html: str, cfg: Config) -> dict | None:
    page = BeautifulSoup(html, "lxml")
    main = page.find(id="listingMain")
    if main is None:
        return None
    if not _industries:
        _industries.update(_industry_menu(page))

    title = _text(page.find("h1"))
    location = _LOCATION.match(_text(main.find("p", class_="mt-4", recursive=False)))
    suburb = (location["suburb"] or "").strip() if location else ""
    if "region" in suburb.lower():
        suburb = ""  # e.g. "Perth Region WA Region": a region, not a suburb
    postcode = (location["postcode"] or "") if location else ""
    price_text = _text(main.find("h2", class_="text-success", recursive=False))
    features = [_text(li) for ul in main.find_all("ul", class_="listReset", recursive=False) for li in ul.find_all("li")]
    category_links = _category_links(main)
    description_el = main.find("div", class_="bsaleDesc", recursive=False)
    description = description_el.get_text("\n", strip=True) if description_el else ""
    region_list = main.select_one(":scope > ul.list-inline")
    side = page.find(id="listingSide")
    phone_link = side.select_one("a.btn-phone") if side else None

    text = "\n".join([title, *features, description])
    profit_aud, profit_type = extract.profit(text)
    listing = {
        "title": title,
        "status": extract.status(title, price_text),
        "industry": next((_industries[a["href"]] for a in category_links if a["href"] in _industries), ""),
        "category": ", ".join(_text(a) for a in category_links),
        "suburb": suburb,
        "postcode": postcode,
        "region": _text(region_list.find("li")) if region_list else "",
        "perth_metro": extract.perth_metro(postcode, cfg.perth_postcodes),
        "price_text": price_text,
        "price_aud": extract.price(price_text) or _meta_price(page),
        "price_basis": extract.price_basis(price_text),
        "turnover_aud": extract.turnover(text),
        "profit_aud": profit_aud,
        "profit_type": profit_type,
        "established": extract.established(text),
        "sale_reason": extract.sale_reasons(text),
        "key_features": "\n".join(features),
        "broker": _text(side.select_one("p.text-primary")) if side else "",
        "broker_phone": (phone_link.get("data-ph") or phone_link.get("href", "").removeprefix("tel:")) if phone_link else "",
        "description": description[:_DESCRIPTION_LIMIT],
        "fingerprint": hashlib.sha1(description.encode()).hexdigest()[:12],
    }
    listing["notes"] = extract.build_notes(listing)
    return listing


def _category_links(main) -> list:
    for paragraph in main.find_all("p", recursive=False):
        if "Business Category" in paragraph.get_text():
            return paragraph.find_all("a", href=True)
    return []


def _industry_menu(page) -> dict[str, str]:
    industries = {}
    for industry in page.select("a.menu-fly[data-pos^='#cat']"):
        panel = page.select_one(industry["data-pos"])
        for link in panel.select("a[href]") if panel else []:
            industries.setdefault(link["href"], industry.get_text(strip=True))
    return industries


def _meta_price(page) -> int | None:
    meta = page.find("meta", property="product:price:amount")
    content = meta.get("content", "") if meta else ""
    return int(content) if content.isdigit() and int(content) > 0 else None


def _text(element) -> str:
    return " ".join(element.get_text(" ", strip=True).split()) if element else ""
