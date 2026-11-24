"""The real business name, found for free in a pipeline business's Drive folder.

Two sources, no AI:
- An ABN printed in a document (an IM, P&L, lease or letterhead): ABN Lookup gives the entity and trading names.
- File names Tom already wrote the business into, like "Balance Sheet 2026 - N24 Impex Pty Ltd.pdf".

Everything found is a suggestion on the website: Accept puts it on the card, Ignore hides it. Each file is read once,
and again only when it changes. An ABN found in two businesses' folders belongs to a broker or an accountant, so it
is skipped.
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import PurePath

from .abn import AbnLookup
from .broker.database import Database
from .config import Config
from .http import PoliteClient

log = logging.getLogger(__name__)

DRIVE = "https://www.googleapis.com/drive/v3/files"
FOLDER = "application/vnd.google-apps.folder"
GOOGLE_DOC = "application/vnd.google-apps.document"
_PAGES = 12  # an ABN sits on the first pages or the letterhead; long PDFs aren't read to the end

_ABN = re.compile(r"(?<!\d)(\d{2}\s?\d{3}\s?\d{3}\s?\d{3})(?!\d)")
_ABN_LABEL = re.compile(r"\bA\.?B\.?N\.?\b", re.I)
_ENTITY = re.compile(r"\b((?:[A-Z0-9][\w&'.]*\s+){0,6}?[A-Z0-9][\w&'.]*\s+(?:Pty\.?\s*Ltd|Pty\.?\s*Limited|Limited|Ltd))\b\.?")
# Words that say what a document is, not whose it is.
_DOC_WORDS = re.compile(
    r"\b(business\s+profile|information\s+memorandum|profit\s*(?:&|and)\s*loss|p\s*&\s*l|balance\s+sheet|asset\s+(?:list|schedule|register)"
    r"|financials?|financial\s+statements?|tax\s+returns?|bas|lease|nda|confidentiality\s+agreement|im|teaser|summary|report"
    r"|fy\s?\d{2,4}|v\d+|draft|final|copy|scan(?:ned)?|\d{4}(?:[-_]\d{2,4})?)\b", re.I)
_PROFILE_WORDS = re.compile(r"\b(business\s+profile|information\s+memorandum)\b", re.I)
# Names that belong to the people selling the business for someone else, not to the business.
_NOT_THE_BUSINESS = re.compile(r"broker|business\s+sales|realty|real\s+estate|accountant|accounting|lawyers?|legal|advisory", re.I)
# A shop's address in a lease's file name is not the business's name.
_ADDRESS = re.compile(r"^(shop|unit|suite|lot|level)\b|\d+\s*,?\s*\d*\s+\w+\s+(rd|road|st|street|ave|avenue|hwy|highway|dr|drive|pde|parade|cres|ct|pl|way|lane|blvd)\b", re.I)


def valid_abn(digits: str) -> bool:
    """The ABN checksum: take 1 from the first digit, weight the 11 digits, and the sum divides by 89."""
    if len(digits) != 11 or not digits.isdigit() or digits[0] == "0":
        return False
    weights = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)
    numbers = [int(digits[0]) - 1] + [int(d) for d in digits[1:]]
    return sum(w * n for w, n in zip(weights, numbers)) % 89 == 0


def abns_in(text: str) -> list[str]:
    """Valid ABNs written in a document, labelled ones ("ABN 12 345 678 901") first, each once."""
    labelled, other = [], []
    for match in _ABN.finditer(text or ""):
        digits = re.sub(r"\D", "", match.group(1))
        if not valid_abn(digits):
            continue
        before = text[max(0, match.start() - 25): match.start()]
        (labelled if _ABN_LABEL.search(before) else other).append(digits)
    return list(dict.fromkeys(labelled + other))


def _tidy(text: str) -> str:
    return re.sub(r"\s{2,}", " ", re.sub(r"[_]+", " ", text)).strip(" -–—,.()")


def names_from_file(file_name: str) -> list[str]:
    """Business names Tom wrote into a file name. Only clear cases: a company name, or the part beside a document type."""
    stem = _tidy(PurePath(file_name).stem)
    found = [_tidy(m.group(1)) for m in _ENTITY.finditer(stem)]
    parts = [p for p in (_tidy(p) for p in re.split(r"\s+[-–—|]\s+", stem)) if p]
    document_parts = [p for p in parts if not _tidy(_DOC_WORDS.sub(" ", p))]
    if len(parts) > 1 and document_parts:
        # "Business Profile - Studio Pilates Applecross": the part beside the one that only says what the document is.
        for part in parts:
            cleaned = _tidy(_DOC_WORDS.sub(" ", part))
            if part not in document_parts and len(cleaned.split()) >= 2:
                found.append(cleaned)
    elif _PROFILE_WORDS.search(stem):
        # "V3 Core Focus Pilates Business Profile": the words left once the document type and version are gone.
        cleaned = _tidy(_DOC_WORDS.sub(" ", stem))
        if len(cleaned.split()) >= 2:
            found.append(cleaned)
    return [n for n in dict.fromkeys(found) if not _NOT_THE_BUSINESS.search(n) and not _ADDRESS.search(n)]


def readable(name: str) -> str:
    """ABN Lookup writes names in capitals: VASSE VALLEY HEMP FARM PTY LTD becomes Vasse Valley Hemp Farm Pty Ltd."""
    if name != name.upper():
        return name.strip()
    words = []
    for word in name.split():
        short = word.strip(".,")
        words.append(word if (len(short) <= 3 and any(c.isdigit() for c in short)) else word.capitalize())
    return re.sub(r"\bPty\b", "Pty", " ".join(words)).replace(" & ", " & ")


def _same(a: str, b: str) -> bool:
    simple = lambda s: re.sub(r"[^a-z0-9]", "", s.lower().replace("pty ltd", "").replace("limited", ""))
    return bool(a) and bool(b) and simple(a) == simple(b)


class Drive:
    """The Acquisitions folders, read as the bots' robot account (Viewer only)."""

    def __init__(self, credentials: dict):
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2.service_account import Credentials

        scope = ["https://www.googleapis.com/auth/drive.readonly"]
        self.http = AuthorizedSession(Credentials.from_service_account_info(credentials, scopes=scope))

    def files(self, folder_id: str, depth: int = 1) -> list[dict]:
        """Files in a folder and one level of folders inside it."""
        safe_id = re.sub(r"[^\w-]", "", folder_id)
        params = {"q": f"'{safe_id}' in parents and trashed = false",
                  "fields": "files(id,name,mimeType,modifiedTime)", "pageSize": 200}
        response = self.http.get(DRIVE, params=params, timeout=60)
        response.raise_for_status()
        found = []
        for f in response.json().get("files", []):
            if f["mimeType"] == FOLDER:
                if depth:
                    found += self.files(f["id"], depth - 1)
            else:
                found.append(f)
        return found

    def text(self, f: dict) -> str:
        """The words in a PDF, a Google Doc or a text file. Other kinds are only judged by their name."""
        if f["mimeType"] == GOOGLE_DOC:
            response = self.http.get(f"{DRIVE}/{f['id']}/export", params={"mimeType": "text/plain"}, timeout=60)
            return response.text if response.ok else ""
        if f["mimeType"] == "application/pdf" or f["name"].lower().endswith(".pdf"):
            response = self.http.get(f"{DRIVE}/{f['id']}", params={"alt": "media"}, timeout=120)
            if not response.ok:
                return ""
            from pypdf import PdfReader

            try:
                reader = PdfReader(io.BytesIO(response.content))
                return "\n".join((page.extract_text() or "") for page in reader.pages[:_PAGES])
            except Exception as e:  # a damaged or locked PDF is skipped, not fatal
                log.info("Couldn't read %s: %s", f["name"], e)
                return ""
        if f["mimeType"].startswith("text/"):
            response = self.http.get(f"{DRIVE}/{f['id']}", params={"alt": "media"}, timeout=60)
            return response.text if response.ok else ""
        return ""


def run(cfg: Config, credentials: dict, guid: str | None) -> int:
    """Look for names in the folders of businesses in the pipeline. Returns how many new suggestions were made."""
    db = Database.connect()
    drive = Drive(credentials)
    tracked = [t for t in db.rows("tracking", select="business_id,drive_folder_id,display_name,archived_at,stage",
                                  drive_folder_id="not.is.null")
               if not t["archived_at"] and t["stage"] != "Passed"]
    if not tracked:
        log.info("No pipeline business has a Drive folder yet")
        return 0
    ids = ",".join(f'"{t["business_id"]}"' for t in tracked)
    listings = {b["id"]: b for b in db.rows("businesses", select="id,name,seller", id=f"in.({ids})")}
    scanned = {(s["file_id"], s["business_id"]): s for s in db.rows("doc_scans", select="file_id,business_id,modified_time,abns")}
    known = {(s["business_id"], s["name"].lower()) for s in db.rows("name_suggestions", select="business_id,name")}

    suggestions: list[dict] = []
    abn_files: dict[str, list[tuple[str, dict]]] = {}  # ABN -> (business, file) where it was printed, old and new
    new_abns: set[str] = set()  # only ABNs in files read this time are looked up; older ones already were
    for t in tracked:
        business = t["business_id"]
        try:
            files = drive.files(t["drive_folder_id"])
        except Exception as e:
            log.warning("Couldn't list the folder for %s: %s", business, e)
            continue
        for f in files:
            before = scanned.get((f["id"], business))
            for abn in (before or {}).get("abns") or []:
                abn_files.setdefault(abn, []).append((business, f))
            if before and before.get("modified_time") == f["modifiedTime"]:
                continue
            for name in names_from_file(f["name"]):
                suggestions.append({"business_id": business, "name": name, "source": "File name",
                                    "evidence": f"The file name: {f['name']}", "file_id": f["id"], "file_name": f["name"]})
            abns = abns_in(drive.text(f))
            for abn in abns:
                abn_files.setdefault(abn, []).append((business, f))
                new_abns.add(abn)
            db.save("doc_scans", {"file_id": f["id"], "business_id": business, "modified_time": f["modifiedTime"], "abns": abns},
                    "file_id,business_id")

    lookup = AbnLookup(PoliteClient(cfg.user_agent, cfg.abn.delay_seconds), guid) if guid else None
    if not lookup and abn_files:
        log.info("ABN_GUID isn't set, so %d ABNs found in documents weren't looked up", len(abn_files))
    for abn in sorted(new_abns) if lookup else []:
        places = abn_files[abn]
        owners = {business for business, _ in places}
        if len(owners) > 1:
            log.info("ABN %s is in %d businesses' folders (a broker or accountant), skipped", abn, len(owners))
            continue
        business, f = places[0]
        try:
            details = lookup.details(abn)
        except Exception as e:  # ABN Lookup down or the ABN unknown: try again when the file changes
            log.info("ABN Lookup couldn't give %s: %s", abn, e)
            continue
        entity = (details.get("EntityName") or "").strip()
        trading = [n.strip() for n in details.get("BusinessName") or [] if isinstance(n, str) and n.strip()]
        seller = (listings.get(business) or {}).get("seller") or ""
        # A person's name ("SMITH, JANE") or a trust's ("The Trustee for ...") says who owns it, not what it's called.
        owner_only = not entity or "," in entity or entity.lower().startswith("the trustee for")
        for raw in trading + ([] if owner_only else [entity]):
            name = readable(raw)
            if _NOT_THE_BUSINESS.search(name) or (seller and _same(name, seller)):
                continue
            kind = "trading name" if raw in trading else "registered entity"
            suggestions.append({"business_id": business, "name": name, "source": "ABN Lookup", "abn": abn,
                                "evidence": f"ABN {abn} is printed in {f['name']}; ABN Lookup lists this {kind}"
                                            + (f" ({entity})" if name != entity and entity else ""),
                                "file_id": f["id"], "file_name": f["name"]})

    made = 0
    for s in suggestions:
        t = next(t for t in tracked if t["business_id"] == s["business_id"])
        listing = listings.get(s["business_id"]) or {}
        key = (s["business_id"], s["name"].lower())
        if key in known or _same(s["name"], t.get("display_name") or "") or _same(s["name"], listing.get("name") or ""):
            continue
        db.add("name_suggestions", s)
        known.add(key)
        made += 1
        log.info("%s: suggested %s (%s)", s["business_id"], s["name"], s["source"])
    log.info("Name finder: %d businesses with folders, %d new suggestions", len(tracked), made)
    return made
