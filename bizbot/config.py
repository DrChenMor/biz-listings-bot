"""Settings from config.toml."""
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
    sources: list[str]
    health: HealthConfig
    abn: AbnConfig


def load(path: Path = ROOT / "config.toml") -> Config:
    raw = tomllib.loads(Path(path).read_text())
    bot, filters, health, abn = raw["bot"], raw["filters"], raw["health"], raw["abn"]
    return Config(
        max_listings_per_run=bot["max_listings_per_run"],
        delay_seconds=tuple(bot["delay_seconds"]),
        start_jitter_minutes=tuple(bot["start_jitter_minutes"]),
        user_agent=bot["user_agent"],
        state=filters["state"].lower(),
        perth_postcodes=[tuple(r) for r in filters["perth_postcodes"]],
        sources=[name for name, s in raw["sources"].items() if s.get("enabled", True)],
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
