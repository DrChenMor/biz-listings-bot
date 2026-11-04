"""The agent's records in the Deal desk database, and its files in the database's private storage."""
import os
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from . import AgentError

BUCKET = "deal-docs"


class Database:
    def __init__(self, url: str, key: str):
        self.http = httpx.Client(base_url=url, timeout=120, headers={"apikey": key, "Authorization": f"Bearer {key}"})

    @classmethod
    def connect(cls) -> "Database":
        url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise AgentError("Set SUPABASE_URL and SUPABASE_SERVICE_KEY first.")
        return cls(url, key)

    def rows(self, table: str, **filters) -> list[dict]:
        return _check(self.http.get(f"/rest/v1/{table}", params={"select": "*", **filters})).json()

    def add(self, table: str, row: dict) -> dict:
        return _check(self.http.post(f"/rest/v1/{table}", json=row, headers={"Prefer": "return=representation"})).json()[0]

    def change(self, table: str, row_id: int, **fields) -> None:
        _check(self.http.patch(f"/rest/v1/{table}", params={"id": f"eq.{row_id}"}, json=fields))

    def save(self, table: str, row: dict, key: str) -> None:
        _check(self.http.post(f"/rest/v1/{table}", params={"on_conflict": key}, json=row,
                              headers={"Prefer": "resolution=merge-duplicates,return=minimal"}))

    def upload(self, path: str, data: bytes, content_type: str) -> None:
        _check(self.http.post(f"/storage/v1/object/{BUCKET}/{quote(path)}", content=data,
                              headers={"Content-Type": content_type, "x-upsert": "true"}))

    def download(self, path: str) -> bytes:
        return _check(self.http.get(f"/storage/v1/object/{BUCKET}/{quote(path)}")).content

    def log(self, business_id: str, text: str) -> None:
        self.add("activity", {"business_id": business_id, "who": "Agent", "text": text})

    def set_status(self, enquiry: dict, status: str, detail: str = "", **fields) -> None:
        """Move an enquiry on, and record it in the business's history."""
        now = datetime.now(timezone.utc).isoformat()
        self.change("enquiries", enquiry["id"], status=status, detail=detail, updated_at=now, **fields)
        enquiry.update(status=status, detail=detail)
        self.log(enquiry["business_id"], f"{status}: {detail}" if detail else status)


def _check(response: httpx.Response) -> httpx.Response:
    if response.status_code >= 300:
        raise AgentError(f"The database refused that (HTTP {response.status_code}): {response.text[:300]}")
    return response
