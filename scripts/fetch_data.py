"""Refresh the nflverse data this project reads.

    python3 scripts/fetch_data.py              # schedule, results and market lines
    python3 scripts/fetch_data.py --team-stats # also weekly EPA (research only)

The schedule is one ~2 MB file covering 1999 to the current week, carrying the
matchups, kickoff times, consensus spreads and the final scores used to grade.
That is all the weekly picks need.

Weekly team stats are another ~5 MB and are only used by
scripts/research_market_efficiency.py, so they are fetched on request and not
tracked in git.
"""

import _bootstrap  # noqa: F401
import argparse
import urllib.request
from pathlib import Path

from weekly_picks.schedule import GAMES_CSV, SCHEDULE_URL, fetch_schedule, load_games

TEAM_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/stats_team/"
    "stats_team_week_{year}.csv"
)
TEAM_STATS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "team_stats_weekly"


def fetch_team_stats(start: int, end: int, force: bool) -> None:
    TEAM_STATS_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for year in range(start, end + 1):
        out = TEAM_STATS_DIR / f"stats_team_week_{year}.csv"
        # The current season's file is rewritten weekly, so always refresh it.
        if out.exists() and not force and year < end:
            continue
        try:
            with urllib.request.urlopen(TEAM_STATS_URL.format(year=year), timeout=120) as r:
                out.write_bytes(r.read())
            total += out.stat().st_size
        except Exception as exc:                                   # noqa: BLE001
            print(f"  FAILED {year}: {exc}")
    print(f"team stats: {total / 1e6:.1f} MB into {TEAM_STATS_DIR.relative_to(Path.cwd())}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=SCHEDULE_URL)
    parser.add_argument("--dest", default=str(GAMES_CSV))
    parser.add_argument("--team-stats", action="store_true",
                        help="also download weekly team stats (needed for research)")
    parser.add_argument("--start", type=int, default=1999)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    path = fetch_schedule(args.dest, args.url)
    games = load_games(path)
    played = games.dropna(subset=["result"])
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
    print(f"  {len(games)} regular season games, {games.season.min()}-{games.season.max()}")
    print(f"  {len(played)} with final scores, {games.spread_line.notna().sum()} with a spread")

    if args.team_stats:
        fetch_team_stats(args.start, args.end or int(games.season.max()), args.force)


if __name__ == "__main__":
    main()
