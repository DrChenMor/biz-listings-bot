"""SEEK alert emails: reads the "new results for your saved search" emails SEEK Business sends to a Gmail
inbox, and adds the listings in them to the SEEK listings tab. Runs on GitHub every day; nothing visits SEEK.

Listings are found by their SEEK links (every alert links to each listing), so this keeps working if SEEK
changes the email's layout. An alert only adds listings that aren't in the sheet yet; prices, changes and
full descriptions come from "Check SEEK" on your Mac.

Needs GMAIL_ADDRESS and GMAIL_APP_PASSWORD (a Google app password for that inbox). Without them it does nothing.
"""
import email
import imaplib
import logging
import os
import re
from email import policy
from html import unescape
from urllib.parse import unquote

from bs4 import BeautifulSoup

from .config import Config
from .run import now
from .seek import SEEK, _save

log = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
SENDER = "seekbusiness.com.au"
DAYS = 14  # each run looks back this far; listings already in the sheet are skipped

_LISTING = re.compile(r"https?://(?:www\.)?seekbusiness\.com\.au/(?:business|franchise)-listing/[^/?#\s\"'<>]+/(\d+)", re.I)
_PRICE = re.compile(r"^(\$|P\.?O\.?A|Price on|Negotiable|Contact)", re.I)
_LOCATION = re.compile(r"\b(WA|Western Australia|Perth)\b")
_LINK_WORDS = re.compile(r"^(view|view (this )?(business|listing|details)|more|read more|see more|enquire|save)\W*$", re.I)


def run(cfg: Config, store, limit: int | None = None, jitter: bool = False) -> list[dict]:
    address, password = os.environ.get("GMAIL_ADDRESS", "").strip(), os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not address or not password:
        log.info("SEEK alert reading is off until GMAIL_ADDRESS and GMAIL_APP_PASSWORD are set")
        return []
    stamp = now()
    stats = dict(started=stamp, source="seek alerts", on_site=0, new=0, updated=0, removed=0, fetched=0, backlog=0, errors=0, skipped=0, result="ok")
    rows = store.load(SEEK)
    changes: list[dict] = []
    try:
        for html in fetch_alerts(address, password):
            stats["fetched"] += 1
            listings = parse_alert(html)
            stats["on_site"] += len(listings)
            for raw in listings:
                key = f"seek:{raw['id']}"
                if key in rows:
                    continue  # already known; Check SEEK keeps it up to date
                _save(cfg, rows, raw, stamp, changes, stats)
    except imaplib.IMAP4.error as e:
        stats["result"] = f"Gmail refused the login ({e}). Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD."
    finally:
        store.save(SEEK, rows)
        store.log(changes, [stats])
    log.info("SEEK alerts: %d emails, %d listings in them, %d new", stats["fetched"], stats["on_site"], stats["new"])
    return [stats]


def fetch_alerts(address: str, password: str, days: int = DAYS) -> list[str]:
    """The HTML of every SEEK Business email from the last `days` days. Read-only: nothing is marked as read."""
    conn = imaplib.IMAP4_SSL(IMAP_HOST)
    try:
        conn.login(address, password)
        # All Mail also covers alerts that were archived; its name differs in some countries.
        for folder in ('"[Gmail]/All Mail"', '"[Google Mail]/All Mail"', "INBOX"):
            if conn.select(folder, readonly=True)[0] == "OK":
                break
        _, data = conn.search(None, "X-GM-RAW", f'"from:{SENDER} newer_than:{days}d"')
        bodies = []
        for number in (data[0] or b"").split():
            _, parts = conn.fetch(number, "(RFC822)")
            message = email.message_from_bytes(parts[0][1], policy=policy.default)
            part = message.get_body(preferencelist=("html", "plain"))
            if part is not None:
                bodies.append(part.get_content())
        return bodies
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def parse_alert(html: str) -> list[dict]:
    """Every SEEK listing linked from an alert email, with what the email says about it."""
    page = BeautifulSoup(html, "lxml")
    links: dict[str, dict] = {}
    for a in page.find_all("a", href=True):
        url, listing_id = listing_link(a["href"])
        if listing_id:
            links.setdefault(listing_id, {"url": url, "anchors": []})["anchors"].append(a)

    listings = []
    for listing_id, found in links.items():
        texts = [_text(a) for a in found["anchors"]]
        titles = [t for t in texts if t and not _LINK_WORDS.match(t)]
        title = max(titles, key=len) if titles else ""
        lines = [l for l in _lines(_card(found["anchors"][0], listing_id)) if l != title]
        listings.append({
            "id": listing_id,
            "url": found["url"],
            "title": title,
            "price_text": next((l for l in lines if _PRICE.match(l)), ""),
            "location": next((l for l in lines if _LOCATION.search(l) and not _PRICE.match(l)), ""),
            "industry": next((l for l in lines if " > " in l and not _LOCATION.search(l)), ""),
            "summary": max((l for l in lines if len(l) > 40 and not _LINK_WORDS.match(l)), key=len, default=""),
        })
    return listings


def listing_link(href: str) -> tuple[str, str]:
    """(listing URL, listing ID) from a link, including tracking links with the address encoded inside."""
    href = unescape(href or "")
    for candidate in (href, unquote(href), unquote(unquote(href))):
        match = _LISTING.search(candidate)
        if match:
            return match.group(0), match.group(1)
    return "", ""


def _card(anchor, listing_id: str):
    """The block of the email about one listing: the largest container around its link that doesn't reach another listing."""
    node = anchor
    while node.parent is not None and node.parent.name not in ("body", "html", "[document]"):
        parent = node.parent
        other = any(listing_link(a["href"])[1] not in ("", listing_id) for a in parent.find_all("a", href=True))
        if other or len(parent.get_text(" ", strip=True)) > 2000:
            break
        node = parent
    return node


def _lines(node) -> list[str]:
    return [" ".join(l.split()) for l in node.get_text("\n").splitlines() if l.strip()]


def _text(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split())
