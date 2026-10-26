"""Check SEEK: reads your SEEK Business searches in a visible Chromium window on your Mac.

SEEK turns away windowless (headless) bots, so this runs only on your Mac, in a normal visible browser
window, when you start it. It reads the newest few result pages of each search in config.toml at a
person's pace, opens up to `details` new listings for their full description, and saves everything to
the "SEEK listings" tab (the same tab the Save-to-sheet bookmark writes to). If SEEK ever shows a
security check, it stops: it never tries to get past one.

The page reading is the bookmark's own code (seekBookmarklet in seek/SaveToSheet.gs), so both read
SEEK the same way.
"""
import logging
import random
import re
import time
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import extract
from .config import ROOT, Config
from .run import PERTH, now
from .store import Table

log = logging.getLogger(__name__)

# Same columns, in the same order, as seek/SaveToSheet.gs.
SEEK = Table(
    "SEEK listings",
    [
        ("status", "Status"),
        ("title", "Title"),
        ("price_text", "Asking price"),
        ("price_aud", "Price (AUD)"),
        ("price_basis", "Price basis"),
        ("opportunity_type", "Type"),
        ("industry", "Industry"),
        ("location", "Location"),
        ("advertiser", "Advertiser"),
        ("advertiser_type", "Advertiser type"),
        ("turnover_aud", "Turnover (AUD/yr)"),
        ("profit_aud", "Profit (AUD/yr)"),
        ("phones", "Phones in listing"),
        ("summary", "Summary"),
        ("description", "Description"),
        ("url", "URL"),
        ("listing_id", "Listing ID"),
        ("seek_updated", "SEEK updated"),
        ("first_seen", "First seen"),
        ("last_seen", "Last seen"),
        ("last_changed", "Last changed"),
        ("key", "Key"),
    ],
    frozenset({"price_aud", "turnover_aud", "profit_aud"}),
)
WATCHED = {"status": "Status", "title": "Title", "price_text": "Asking price", "opportunity_type": "Type"}

_BOOKMARKLET = re.compile(r"^function seekBookmarklet\(.*?^\}$", re.M | re.S)
_CHECK_PAGE = re.compile(r"just a moment|performing security verification|attention required|verify you are human", re.I)


class SecurityCheck(Exception):
    """SEEK showed a security check instead of the page."""


def run(cfg: Config, store, limit: int | None = None, jitter: bool = False) -> list[dict]:
    """`limit` is the number of result pages per search (default: config.toml). `jitter` is ignored."""
    from playwright.sync_api import sync_playwright

    pages = cfg.seek.pages if limit is None else limit
    rows = store.load(SEEK)
    changes: list[dict] = []
    stamp = now()
    stats = dict(started=stamp, source="seek", on_site=0, new=0, updated=0, removed=0, fetched=0, backlog=0, errors=0, skipped=0, result="ok")
    reader = f"({bookmarklet_source()})(null, true)"
    try:
        with sync_playwright() as p:
            # A visible window: SEEK turns away headless browsers, and this is meant to run while you're there.
            browser = p.chromium.launch(headless=False)
            page = browser.new_context(locale="en-AU", timezone_id="Australia/Perth").new_page()
            try:
                for search in cfg.seek.searches:
                    for number in range(1, pages + 1):
                        listings = _read(page, _page_url(search, number), reader, stats)
                        stats["on_site"] += len(listings)
                        for raw in listings:
                            _save(cfg, rows, raw, stamp, changes, stats)
                        if not listings:
                            break
                        _pause(cfg)
                # Full description and phones for the newest listings that don't have them yet.
                todo = sorted((r for r in rows.values() if not r.get("description") and r.get("url")), key=lambda r: r.get("first_seen", ""), reverse=True)
                stats["backlog"] = max(0, len(todo) - cfg.seek.details)
                for row in todo[: cfg.seek.details]:
                    _pause(cfg)
                    for raw in _read(page, row["url"], reader, stats):
                        # The results card's location names the suburb; a listing page often doesn't.
                        if row.get("location"):
                            raw = {k: v for k, v in raw.items() if k != "location"}
                        _save(cfg, rows, raw, stamp, changes, stats)
            except SecurityCheck as e:
                log.error("%s", e)
                stats["result"] = str(e)
            finally:
                browser.close()
    finally:
        store.save(SEEK, rows)
        store.log(changes, [stats])
    return [stats]


def bookmarklet_source() -> str:
    """The bookmark's page-reading function, from seek/SaveToSheet.gs."""
    match = _BOOKMARKLET.search((ROOT / "seek" / "SaveToSheet.gs").read_text())
    if not match:
        raise RuntimeError("Couldn't find seekBookmarklet in seek/SaveToSheet.gs")
    return match.group(0)


def normalise(raw: dict, stamp: str) -> dict:
    """One listing as read from the page -> the fields of its row (same rules as SaveToSheet.gs)."""
    listing_id = re.sub(r"\D", "", str(raw.get("id", "")))
    title = _clean(raw.get("title"))
    price_text = _clean(raw.get("price_text")) or price_from_parts(raw)
    text = "\n".join(t for t in (title, raw.get("summary"), raw.get("description")) if t)
    basis = [b for b in extract.price_basis(price_text).split(", ") if b]
    if raw.get("sav") and "+ stock (SAV)" not in basis:
        basis.append("+ stock (SAV)")
    if raw.get("negotiable") and "Negotiable / offers" not in basis:
        basis.append("Negotiable / offers")
    refreshed = raw.get("refreshed") or ""
    return {
        "key": f"seek:{listing_id}",
        "listing_id": listing_id,
        "status": extract.status(title, price_text),
        "title": title,
        "price_text": price_text,
        "price_aud": int(raw["price_min"]) if str(raw.get("price_min") or "").isdigit() else extract.price(price_text),
        "price_basis": ", ".join(basis),
        "opportunity_type": _clean(raw.get("opportunity_type")),
        "industry": _clean(raw.get("industry")),
        "location": _clean(raw.get("location")),
        "advertiser": _clean(raw.get("advertiser")),
        "advertiser_type": _clean(raw.get("advertiser_type")),
        "turnover_aud": extract.turnover(text),
        "profit_aud": extract.profit(text)[0],
        "phones": "; ".join(extract.phones(text)),
        "summary": _clean(raw.get("summary")),
        "description": str(raw.get("description") or "").strip()[:5000],
        "url": raw.get("url", ""),
        "seek_updated": _perth_time(refreshed) if refreshed else "",
        "last_seen": stamp,
    }


def price_from_parts(raw: dict) -> str:
    if raw.get("poa"):
        return "P.O.A"
    low, high = int(raw.get("price_min") or 0), int(raw.get("price_max") or 0)
    if not low and not high:
        return ""
    text = f"${low:,} - ${high:,}" if low and high and low != high else f"${low or high:,}"
    return text + (" + SAV" if raw.get("sav") else "")


def merge(rows: dict, record: dict, stamp: str, changes: list, stats: dict) -> None:
    key = record["key"]
    old = rows.get(key)
    if old is None:
        record["first_seen"] = record["last_changed"] = stamp
        rows[key] = record
        stats["new"] += 1
        _record(changes, record, stamp, "New listing", "", record["price_text"])
        return
    # A results page has no description; keep what a listing page gave earlier.
    merged = {**old, **{f: v for f, v in record.items() if v not in (None, "")}}
    merged["first_seen"] = old.get("first_seen") or stamp
    diffs = [(label, old.get(f) or "", merged.get(f) or "") for f, label in WATCHED.items() if str(old.get(f) or "") != str(merged.get(f) or "")]
    if diffs and old.get("first_seen") != stamp:
        merged["last_changed"] = stamp
        stats["updated"] += 1
        for label, before, after in diffs:
            _record(changes, merged, stamp, label, before, after)
    rows[key] = merged


def _read(page, url: str, reader: str, stats: dict) -> list[dict]:
    response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2_500)  # let the listings render
    stats["fetched"] += 1
    if (response and response.status in (403, 429)) or _CHECK_PAGE.search(page.title()):
        raise SecurityCheck(f"SEEK showed a security check at {url}; stopped without trying to get past it")
    payload = page.evaluate(reader) or {}
    return payload.get("listings") or []


def _save(cfg: Config, rows: dict, raw: dict, stamp: str, changes: list, stats: dict) -> None:
    record = normalise(raw, stamp)
    if not record["listing_id"]:
        return
    if cfg.excluded(record["industry"]) or record["status"] == "Sold":
        stats["skipped"] += 1
        rows.pop(record["key"], None)
        return
    merge(rows, record, stamp, changes, stats)


def _page_url(search: str, number: int) -> str:
    parts = urlsplit(search)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "pg"] + ([("pg", str(number))] if number > 1 else [])
    return urlunsplit(parts._replace(query=urlencode(query)))


def _pause(cfg: Config) -> None:
    time.sleep(random.uniform(*cfg.seek.delay_seconds))


def _record(changes: list, row: dict, stamp: str, what: str, old, new) -> None:
    changes.append(dict(when=stamp, source="seek", listing_id=row.get("listing_id", ""), title=row.get("title", ""), what=what, old=old, new=new, url=row.get("url", "")))


def _perth_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PERTH).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return ""


def _clean(value) -> str:
    return " ".join(str(value or "").split())
