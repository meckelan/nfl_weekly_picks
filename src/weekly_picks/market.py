"""Where the market's number comes from.

nflverse's `spread_line` is one snapshot a day, and the strategy keys on gaps
of half a point to a point — at or below that series' noise floor. It has been
caught reading 1.5 where books showed 2.5, and in week 7 it read +1.5 on a
game that closed at -3.0, a 4.5-point miss. Over the eleven edges it flagged
in weeks 7-9 it still tracked the close better than the pool's own line (0.68
vs 0.82 points of mean error), so the signal is real — but it is being read
through a noisy instrument.

So the market reference is pluggable. `OddsApiMarket` asks the-odds-api.com
for live spreads across books and takes the **median**, which is what makes
this worth doing: a single book being off by a point no longer invents an
edge, where a single daily snapshot could. `NflverseMarket` keeps the old
behaviour as a fallback when no key is configured or the call fails.

Both return the same thing: home-favoured-positive spreads keyed by the pair
of teams, matching the convention in schedule.py.
"""

from __future__ import annotations

import json
import os
import statistics
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import pandas as pd

from .teams import UnknownTeamError, resolve

ROOT = Path(__file__).resolve().parents[2]
MARKET_DIR = ROOT / "data" / "market"

ODDS_API_HOST = "api.the-odds-api.com"
ODDS_API_URL = f"https://{ODDS_API_HOST}/v4/sports/americanfootball_nfl/odds"


@dataclass(frozen=True)
class Quote:
    """One game's market spread, home-favoured-positive."""

    away_team: str
    home_team: str
    home_spread: float
    books: int = 0           # how many bookmakers the median was taken over
    spread_of_books: float = 0.0   # max - min across books, i.e. how much they disagree

    @property
    def teams(self) -> frozenset[str]:
        return frozenset({self.away_team, self.home_team})


class MarketSource(Protocol):
    name: str

    def quotes(self, season: int, week: int) -> dict[frozenset[str], Quote]:
        ...


@dataclass
class NflverseMarket:
    """The daily consensus snapshot in games.csv. One number, no book count."""

    games: pd.DataFrame
    name: str = "nflverse (daily snapshot)"

    def quotes(self, season: int, week: int) -> dict[frozenset[str], Quote]:
        slate = self.games[(self.games.season == season) & (self.games.week == week)]
        out: dict[frozenset[str], Quote] = {}
        for game in slate.itertuples():
            if pd.isna(game.spread_line):
                continue
            quote = Quote(game.away_team, game.home_team, float(game.spread_line))
            out[quote.teams] = quote
        return out


@dataclass
class OddsApiMarket:
    """Live spreads from the-odds-api.com, taken as the median across books."""

    api_key: str = field(default_factory=lambda: os.environ.get("ODDS_API_KEY", ""))
    regions: str = "us"
    timeout: int = 30
    name: str = "the-odds-api (median of books)"
    last_payload: list | None = None
    requests_remaining: str | None = None

    def fetch(self) -> list:
        """The raw payload for the upcoming NFL slate."""
        if not self.api_key:
            raise RuntimeError("ODDS_API_KEY is not set")

        query = urllib.parse.urlencode({
            "apiKey": self.api_key,
            "regions": self.regions,
            "markets": "spreads",
            "oddsFormat": "american",
        })
        request = urllib.request.Request(f"{ODDS_API_URL}?{query}")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            # The quota headers are the only way to notice the free tier running
            # out before it starts failing.
            self.requests_remaining = response.headers.get("x-requests-remaining")
            self.last_payload = json.loads(response.read())
        return self.last_payload

    @staticmethod
    def parse(payload: list) -> dict[frozenset[str], Quote]:
        """Median home spread per game, on our sign convention.

        The API quotes a spread the way a book does — negative means the team
        is laying points — so the home team's `point` is negated to match
        nflverse, where positive means the home team is favoured.
        """
        out: dict[frozenset[str], Quote] = {}
        for event in payload:
            try:
                home = resolve(event["home_team"])
                away = resolve(event["away_team"])
            except (UnknownTeamError, KeyError):
                continue

            points: list[float] = []
            for book in event.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market.get("key") != "spreads":
                        continue
                    for outcome in market.get("outcomes", []):
                        try:
                            if resolve(outcome["name"]) == home and outcome.get("point") is not None:
                                points.append(float(outcome["point"]))
                        except (UnknownTeamError, KeyError):
                            continue
            if not points:
                continue

            quote = Quote(
                away_team=away,
                home_team=home,
                home_spread=-statistics.median(points),   # book sign -> ours
                books=len(points),
                spread_of_books=max(points) - min(points),
            )
            out[quote.teams] = quote
        return out

    def quotes(self, season: int, week: int) -> dict[frozenset[str], Quote]:
        # The endpoint returns the upcoming slate rather than a chosen week, so
        # season and week are accepted for the interface and not used.
        return self.parse(self.fetch())


def resolve_source(games: pd.DataFrame) -> tuple[MarketSource, str]:
    """The best market source available, and a line about which it is."""
    if os.environ.get("ODDS_API_KEY"):
        return OddsApiMarket(), "live odds (median across books)"
    return NflverseMarket(games), "nflverse daily snapshot — no ODDS_API_KEY set"


def save_snapshot(quotes: dict[frozenset[str], Quote], season: int, week: int,
                  source: str, directory: Path = MARKET_DIR) -> Path:
    """Record what the market said at pick time.

    Same lesson as recording the picks: grading later must not re-read a market
    that has since moved.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{season}_wk{week:02d}.json"
    payload = {
        "season": season, "week": week, "source": source,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quotes": [
            {"away_team": q.away_team, "home_team": q.home_team,
             "home_spread": q.home_spread, "books": q.books,
             "spread_of_books": q.spread_of_books}
            for q in sorted(quotes.values(), key=lambda q: (q.away_team, q.home_team))
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path
