"""One bot run: list each source's listings, open the new or changed ones, and record what changed."""
import logging
import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Config
from .http import Blocked, PoliteClient
from .sources import SOURCES
from .store import LISTINGS, SKIPPED

log = logging.getLogger(__name__)
PERTH = ZoneInfo("Australia/Perth")

# Changes to these fields are written to the Changes tab.
WATCHED = {
    "status": "Status",
    "title": "Title",
    "price_text": "Asking price",
    "category": "Category",
    "fingerprint": "Description",
}


def run(cfg: Config, store, limit: int | None = None, jitter: bool = False) -> list[dict]:
    if jitter:
        wait_randomly(cfg)
    listings = store.load(LISTINGS)
    skipped = store.load(SKIPPED)
    client = PoliteClient(cfg.user_agent, cfg.delay_seconds)
    changes: list[dict] = []
    runs: list[dict] = []
    try:
        for name in cfg.sources:
            max_pages = cfg.max_listings_per_run if limit is None else limit
            runs.append(sync_source(SOURCES[name], cfg, client, listings, changes, max_pages, skipped))
    finally:
        store.save(LISTINGS, listings)
        store.save(SKIPPED, skipped)
        store.log(changes, runs)
    return runs


def wait_randomly(cfg: Config) -> None:
    wait = random.uniform(*cfg.start_jitter_minutes) * 60
    log.info("Waiting %.0f seconds before starting", wait)
    time.sleep(wait)


def sync_source(source, cfg: Config, client: PoliteClient, listings: dict, changes: list, limit: int, skipped: dict | None = None) -> dict:
    stamp = now()
    skipped = {} if skipped is None else skipped
    stats = dict(started=stamp, source=source.NAME, on_site=0, new=0, updated=0, removed=0, fetched=0, backlog=0, errors=0, skipped=0, result="ok")
    try:
        entries = {f"{source.NAME}:{e.listing_id}": e for e in source.list_entries(client, cfg)}
    except Blocked as e:
        log.error("%s refused the listing index: %s", source.NAME, e)
        stats["result"] = f"blocked: {e}"
        return stats
    except Exception as e:
        # Often a temporary "busy" page; the next run tries again.
        log.error("Couldn't read the %s listing index: %s", source.NAME, e)
        stats["result"] = f"listing index unavailable: {e}"
        return stats
    stats["on_site"] = len(entries)
    if not entries:
        # An empty index is far more likely a site problem than every listing selling at once.
        stats["result"] = "listing index was empty; nothing marked as removed"
        return stats

    # Listings already in the sheet that the exclusions now cover (food businesses) leave it.
    for key in [k for k, row in listings.items() if row.get("source") == source.NAME and cfg.excluded(row.get("industry"), row.get("category"))]:
        row = listings.pop(key)
        skipped[key] = _skip(key, row, stamp, cfg.excluded(row.get("industry"), row.get("category")))
        stats["skipped"] += 1
    # Forget skipped listings that are no longer on the site.
    for key in [k for k, row in skipped.items() if row.get("source") == source.NAME and k not in entries]:
        del skipped[key]

    for key, row in listings.items():
        if row.get("source") != source.NAME:
            continue
        if key in entries:
            row["last_seen"] = stamp
        elif row.get("status") != "Removed":
            _record(changes, row, stamp, "Status", row.get("status", ""), "Removed")
            # Clearing the site timestamp makes the bot re-open the listing if it comes back.
            row.update(status="Removed", last_changed=stamp, sitemap_lastmod="")
            stats["removed"] += 1

    # A skipped listing is opened again only if the site has updated it since.
    was_skipped = {k for k, e in entries.items() if skipped.get(k, {}).get("sitemap_lastmod") == e.lastmod}
    new = sorted((e for k, e in entries.items() if k not in listings and k not in was_skipped), key=lambda e: int(e.listing_id), reverse=True)
    updated = [e for k, e in entries.items() if k in listings and listings[k].get("sitemap_lastmod") != e.lastmod]
    queue = (new + updated)[:limit]
    stats["backlog"] = len(new) + len(updated) - len(queue)
    random.shuffle(queue)
    log.info("%s: %d listings on site, %d new, %d updated, opening %d now", source.NAME, len(entries), len(new), len(updated), len(queue))

    for done, entry in enumerate(queue, 1):
        key = f"{source.NAME}:{entry.listing_id}"
        try:
            data = source.fetch_listing(client, entry, cfg)
        except Blocked as e:
            log.error("%s started refusing pages, stopping this source: %s", source.NAME, e)
            stats["result"] = f"blocked after {done - 1} pages: {e}"
            stats["backlog"] += len(queue) - done + 1
            break
        except Exception as e:
            log.warning("Could not read %s: %s", entry.url, e)
            stats["errors"] += 1
            continue
        stats["fetched"] += 1
        if data is None:
            if key in listings and listings[key].get("status") != "Removed":
                _record(changes, listings[key], stamp, "Status", listings[key].get("status", ""), "Removed")
                listings[key].update(status="Removed", last_changed=stamp, sitemap_lastmod=entry.lastmod)
                stats["removed"] += 1
            continue
        if word := cfg.excluded(data.get("industry"), data.get("category")):
            skipped[key] = _skip(key, {**data, "url": entry.url}, stamp, word, entry.lastmod)
            listings.pop(key, None)
            stats["skipped"] += 1
            continue
        skipped.pop(key, None)
        _merge(listings, key, source.NAME, entry, data, stamp, changes, stats)
        if done % 25 == 0:
            log.info("%s: %d/%d pages opened", source.NAME, done, len(queue))
    if stats["skipped"]:
        log.info("%s: skipped %d listings in excluded categories (see the Skipped tab)", source.NAME, stats["skipped"])
    return stats


def _skip(key: str, row: dict, stamp: str, word: str, lastmod: str | None = None) -> dict:
    return {
        "key": key,
        "title": row.get("title", ""),
        "reason": f"Excluded category ({word.lower()}): {row.get('category') or row.get('industry')}",
        "source": key.split(":", 1)[0],
        "url": row.get("url", ""),
        "sitemap_lastmod": row.get("sitemap_lastmod", "") if lastmod is None else lastmod,
        "skipped_at": stamp,
    }


def _merge(listings: dict, key: str, source_name: str, entry, data: dict, stamp: str, changes: list, stats: dict) -> None:
    old = listings.get(key)
    row = {
        **(old or {}),
        **data,
        "key": key,
        "source": source_name,
        "listing_id": entry.listing_id,
        "url": entry.url,
        "sitemap_lastmod": entry.lastmod,
        "last_seen": stamp,
    }
    if old is None:
        row["first_seen"] = row["last_changed"] = stamp
        stats["new"] += 1
        _record(changes, row, stamp, "New listing", "", row.get("price_text", ""))
    else:
        diffs = [(label, old.get(f) or "", row.get(f) or "") for f, label in WATCHED.items() if str(old.get(f) or "") != str(row.get(f) or "")]
        if diffs:
            row["last_changed"] = stamp
            stats["updated"] += 1
        for label, before, after in diffs:
            if label == "Description":
                before, after = "", "Description text changed"
            _record(changes, row, stamp, label, before, after)
    listings[key] = row


def _record(changes: list, row: dict, stamp: str, what: str, old, new) -> None:
    changes.append(
        dict(when=stamp, source=row.get("source", ""), listing_id=row.get("listing_id", ""), title=row.get("title", ""), what=what, old=old, new=new, url=row.get("url", ""))
    )


def now() -> str:
    return datetime.now(PERTH).strftime("%Y-%m-%d %H:%M")


def is_due(stamp, days: int) -> bool:
    """True when a "YYYY-MM-DD HH:MM" Perth time is empty or at least `days` days ago."""
    if not stamp:
        return True
    try:
        checked = datetime.strptime(str(stamp), "%Y-%m-%d %H:%M").replace(tzinfo=PERTH)
    except ValueError:
        return True
    return datetime.now(PERTH) - checked >= timedelta(days=days)
