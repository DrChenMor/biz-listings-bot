"""ABN Lookup: match each health business to its ABN record, and from that its owner where ABN Lookup shows one.

Uses the free ABN Lookup JSON web services, which need a key (GUID) from the Australian Business
Register. Matching is by name: a candidate must be an active ABN in the same state with a near-identical
name. Each match is graded so you know how far to trust it:

  High    same name and the ABN's postcode is the practice's postcode
  Medium  same name, different postcode (practices often register at the owner's home or head office),
          or a very close name in the same postcode
  Low     nothing close enough. The ABN columns stay empty; ABN notes names the closest candidate.

Owner names: ABN Lookup shows a person's name only for sole traders. For companies and trusts you need
an ASIC search, and partnerships show only the partnership's name; the Owner column says which applies.
"""
import difflib
import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode

from .config import Config
from .http import Blocked, PoliteClient
from .run import is_due, now

log = logging.getLogger(__name__)

NAMES_URL = "https://abr.business.gov.au/json/MatchingNames.aspx"
DETAILS_URL = "https://abr.business.gov.au/json/AbnDetails.aspx"

# ABN fields whose change is worth a row in the Changes tab: a new ABN or entity often means a new owner.
WATCHED = {"abn": "ABN", "abn_entity": "Registered entity (ABN)", "owner": "Owner name on ABN"}

_JSONP = re.compile(r"^[^(]*\((.*)\)[;\s]*$", re.S)
_IGNORED_WORDS = {"the", "pty", "ltd", "limited", "and", "co", "company", "trust", "trustee", "for", "ta", "as", "of"}
_CANDIDATES_TO_CHECK = 3
_NO_MATCH = dict.fromkeys(("abn", "abn_entity", "abn_entity_type", "owner", "abn_active_from", "abn_business_names", "abn_postcode"), "")


class AbnError(Exception):
    """ABN Lookup answered with an error message."""


class AbnLookup:
    def __init__(self, client: PoliteClient, guid: str):
        self.client = client
        self.guid = guid
        self.requests = 0

    def names(self, name: str, max_results: int = 20) -> list[dict]:
        data = self._call(NAMES_URL, name=name, maxResults=max_results)
        # Field names are read without regard to case, so "IsCurrent" and "isCurrent" both work.
        return [{k.lower(): v for k, v in n.items()} for n in data.get("Names") or []]

    def details(self, abn: str) -> dict:
        return self._call(DETAILS_URL, abn=abn)

    def _call(self, url: str, **params) -> dict:
        query = urlencode({**params, "callback": "c", "guid": self.guid})
        # The key travels in the URL, so logs show a label instead.
        response = self.client.get(f"{url}?{query}", label=f"ABN Lookup {url.rsplit('/', 1)[-1]}")
        self.requests += 1
        response.raise_for_status()
        match = _JSONP.match(response.text.strip())
        if not match:
            raise AbnError("ABN Lookup returned something unexpected")
        data = json.loads(match.group(1))
        if data.get("Message"):
            raise AbnError(data["Message"])
        return data


def sync(cfg: Config, businesses: dict, changes: list, guid: str) -> dict:
    stamp = now()
    stats = dict(started=stamp, source="abn", on_site=len(businesses), new=0, updated=0, removed=0, fetched=0, backlog=0, errors=0, result="ok")
    due = sorted(
        (row for row in businesses.values() if row.get("status") == "Listed" and is_due(row.get("abn_checked"), cfg.abn.recheck_days)),
        key=lambda row: row.get("abn_checked") or "",
    )
    batch = due[: cfg.abn.max_businesses_per_run]
    stats["backlog"] = len(due) - len(batch)
    lookup = AbnLookup(PoliteClient(cfg.user_agent, cfg.abn.delay_seconds), guid)
    log.info("ABN: matching %d businesses (%d waiting)", len(batch), stats["backlog"])
    for done, row in enumerate(batch, 1):
        try:
            found = match(lookup, row, cfg.state.upper())
        except AbnError as e:
            if "guid" in str(e).lower():
                stats["result"] = f"ABN Lookup didn't accept the key: {e}"
                stats["backlog"] += len(batch) - done + 1
                break
            log.warning("ABN Lookup error for %s: %s", row.get("name"), e)
            stats["errors"] += 1
            continue
        except Blocked as e:
            stats["result"] = f"blocked: {e}"
            stats["backlog"] += len(batch) - done + 1
            break
        except Exception as e:
            log.warning("ABN matching failed for %s: %s", row.get("name"), e)
            stats["errors"] += 1
            continue
        _apply(row, found, stamp, changes, stats)
        if done % 25 == 0:
            log.info("ABN: %d/%d businesses checked", done, len(batch))
    stats["fetched"] = lookup.requests
    return stats


def match(lookup: AbnLookup, row: dict, state: str) -> dict:
    """The ABN fields for one business (empty ABN fields when there's no confident match)."""
    queries = _queries(row.get("name", ""), row.get("suburb", ""))
    candidates: dict[str, dict] = {}
    for query in queries:
        for candidate in lookup.names(query):
            if str(candidate.get("state", "")).upper() != state or not _is_active(candidate):
                continue
            score = max(similarity(q, candidate.get("name", "")) for q in queries)
            abn = re.sub(r"\D", "", str(candidate.get("abn", "")))
            if abn and score > candidates.get(abn, {}).get("similarity", -1):
                candidates[abn] = {**candidate, "abn": abn, "similarity": score}
        if any(c["similarity"] >= 0.9 for c in candidates.values()):
            break  # no need to try the shorter name

    ranked = sorted(candidates.values(), key=lambda c: (c["similarity"] + (0.1 if c.get("postcode") == row.get("postcode") else 0), c.get("score") or 0), reverse=True)
    close = [c for c in ranked if c["similarity"] >= 0.8][:_CANDIDATES_TO_CHECK]
    if not close:
        best = ranked[0] if ranked else None
        note = f"Closest name on ABN Lookup: {best.get('name')} (ABN {format_abn(best['abn'])}, {best.get('postcode')})" if best else "No similar name on ABN Lookup"
        return {**_NO_MATCH, "abn_match": "Low", "abn_notes": note}

    # Several ABNs can carry the same name (say, a new owner's trust and the previous owner).
    # Prefer the one registered in the practice's postcode, then the most recently active one.
    checked = []
    for candidate in close:
        details = lookup.details(candidate["abn"])
        if str(details.get("AbnStatus", "")).lower().startswith("active"):
            checked.append((candidate, details))
    if not checked:
        return {**_NO_MATCH, "abn_match": "Low", "abn_notes": "Matching names found, but none with an active ABN"}
    checked.sort(key=lambda cd: (cd[1].get("AddressPostcode") == row.get("postcode"), cd[0]["similarity"], cd[1].get("AbnStatusEffectiveFrom") or ""), reverse=True)
    candidate, details = checked[0]

    same_postcode = details.get("AddressPostcode") == row.get("postcode")
    if candidate["similarity"] >= 0.9:
        grade = "High" if same_postcode else "Medium"
    else:
        grade = "Medium" if same_postcode else "Low"
    notes = []
    if not same_postcode and details.get("AddressPostcode"):
        notes.append(f"ABN location is {details['AddressPostcode']}.")
    active_from = details.get("AbnStatusEffectiveFrom") or ""
    if _recent(active_from, days=730):
        notes.append(f"ABN active only since {active_from}: possibly a recent change of owner.")
    for other, other_details in checked[1:]:
        notes.append(f"Also on ABN {format_abn(other['abn'])}: {other_details.get('EntityName')} ({other_details.get('EntityTypeName')}, since {other_details.get('AbnStatusEffectiveFrom')}).")
    if grade == "Low":
        closest = f"Closest: {details.get('EntityName')} (ABN {format_abn(candidate['abn'])}, {details.get('AddressPostcode')})."
        return {**_NO_MATCH, "abn_match": "Low", "abn_notes": " ".join([closest, *notes])}
    return {
        "abn": format_abn(candidate["abn"]),
        "abn_entity": details.get("EntityName", ""),
        "abn_entity_type": details.get("EntityTypeName", ""),
        "owner": owner(details),
        "abn_active_from": active_from,
        "abn_business_names": "; ".join(details.get("BusinessName") or []),
        "abn_postcode": details.get("AddressPostcode", ""),
        "abn_match": grade,
        "abn_notes": " ".join(notes),
    }


def owner(details: dict) -> str:
    name = (details.get("EntityName") or "").strip()
    kind = (details.get("EntityTypeName") or "").lower()
    if details.get("EntityTypeCode") == "IND" or "individual" in kind:
        if "," in name:
            family, given = name.split(",", 1)
            return f"{given.strip().title()} {family.strip().title()}"
        return name.title()
    if "partnership" in kind:
        return f"{name} (partners' names aren't shown on ABN Lookup)"
    if "trust" in kind:
        return "Not on ABN (trust: the trustee needs an ASIC search)"
    if "company" in kind:
        return "Not on ABN (company: directors need an ASIC company extract)"
    return ""


def similarity(a: str, b: str) -> float:
    """0-1 likeness of two business names, ignoring case, punctuation and words like Pty Ltd."""
    words_a, words_b = _words(a), _words(b)
    if not words_a or not words_b:
        return 0.0
    ratio = difflib.SequenceMatcher(None, " ".join(words_a), " ".join(words_b)).ratio()
    shorter, longer = sorted((set(words_a), set(words_b)), key=len)
    if len(shorter) >= 2 and shorter <= longer:
        ratio = max(ratio, 0.9)  # e.g. "Dental 359" within "Dental 359 Subiaco"
    return ratio


def format_abn(abn: str) -> str:
    digits = re.sub(r"\D", "", str(abn))
    return f"{digits[:2]} {digits[2:5]} {digits[5:8]} {digits[8:]}" if len(digits) == 11 else digits


def _apply(row: dict, found: dict, stamp: str, changes: list, stats: dict) -> None:
    diffs = [(label, row.get(f) or "", found.get(f) or "") for f, label in WATCHED.items() if str(row.get(f) or "") != str(found.get(f) or "")]
    first_time = not row.get("abn_checked")
    row.update(found, abn_checked=stamp)
    if first_time:
        stats["new"] += bool(found.get("abn"))
        return
    if diffs:
        row["last_changed"] = stamp
        stats["updated"] += 1
    for label, before, after in diffs:
        changes.append(dict(when=stamp, source="abn", listing_id=row.get("key", ""), title=row.get("name", ""), what=label, old=before, new=after, url=row.get("healthdirect_url", "")))


def _queries(name: str, suburb: str) -> list[str]:
    """The name as listed, plus the name without its suburb (e.g. "Jupiter Health Subiaco" -> "Jupiter Health")."""
    queries = [name.strip()]
    if suburb:
        shorter = re.sub(rf"[\s\-–,(]*\b{re.escape(suburb)}\b\)?\s*$", "", name, flags=re.I).strip()
        if shorter and shorter.lower() != name.strip().lower():
            queries.append(shorter)
    return queries


def _words(name: str) -> list[str]:
    text = re.sub(r"&", " and ", (name or "").lower())
    return [w for w in re.split(r"[^a-z0-9]+", text) if w and w not in _IGNORED_WORDS]


def _is_active(candidate: dict) -> bool:
    current = candidate.get("iscurrent", candidate.get("current", True))
    if str(current).lower() in ("false", "0", "n"):
        return False
    status = str(candidate.get("abnstatus", "")).lower()
    return not (status.startswith("cancel") or status == "0000000002")


def _recent(date: str, days: int) -> bool:
    try:
        return datetime.now() - datetime.strptime(date[:10], "%Y-%m-%d") < timedelta(days=days)
    except ValueError:
        return False
