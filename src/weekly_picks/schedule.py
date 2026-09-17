"""nflverse schedule, results and market lines.

One public release asset carries everything the picks need: the week's
matchups, kickoff times, the consensus spread, and (once played) the final
score used to grade. No API key, no scraping.

Spread convention throughout this project, matching nflverse:

    spread_line > 0  ->  the HOME team is favored by that many points
    margin = home_score - away_score  (the `result` column)
    home covers when margin > spread_line

Verified against 6,983 games (1999-2026): when spread_line > 0 the home team
wins 67.6% of the time and is priced at an average moneyline of -309.
"""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

import pandas as pd

SCHEDULE_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
)

ROOT = Path(__file__).resolve().parents[2]
GAMES_CSV = ROOT / "data" / "raw" / "games.csv"

COLUMNS = [
    "game_id", "season", "game_type", "week", "gameday", "weekday", "gametime",
    "away_team", "home_team", "away_score", "home_score", "result",
    "location", "spread_line", "total_line", "away_moneyline", "home_moneyline",
    "away_rest", "home_rest", "div_game", "roof", "surface",
    "away_qb_name", "home_qb_name",
]


def fetch_schedule(dest: Path | str = GAMES_CSV, url: str = SCHEDULE_URL) -> Path:
    """Download the current schedule/results file, replacing any local copy."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with urllib.request.urlopen(url, timeout=120) as response, tmp.open("wb") as out:
        shutil.copyfileobj(response, out)
    tmp.replace(dest)
    return dest


def load_games(
    path: Path | str = GAMES_CSV,
    *,
    regular_season_only: bool = True,
    played_only: bool = False,
) -> pd.DataFrame:
    """Load the schedule.

    By default returns every regular season game, played or not, so the same
    frame serves both backtesting and this week's upcoming slate.
    """
    df = pd.read_csv(path, low_memory=False)

    if regular_season_only:
        df = df[df["game_type"] == "REG"]
    if played_only:
        df = df.dropna(subset=["home_score", "away_score"])

    df = df.reindex(columns=[c for c in COLUMNS if c in df.columns]).copy()
    df["kickoff"] = pd.to_datetime(
        df["gameday"].astype(str) + " " + df["gametime"].fillna("00:00").astype(str),
        errors="coerce",
    )
    return df.sort_values(["season", "week", "kickoff"]).reset_index(drop=True)


def market_lines(games: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    """The market's spread for one week, as the reference the pool is judged against.

    Returns one row per game with `market_spread` on the home-favored-positive
    convention. Games the source has no line for are kept with NaN so a missing
    line is visible rather than silently dropped.
    """
    slate = games[(games["season"] == season) & (games["week"] == week)].copy()
    slate = slate.rename(columns={"spread_line": "market_spread"})
    return slate[
        [
            "game_id", "season", "week", "kickoff", "weekday",
            "away_team", "home_team", "market_spread", "total_line",
            "away_moneyline", "home_moneyline", "location",
        ]
    ].reset_index(drop=True)


def current_week(games: pd.DataFrame, season: int, now: pd.Timestamp | None = None) -> int:
    """The week whose games are next to be played.

    A week stays 'current' until its last game has kicked off, so a Thursday
    run picks the week that starts that evening.
    """
    now = pd.Timestamp.now() if now is None else now
    season_games = games[games["season"] == season]
    if season_games.empty:
        raise ValueError(f"no games found for season {season}")

    upcoming = season_games[season_games["kickoff"] >= now]
    if upcoming.empty:
        return int(season_games["week"].max())
    return int(upcoming["week"].min())
