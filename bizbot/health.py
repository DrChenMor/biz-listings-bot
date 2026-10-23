"""healthdirect: health practices suburb by suburb, from the public National Health Services Directory.

healthdirect publishes a sitemap of every "service type in suburb" search page (e.g. Dentists in
Subiaco). Each search page carries its results as JSON: the nearest 10 practices in full, plus map
pins for up to 30. The bot reads those pages for the suburbs in config.toml, opens a practice's own
page only for pins it doesn't already know, and keeps one row per practice per address, with every
service type it offers. When the ABN_GUID secret is set, each practice is then matched to its ABN.
"""
import json
import logging
import os
import re

from . import abn
from .config import Config
from .http import Blocked, PoliteClient, parse_xml
from .run import is_due, now, wait_randomly
from .store import Table

log = logging.getLogger(__name__)

SITEMAP_INDEX = "https://www.healthdirect.gov.au/australian-health-services/sitemaps/sitemap-index-health-services.xml"
BASE = "https://www.healthdirect.gov.au/australian-health-services"

HEALTH = Table(
    "Health businesses",
    [
        ("status", "Status"),
        ("name", "Business name"),
        ("sector", "Sector"),
        ("kind", "Type"),
        ("main_service", "Main service"),
        ("services", "All services listed"),
        ("address", "Address"),
        ("suburb", "Suburb"),
        ("postcode", "Postcode"),
        ("phone", "Phone"),
        ("email", "Email"),
        ("website", "Website"),
        ("abn", "ABN"),
        ("abn_entity", "Registered entity (ABN)"),
        ("abn_entity_type", "Entity type"),
        ("owner", "Owner name on ABN"),
        ("abn_active_from", "ABN active from"),
        ("abn_business_names", "Business names on ABN"),
        ("abn_postcode", "ABN postcode"),
        ("abn_match", "ABN match"),
        ("abn_notes", "ABN notes"),
        ("practitioners", "Practitioners"),
        ("practitioner_count", "Practitioner count"),
        ("billing", "Billing"),
        ("new_patients", "Accepts new patients"),
        ("latitude", "Latitude"),
        ("longitude", "Longitude"),
        ("map", "Map"),
        ("healthdirect_url", "healthdirect link"),
        ("first_seen", "First seen"),
        ("last_seen", "Last seen"),
        ("last_changed", "Last changed"),
        ("details_checked", "Details checked"),
        ("abn_checked", "ABN checked"),
        ("service_ids", "healthdirect service IDs"),
        ("organisation_id", "Organisation ID"),
        ("location_id", "Location ID"),
        ("key", "Key"),
    ],
    frozenset({"latitude", "longitude", "practitioner_count"}),
)
# Progress through healthdirect's search pages: which were read, and when.
HEALTH_PAGES = Table(
    "Health pages",
    [("suburb", "Suburb"), ("service", "Service type"), ("last_checked", "Last checked"), ("results", "Results nearby"), ("key", "URL")],
    frozenset({"results"}),
)

# Changes to these fields are written to the Changes tab.
WATCHED = {"name": "Business name", "address": "Address", "phone": "Phone", "email": "Email", "website": "Website", "status": "Status"}

# Service type wording -> sector, checked in this order. The first sector found among a practice's
# services also decides its "Main service".
SECTORS = [
    ("GP / medical centre", r"general practice|\bgp\b|medical cent"),
    ("Dental", r"dent|orthodont|periodont|prosthodont|endodont|oral"),
    ("Pharmacy", r"pharmac|chemist"),
    ("Hospital / day surgery", r"hospital|day surgery|emergency department"),
    ("Pathology & imaging", r"patholog|radiolog|imaging|x-ray|ultrasound|sample collection|\bmri\b|\bct\b"),
    ("Optical & hearing", r"optom|optic|hearing|audiolog"),
    ("Mental health", r"psycholog|psychiatr|counsel|mental|eating disorder|drug and alcohol|addiction"),
    ("Allied health", r"physio|chiropract|osteopath|podiatr|occupational therap|speech|dietit|dietetic|nutrition|exercise physiolog|myotherap|hand therap|child development|diabetes educ"),
    ("Complementary", r"naturopath|acupunct|chinese medicine|homeopath|massage|herbal"),
    ("Aged care", r"aged care|respite|residential"),
    ("Medical specialist", r"olog|surg|paediatric|obstetric|specialist|medicine|clinic|anaesthe|orthopaed|infectious|medical service"),
    # Last, so a practice that also runs a support group keeps its real sector. Usually not a business.
    ("Community / support", r"support group|information and referral|health promotion|advocacy|maternal|parenting|family support|helpline|disability aids"),
]
_PERSON = re.compile(r"^(dr|prof|professor|associate professor|a/prof|mr|mrs|ms|miss)\b\.?", re.I)

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_SEARCH_URL = re.compile(
    r"/australian-health-services/search/(?P<suburb>[a-z0-9-]+?-(?P<postcode>\d{4})-(?P<state>[a-z]+))/(?P<service>[a-z0-9-]+)/\d+$"
)
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def run(cfg: Config, store, limit: int | None = None, jitter: bool = False) -> list[dict]:
    if jitter:
        wait_randomly(cfg)
    businesses = store.load(HEALTH)
    pages = store.load(HEALTH_PAGES)
    changes: list[dict] = []
    runs: list[dict] = []
    try:
        client = PoliteClient(cfg.user_agent, cfg.health.delay_seconds)
        max_pages = cfg.health.max_pages_per_run if limit is None else limit
        runs.append(sync(cfg, client, businesses, pages, changes, max_pages))
        guid = os.environ.get("ABN_GUID", "").strip()
        if guid:
            runs.append(abn.sync(cfg, businesses, changes, guid))
        else:
            log.info("ABN matching is off until the ABN_GUID secret is set")
    finally:
        store.save(HEALTH, businesses)
        store.save(HEALTH_PAGES, pages)
        store.log(changes, runs)
    return runs


def sync(cfg: Config, client: PoliteClient, businesses: dict, pages: dict, changes: list, limit: int) -> dict:
    stamp = now()
    stats = dict(started=stamp, source="healthdirect", on_site=0, new=0, updated=0, removed=0, fetched=0, backlog=0, errors=0, result="ok")
    try:
        targets = search_pages(client, cfg)
    except Blocked as e:
        stats["result"] = f"blocked: {e}"
        return stats
    except Exception as e:
        log.error("Couldn't read healthdirect's page index: %s", e)
        stats["result"] = f"page index unavailable: {e}"
        return stats
    stats["on_site"] = len(targets)
    for page in targets:
        pages.setdefault(page["key"], {**page, "last_checked": "", "results": None})

    target_keys = {t["key"] for t in targets}
    due = sorted(
        (p for p in pages.values() if p["key"] in target_keys and is_due(p.get("last_checked"), cfg.health.recheck_days)),
        key=lambda p: p.get("last_checked") or "",
    )
    log.info("healthdirect: %d search pages for your suburbs, %d due now", len(targets), len(due))
    opened = finished = 0
    for page in due:
        if opened >= limit:
            break
        try:
            used, complete = _read_search_page(cfg, client, page, businesses, changes, stats, stamp, limit - opened)
        except Blocked as e:
            log.error("healthdirect started refusing pages, stopping: %s", e)
            stats["result"] = f"blocked: {e}"
            break
        except Exception as e:
            log.warning("Could not read %s: %s", page["key"], e)
            stats["errors"] += 1
            continue
        opened += used
        finished += complete
        if finished and finished % 10 == 0 and complete:
            log.info("healthdirect: %d/%d search pages read, %d pages opened", finished, len(due), opened)
    stats["fetched"] = opened
    stats["backlog"] = len(due) - finished

    # Practices no search page has shown for two check cycles have probably closed or left the directory.
    for row in businesses.values():
        if row.get("status") == "Listed" and is_due(row.get("last_seen"), 2 * cfg.health.recheck_days):
            _record(changes, row, stamp, "Status", "Listed", "Not seen recently")
            row.update(status="Not seen recently", last_changed=stamp)
            stats["removed"] += 1
    return stats


def search_pages(client: PoliteClient, cfg: Config) -> list[dict]:
    """Every healthdirect search page for the configured suburbs and service types."""
    state = cfg.state.upper()
    index = parse_xml(client.get(SITEMAP_INDEX), "healthdirect's page index")
    sitemaps = [
        loc.text.strip()
        for loc in index.iter(f"{_SITEMAP_NS}loc")
        if re.search(rf"-{state}(?:-\d+)?\.xml$", loc.text.strip())
    ]
    pages = []
    for sitemap in sitemaps:
        for loc in parse_xml(client.get(sitemap), "healthdirect's page index").iter(f"{_SITEMAP_NS}loc"):
            match = _SEARCH_URL.search(loc.text.strip())
            if not match or not _is_target(cfg, match["suburb"], match["postcode"]):
                continue
            if cfg.health.service_types and match["service"] not in cfg.health.service_types:
                continue
            pages.append({"key": loc.text.strip(), "suburb": match["suburb"], "service": match["service"]})
    return pages


def parse_page(html: str) -> dict:
    match = _NEXT_DATA.search(html)
    if not match:
        return {}
    return json.loads(match.group(1)).get("props", {}).get("pageProps", {})


def business_fields(record: dict) -> dict | None:
    """One healthdirect service record -> the fields of its business row."""
    organisation = record.get("organisation") or {}
    location = record.get("location") or {}
    if not organisation.get("id") or not location.get("id"):
        return None
    place = location.get("physicalLocation") or {}
    geocode = place.get("geocode") or {}
    suburb = ((place.get("suburb") or {}).get("label") or "").title()
    contacts = {}
    for contact in sorted(record.get("contacts") or [], key=lambda c: -(c.get("priority") or 0)):
        kind = ((contact.get("valueType") or {}).get("label") or "").lower()
        if contact.get("value") and kind in ("phone", "email", "website"):
            contacts.setdefault(kind, []).append(contact["value"].strip())
    service = ", ".join(t.get("label", "") for t in record.get("serviceType") or [] if t.get("label"))
    lat, lng = geocode.get("latitude"), geocode.get("longitude")
    return {
        "key": f"hd:{organisation['id']}:{location['id']}",
        "name": organisation.get("name", "").strip(),
        "address": ", ".join(x for x in (place.get("addressLine1"), place.get("addressLine2")) if x),
        "suburb": suburb,
        "postcode": place.get("postcode", ""),
        "phones": contacts.get("phone", []),
        "emails": [e.lower() for e in contacts.get("email", [])],
        "websites": [_website(w) for w in contacts.get("website", [])],
        "billing": _billing(record.get("billingOptions") or []),
        "new_patients": "Yes" if record.get("acceptsNewPatients") else "",
        "latitude": lat,
        "longitude": lng,
        "map": f"https://www.google.com/maps/search/?api=1&query={lat},{lng}" if lat and lng else "",
        "organisation_id": organisation["id"],
        "location_id": location["id"],
        "service": service,
        "service_id": record.get("id", ""),
        "practitioner_names": [n for n in (_practitioner_name(p) for p in record.get("practitioners") or []) if n],
    }


def merge(businesses: dict, fields: dict, stamp: str, changes: list, stats: dict, url: str = "") -> str:
    """Add one service record to its business row; returns the row's key."""
    key = fields["key"]
    old = businesses.get(key)
    row = dict(old or {})
    services = _items(row.get("services")) | ({fields["service"]} if fields["service"] else set())
    practitioners = _items(row.get("practitioners")) | set(fields["practitioner_names"])
    service_ids = set((row.get("service_ids") or "").split()) | {fields["service_id"]}
    for field, values in (("phone", fields["phones"]), ("email", fields["emails"]), ("website", fields["websites"])):
        # A practice can list different contacts per service; keep them all, the first one first.
        # Numbers are compared by their digits, so "08 6490 9076" and "08 64909076" count once.
        existing = [v for v in (row.get(field) or "").split("; ") if v]
        same = (lambda v: re.sub(r"\D", "", v)) if field == "phone" else (lambda v: v)
        for value in values:
            if same(value) not in {same(e) for e in existing}:
                existing.append(value)
        row[field] = "; ".join(existing)
    for field in ("name", "address", "suburb", "postcode", "latitude", "longitude", "map", "organisation_id", "location_id", "key"):
        row[field] = fields[field]
    row["billing"] = fields["billing"] or row.get("billing", "")
    row["new_patients"] = fields["new_patients"] or row.get("new_patients", "")
    row["services"] = "; ".join(sorted(services))
    row["practitioners"] = "; ".join(sorted(practitioners))
    row["practitioner_count"] = len(practitioners) or None
    row["service_ids"] = " ".join(sorted(service_ids))
    row["main_service"], row["sector"] = main_service(services, row["name"])
    is_person = _PERSON.match(row["name"]) or row["name"].lower() in {p.lower() for p in practitioners}
    row["kind"] = "Hospital / day surgery" if row["sector"].startswith("Hospital") else (
        "Individual practitioner" if is_person else "Practice / clinic"
    )
    row["healthdirect_url"] = row.get("healthdirect_url") or url
    row.update(status="Listed", last_seen=stamp, details_checked=stamp)
    if old is None:
        row["first_seen"] = row["last_changed"] = stamp
        stats["new"] += 1
        _record(changes, row, stamp, "New business", "", row["services"])
    elif old.get("first_seen") != stamp:  # a row added earlier in this same run isn't "changed"
        diffs = [(label, old.get(f) or "", row.get(f) or "") for f, label in WATCHED.items() if str(old.get(f) or "") != str(row.get(f) or "")]
        if diffs:
            row["last_changed"] = stamp
            stats["updated"] += 1
        for label, before, after in diffs:
            _record(changes, row, stamp, label, before, after)
    businesses[key] = row
    return key


def main_service(services: set[str], name: str = "") -> tuple[str, str]:
    """The practice's most telling service and its sector, e.g. ("Dentists", "Dental")."""
    if re.search(r"\bhospital\b|day surgery", name, re.I):
        return (sorted(services)[0] if services else ""), "Hospital / day surgery"
    for sector, pattern in SECTORS:
        for service in sorted(services):
            if re.search(pattern, service, re.I):
                return service, sector
    return (sorted(services)[0] if services else ""), "Other"


def _read_search_page(cfg: Config, client: PoliteClient, page: dict, businesses: dict, changes: list, stats: dict, stamp: str, budget: int) -> tuple[int, bool]:
    """Read one search page and the practice pages it needs.

    Returns how many pages were opened, and whether the page was finished. A page left unfinished
    because the run's page budget ran out is read again next run.
    """
    data = parse_page(client.get(page["key"]).text)
    opened = 1
    results = data.get("healthcareServices") or {}
    service_label = ((data.get("serviceType") or {}).get("valueType") or {}).get("label", "")
    full_ids = set()
    for record in results.get("services") or []:
        full_ids.add(record.get("id"))
        _merge_record(cfg, businesses, record, stamp, changes, stats, _record_url(record, page["service"], cfg.state))

    by_service_id = {sid: key for key, row in businesses.items() for sid in (row.get("service_ids") or "").split()}
    by_place = {(_norm(row.get("name")), _spot(row.get("latitude"), row.get("longitude"))): key for key, row in businesses.items()}
    for pin in data.get("mapPins") or []:
        if pin.get("id") in full_ids or not _is_target(cfg, _slug(pin.get("suburbLabel", "")), str(pin.get("postcode", ""))):
            continue
        spot = _spot((pin.get("location") or {}).get("latitude"), (pin.get("location") or {}).get("longitude"))
        key = by_service_id.get(pin["id"]) or by_place.get((_norm(pin.get("organisationName")), spot))
        if key and not is_due(businesses[key].get("details_checked"), cfg.health.recheck_days):
            # Known practice with recent details: note the service type without opening its page.
            row = businesses[key]
            row["last_seen"] = stamp
            if service_label and service_label not in _items(row.get("services")):
                row["services"] = "; ".join(sorted(_items(row["services"]) | {service_label}))
                row["main_service"], row["sector"] = main_service(_items(row["services"]), row.get("name", ""))
            row["service_ids"] = " ".join(sorted(set(row.get("service_ids", "").split()) | {pin["id"]}))
            continue
        if opened >= budget:
            return opened, False
        url = _practice_url(pin, page["service"])
        detail = parse_page(client.get(url).text).get("healthcareService")
        opened += 1
        if detail:
            _merge_record(cfg, businesses, detail, stamp, changes, stats, url)
    page.update(last_checked=stamp, results=results.get("count"))
    return opened, True


def _merge_record(cfg: Config, businesses: dict, record: dict, stamp: str, changes: list, stats: dict, url: str = "") -> None:
    fields = business_fields(record)
    if fields and _is_target(cfg, _slug(fields["suburb"]), fields["postcode"]):
        merge(businesses, fields, stamp, changes, stats, url)


def _is_target(cfg: Config, suburb: str, postcode: str) -> bool:
    """suburb is a slug such as "subiaco" or "subiaco-6008-wa"."""
    name = re.sub(rf"-{postcode}(-[a-z]+)?$", "", suburb) if postcode else suburb
    for target in cfg.health.suburbs:
        match = re.match(r"^(.*)-(\d{4})(?:-[a-z]+)?$", target)
        if match and match.group(1) == name and match.group(2) == postcode:
            return True
    return postcode.isdigit() and any(low <= int(postcode) <= high for low, high in cfg.health.postcode_ranges)


def _practice_url(pin: dict, service_slug: str) -> str:
    suburb = f"{_slug(pin.get('suburbLabel', ''))}-{pin.get('postcode', '')}-{pin.get('stateLabel', '').lower()}"
    return f"{BASE}/healthcare-service/{suburb}/{_slug(pin.get('organisationName', '')) or 'practice'}/{service_slug}/{pin['id']}"


def _record_url(record: dict, service_slug: str, state: str) -> str:
    place = (record.get("location") or {}).get("physicalLocation") or {}
    pin = {
        "id": record.get("id", ""),
        "suburbLabel": (place.get("suburb") or {}).get("label", ""),
        "postcode": place.get("postcode", ""),
        "stateLabel": state,
        "organisationName": (record.get("organisation") or {}).get("name", ""),
    }
    return _practice_url(pin, service_slug)


def _practitioner_name(practitioner: dict) -> str:
    for key in ("name", "displayName", "fullName", "practitionerName"):
        value = practitioner.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            text = value.get("text") or " ".join(str(value.get(p, "")) for p in ("prefix", "given", "family") if value.get(p))
            if text.strip():
                return text.strip()
    nested = practitioner.get("practitioner")
    return _practitioner_name(nested) if isinstance(nested, dict) else ""


def _billing(options: list) -> str:
    labels = {((o.get("valueType") or {}).get("label") or "") for o in options if str(o.get("value")).lower() in ("yes", "true")}
    if any("bulk" in l.lower() and "billing" in l.lower() and "some" not in l.lower() for l in labels):
        return "Bulk billing"
    if any("bulk" in l.lower() for l in labels):
        return "Some bulk billing"
    return "Fees apply" if any("fee" in l.lower() for l in labels) else ""


def _website(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.strip().lower()).rstrip("/")


def _record(changes: list, row: dict, stamp: str, what: str, old, new) -> None:
    changes.append(dict(when=stamp, source="healthdirect", listing_id=row.get("key", ""), title=row.get("name", ""), what=what, old=old, new=new, url=row.get("healthdirect_url", "")))


def _items(text) -> set[str]:
    return {item for item in (text or "").split("; ") if item}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _spot(lat, lng) -> tuple:
    try:
        return round(float(lat), 4), round(float(lng), 4)
    except (TypeError, ValueError):
        return None, None
