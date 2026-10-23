"""Settings from config.toml."""
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class HealthConfig:
    suburbs: list[str]
    postcode_ranges: list[tuple[int, int]]
    service_types: list[str]
    recheck_days: int
    max_pages_per_run: int
    delay_seconds: tuple[float, float]


@dataclass
class SeekConfig:
    searches: list[str]
    pages: int
    details: int
    delay_seconds: tuple[float, float]


@dataclass
class AbnConfig:
    recheck_days: int
    max_businesses_per_run: int
    delay_seconds: tuple[float, float]


@dataclass
class Config:
    max_listings_per_run: int
    delay_seconds: tuple[float, float]
    start_jitter_minutes: tuple[float, float]
    user_agent: str
    state: str
    perth_postcodes: list[tuple[int, int]]
    # Matches industries/categories every bot skips (food businesses); None when the list is empty.
    exclude: re.Pattern | None
    sources: list[str]
    seek: SeekConfig
    health: HealthConfig
    abn: AbnConfig

    def excluded(self, *texts: str) -> str:
        """The excluded word found in these texts, or "" if none."""
        match = self.exclude.search(" ".join(t for t in texts if t)) if self.exclude else None
        return match.group(0) if match else ""


def load(path: Path = ROOT / "config.toml") -> Config:
    raw = tomllib.loads(Path(path).read_text())
    bot, filters, seek, health, abn = raw["bot"], raw["filters"], raw["seek"], raw["health"], raw["abn"]
    return Config(
        max_listings_per_run=bot["max_listings_per_run"],
        delay_seconds=tuple(bot["delay_seconds"]),
        start_jitter_minutes=tuple(bot["start_jitter_minutes"]),
        user_agent=bot["user_agent"],
        state=filters["state"].lower(),
        perth_postcodes=[tuple(r) for r in filters["perth_postcodes"]],
        exclude=_word_pattern(filters.get("exclude_categories", [])),
        sources=[name for name, s in raw["sources"].items() if s.get("enabled", True)],
        seek=SeekConfig(
            searches=list(seek["searches"]),
            pages=seek["pages"],
            details=seek["details"],
            delay_seconds=tuple(seek["delay_seconds"]),
        ),
        health=HealthConfig(
            suburbs=[s.lower() for s in health["suburbs"]],
            postcode_ranges=[tuple(r) for r in health["postcode_ranges"]],
            service_types=[s.lower() for s in health["service_types"]],
            recheck_days=health["recheck_days"],
            max_pages_per_run=health["max_pages_per_run"],
            delay_seconds=tuple(health["delay_seconds"]),
        ),
        abn=AbnConfig(
            recheck_days=abn["recheck_days"],
            max_businesses_per_run=abn["max_businesses_per_run"],
            delay_seconds=tuple(abn["delay_seconds"]),
        ),
    )


def _word_pattern(words: list[str]) -> re.Pattern | None:
    """Whole words, plural or not: "cafe" matches "Cafe" and "Cafes" but "bar" doesn't match "Barber"."""
    if not words:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")(?:s|es)?\b", re.I)
