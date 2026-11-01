"""Copies the Google Sheet's businesses into the Deal desk app's database. The Sheet is only read.

Run with `python -m bizbot sync-db`. It needs SUPABASE_URL and SUPABASE_SERVICE_KEY. A business that has left the
Sheet stays in the database marked as off the Sheet, so anything tracked in the app keeps its history.
"""
import logging
import os
import re
from datetime import datetime, timezone

import httpx

from .config import Config
from .health import HEALTH
from .seek import SEEK
from .sheet_view import BUSINESS_TYPES, TYPE_NOISE
from .sources.commercialrealestate import TABLE as CRE
from .store import LISTINGS, SheetError

log = logging.getLogger(__name__)

BATCH = 500
SITE_NAMES = {
    "bsale": "bsale", "business2sell": "business2sell", "anybusiness": "AnyBusiness", "businessforsale": "businessforsale.com.au",
    "commercialrealestate": "commercialrealestate.com.au",
}


def sync(cfg: Config, store) -> int:
    """Copy every business across. Returns how many rows were sent."""
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise SheetError("Set SUPABASE_URL and SUPABASE_SERVICE_KEY first.")
    started = datetime.now(timezone.utc).isoformat()
    rows = [sale_row(cfg, r, r.get("source", "")) for r in store.load(LISTINGS).values()]
    rows += [sale_row(cfg, r, "commercialrealestate") for r in store.load(CRE).values()]
    rows += [seek_row(r) for r in store.load(SEEK).values()]
    rows += [practice_row(cfg, r) for r in store.load(HEALTH).values()]
    with httpx.Client(base_url=f"{url}/rest/v1", timeout=60, headers={"apikey": key, "Authorization": f"Bearer {key}"}) as db:
        for start in range(0, len(rows), BATCH):
            _send(db, "/businesses?on_conflict=id", [{**row, "on_sheet": True, "synced_at": started} for row in rows[start: start + BATCH]])
        _check(db.patch("/businesses", params={"synced_at": f"lt.{started}"}, json={"on_sheet": False}))
        _send(db, "/site_runs?on_conflict=site", latest_runs(store))
    log.info("Sent %d businesses to the database", len(rows))
    return len(rows)


def latest_runs(store) -> list[dict]:
    """The newest result for each site, from the Runs tab."""
    latest = {}
    for row in store.book.worksheet("Runs").get_all_values()[1:]:
        latest[row[1]] = {"site": row[1], "started": row[0], "result": row[-1]}
    return list(latest.values())


def sale_row(cfg: Config, r: dict, source: str) -> dict:
    site = SITE_NAMES.get(source, source)
    seller = r.get("broker") or ""
    where = r.get("suburb") or r.get("region") or ""
    region = r.get("region") or ""
    return {
        **_common(r),
        "kind": "sale",
        "site": site,
        "name": r.get("title") or "Untitled listing",
        "summary": r.get("notes"),
        "types": listing_types(f"{r.get('industry', '')} {r.get('category', '')}"),
        "category": r.get("category"),
        "suburb": where,
        "postcode": r.get("postcode"),
        "region": region,
        "perth": r.get("perth_metro") == "Yes" or (not r.get("perth_metro") and "perth" in region.lower()),
        "price_text": r.get("price_text"),
        "price": _money(r.get("price_aud")),
        "turnover": r.get("turnover_aud"),
        "profit": _believable_profit(r),
        "route": seller_route(seller),
        "tags": _some([f"On {site}", r.get("established") and f"Est. {r['established']}", r.get("sale_reason")]),
        "seller": seller,
        "phone": r.get("broker_phone"),
        "url": r.get("url"),
        "description": r.get("description"),
        "facts": _facts(r, site, [
            ("Asking price", r.get("price_text"), site), ("Turnover", _dollars(r.get("turnover_aud")), "Read from the listing text"),
            ("Profit", _dollars(_believable_profit(r)), "Read from the listing text"), ("Where", where, site), ("Seller", seller, site),
            ("Phone", r.get("broker_phone"), site), ("Established", r.get("established"), "Read from the listing text"),
            ("Reason for sale", r.get("sale_reason"), "Read from the listing text"),
        ]),
    }


def seek_row(r: dict) -> dict:
    seller = r.get("advertiser") or ""
    return {
        **_common(r),
        "kind": "sale",
        "site": "SEEK Business",
        "name": r.get("title") or "Untitled listing",
        "summary": r.get("summary"),
        "types": listing_types(f"{r.get('industry', '')} {r.get('opportunity_type', '')}"),
        "category": r.get("industry"),
        "suburb": r.get("location"),
        "postcode": "",
        "region": "Perth",
        "perth": True,  # the SEEK search only covers 50 km around Perth
        "price_text": r.get("price_text"),
        "price": _money(r.get("price_aud")),
        "turnover": r.get("turnover_aud"),
        "profit": _believable_profit(r),
        "route": {"PrivateSeller": "Private seller", "Franchisor": "Franchisor"}.get(r.get("advertiser_type"), "Via broker"),
        "tags": _some(["On SEEK Business", r.get("advertiser_type")]),
        "seller": seller,
        "phone": r.get("phones"),
        "url": r.get("url"),
        "description": r.get("description") or r.get("summary"),
        "facts": _facts(r, "SEEK Business", [
            ("Asking price", r.get("price_text"), "SEEK Business"), ("Turnover", _dollars(r.get("turnover_aud")), "Read from the listing text"),
            ("Profit", _dollars(_believable_profit(r)), "Read from the listing text"), ("Where", r.get("location"), "SEEK Business"),
            ("Advertiser", seller, "SEEK Business"), ("Phone", r.get("phones"), "SEEK Business"),
        ]),
    }


def practice_row(cfg: Config, r: dict) -> dict:
    postcode = str(r.get("postcode") or "")
    sector = r.get("sector") or "Other"
    people = r.get("practitioner_count")
    return {
        **_common(r),
        "kind": "practice",
        "site": "healthdirect",
        "name": r.get("name") or "Unnamed practice",
        "summary": r.get("main_service"),
        "types": [sector],
        "category": r.get("main_service"),
        "suburb": r.get("suburb"),
        "postcode": postcode,
        "region": "",
        "perth": postcode.isdigit() and any(low <= int(postcode) <= high for low, high in cfg.perth_postcodes),
        "price_text": "",
        "route": "Needs a pharmacist" if sector == "Pharmacy" else "Not scored yet",
        "tags": _some([r.get("main_service"), people and f"{people} practitioners", r.get("email") and "Email listed"]),
        "seller": r.get("owner"),
        "phone": r.get("phone"),
        "email": r.get("email"),
        "website": r.get("website"),
        "address": r.get("address"),
        "url": r.get("healthdirect_url"),
        "map_url": r.get("map"),
        "description": r.get("services"),
        "facts": _facts(r, "healthdirect", [
            ("Address", r.get("address"), "healthdirect"), ("Phone", r.get("phone"), "healthdirect"), ("Email", r.get("email"), "healthdirect"),
            ("Website", r.get("website"), "healthdirect"), ("Main service", r.get("main_service"), "healthdirect"),
            ("All services", r.get("services"), "healthdirect"), ("Practitioners", r.get("practitioners"), "healthdirect"),
            ("Owner", r.get("owner"), "ABN Lookup"), ("ABN", r.get("abn"), "ABN Lookup"),
        ]),
    }


def listing_types(text: str) -> list[str]:
    """The Find tab's business types a listing belongs to."""
    cleaned = re.sub(TYPE_NOISE, "", text.lower())
    return [name for name, pattern in BUSINESS_TYPES[1:] if re.search(pattern, cleaned)]


def seller_route(seller: str) -> str:
    if not seller:
        return "Site enquiry"
    return "Private seller" if "private" in seller.lower() else "Via broker"


def _common(r: dict) -> dict:
    row = {"id": r["key"], "status": r.get("status"), "first_seen": _when(r.get("first_seen"))}
    for field in ("summary", "types", "category", "suburb", "postcode", "region", "perth", "price_text", "price", "turnover", "profit", "route",
                  "tags", "seller", "phone", "email", "website", "address", "url", "map_url", "description", "facts", "search_text"):
        row[field] = None
    return row


def _facts(r: dict, site: str, items: list[tuple]) -> list[dict]:
    """What we know, each with where it came from and when. Empty facts are left out."""
    date = str(r.get("last_seen") or r.get("first_seen") or "")[:10]
    return [{"label": label, "value": str(value), "source": source, "date": date} for label, value, source in items if value not in (None, "")]


def _believable_profit(r: dict):
    """A profit as high as the turnover means one of them was misread."""
    turnover, profit = r.get("turnover_aud"), r.get("profit_aud")
    return None if turnover and profit and profit >= turnover else profit


def _money(value):
    """SEEK uses a price of $1 for "price on application"."""
    return value if value and value > 1 else None


def _dollars(value) -> str:
    return f"${value:,.0f}" if value else ""


def _some(values: list) -> list[str]:
    return [str(v) for v in values if v]


def _when(stamp) -> str | None:
    """A "YYYY-MM-DD HH:MM" Perth time as a moment the database understands."""
    return f"{str(stamp)[:16].replace(' ', 'T')}:00+08:00" if re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d", str(stamp or "")) else None


def _send(db: httpx.Client, path: str, rows: list[dict]) -> None:
    if rows:
        for row in rows:
            if "name" in row:
                row["search_text"] = " ".join(str(row.get(f) or "") for f in ("name", "suburb", "seller", "category", "summary", "phone")).lower()
        _check(db.post(path, json=rows, headers={"Prefer": "resolution=merge-duplicates,return=minimal"}))


def _check(response: httpx.Response) -> None:
    if response.status_code >= 300:
        raise SheetError(f"The database refused the data (HTTP {response.status_code}): {response.text[:300]}")
