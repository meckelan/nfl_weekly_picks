"""Refresh the nflverse schedule, results and market lines.

    python3 scripts/fetch_data.py

Safe to run as often as you like — it is one ~2 MB file covering 1999 to the
current week, and it carries the results used for grading as well as the lines.
"""

import _bootstrap  # noqa: F401
import argparse

from weekly_picks.schedule import GAMES_CSV, SCHEDULE_URL, fetch_schedule, load_games


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=SCHEDULE_URL)
    parser.add_argument("--dest", default=str(GAMES_CSV))
    args = parser.parse_args()

    path = fetch_schedule(args.dest, args.url)
    games = load_games(path)
    played = games.dropna(subset=["result"])
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
    print(f"  {len(games)} regular season games, {games.season.min()}-{games.season.max()}")
    print(f"  {len(played)} with final scores, {games.spread_line.notna().sum()} with a spread")


if __name__ == "__main__":
    main()
