"""Who the agent says the buyer is. It states only what is in this profile.

Test mode uses a made-up buyer. Live mode reads BUYER_PROFILE, a JSON object with name, email, phone and postcode, and
optionally company, abn and address. The signature is a PNG in BUYER_SIGNATURE_FILE or, base64 encoded, BUYER_SIGNATURE_B64.
"""
import base64
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import AgentError

REQUIRED = ("name", "email", "phone", "postcode")


@dataclass(frozen=True)
class Buyer:
    name: str
    email: str
    phone: str
    postcode: str
    company: str = ""
    abn: str = ""
    address: str = ""
    signature: bytes | None = None

    def address_for(self, enquiry_id: int) -> str:
        """The buyer's email with the enquiry in it, so a reply finds its way back: deals+e12@gmail.com."""
        local, domain = self.email.split("@", 1)
        return f"{local}+e{enquiry_id}@{domain}"

    def form_fields(self, enquiry_id: int) -> dict:
        first, _, last = self.name.partition(" ")
        return {"name": self.name, "first_name": first, "last_name": last or first, "email": self.address_for(enquiry_id),
                "phone": self.phone, "postcode": self.postcode}

    def signing_values(self) -> dict:
        """What can be written on an NDA. The signature itself is drawn separately."""
        today = datetime.now(ZoneInfo("Australia/Perth"))
        return {"name": self.name, "date": f"{today.day} {today:%B %Y}", "company": self.company, "abn": self.abn,
                "address": self.address, "phone": self.phone, "email": self.email}


TEST_BUYER = Buyer("Test Buyer", "test.buyer@example.com", "0400000000", "6000")


def load(live: bool) -> Buyer:
    if not live:
        return TEST_BUYER
    try:
        profile = json.loads(os.environ.get("BUYER_PROFILE") or "null")
    except ValueError:
        raise AgentError("BUYER_PROFILE isn't valid JSON.") from None
    missing = [field for field in REQUIRED if not (profile or {}).get(field)]
    if missing:
        raise AgentError(f"BUYER_PROFILE needs {', '.join(missing)}.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+", profile["email"]):
        raise AgentError("BUYER_PROFILE's email doesn't look like an email address.")
    known = {key: str(profile[key]) for key in (*REQUIRED, "company", "abn", "address") if profile.get(key)}
    return Buyer(**known, signature=_signature())


def _signature() -> bytes | None:
    if path := os.environ.get("BUYER_SIGNATURE_FILE"):
        return Path(path).expanduser().read_bytes()
    if encoded := os.environ.get("BUYER_SIGNATURE_B64"):
        return base64.b64decode(encoded)
    return None
