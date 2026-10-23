"""Settings from config.toml."""
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    max_listings_per_run: int
    delay_seconds: tuple[float, float]
    start_jitter_minutes: tuple[float, float]
    user_agent: str
    state: str
    perth_postcodes: list[tuple[int, int]]
    sources: list[str]


def load(path: Path = ROOT / "config.toml") -> Config:
    raw = tomllib.loads(Path(path).read_text())
    bot, filters = raw["bot"], raw["filters"]
    return Config(
        max_listings_per_run=bot["max_listings_per_run"],
        delay_seconds=tuple(bot["delay_seconds"]),
        start_jitter_minutes=tuple(bot["start_jitter_minutes"]),
        user_agent=bot["user_agent"],
        state=filters["state"].lower(),
        perth_postcodes=[tuple(r) for r in filters["perth_postcodes"]],
        sources=[name for name, s in raw["sources"].items() if s.get("enabled", True)],
    )
