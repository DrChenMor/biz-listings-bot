"""A slow, polite HTTP client: obeys robots.txt, pauses randomly, and stops when a site says no."""
import logging
import random
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)


class Blocked(Exception):
    """The site refused us (403/429). The bot stops that source for this run instead of pushing on."""


class PoliteClient:
    def __init__(self, user_agent: str, delay_range: tuple[float, float]):
        self.delay_range = delay_range
        self.http = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Language": "en-AU,en;q=0.9"},
            timeout=30,
            follow_redirects=True,
        )
        self._robots: dict[str, RobotFileParser] = {}
        self._last_request = 0.0

    def get(self, url: str, retries: int = 3) -> httpx.Response:
        if not self._allowed(url):
            raise PermissionError(f"robots.txt does not allow {url}")
        for attempt in range(1, retries + 1):
            self._pause()
            try:
                response = self.http.get(url)
            except httpx.TransportError as e:
                log.warning("Network error on %s (%s), attempt %d/%d", url, e, attempt, retries)
                time.sleep(10 * attempt)
                continue
            if response.status_code in (403, 429):
                raise Blocked(f"HTTP {response.status_code} from {url}")
            if response.status_code >= 500:
                log.warning("HTTP %d on %s, attempt %d/%d", response.status_code, url, attempt, retries)
                time.sleep(10 * attempt)
                continue
            return response
        raise RuntimeError(f"Gave up on {url} after {retries} attempts")

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        robots = self._robots.get(base)
        if robots is None:
            robots = RobotFileParser()
            response = self.http.get(base + "/robots.txt")
            if response.status_code in (401, 403):
                robots.disallow_all = True
            elif response.status_code >= 400:
                robots.allow_all = True
            else:
                robots.parse(response.text.splitlines())
            self._robots[base] = robots
        return robots.can_fetch(self.http.headers["User-Agent"], url)

    def _pause(self) -> None:
        wait = random.uniform(*self.delay_range) - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
