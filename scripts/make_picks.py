"""Thursday's run: a side for every game.

    python3 scripts/make_picks.py                 # current week
    python3 scripts/make_picks.py --week 3
    python3 scripts/make_picks.py --week 3 --csv picks.csv

Picks come from two places, and the report keeps them apart because they are
not the same kind of claim:

  * LINE EDGE — the pool's number differs from the market's. This is a real,
    measured accuracy edge and the size of it is known.
  * UNDERDOG RULE — the lines agree, so there is no discrepancy to exploit.
    The pick goes to the underdog, which covers 51.1% of decided games overall
    and 53.7% for early-season road dogs. Small, but measured in both halves of
    the sample. See scripts/research_factors.py.
"""

import _bootstrap  # noqa: F401
import argparse
import json
from pathlib import Path

import pandas as pd

from weekly_picks.calibration import EdgeCalibration
from weekly_picks.crowd import CrowdModel
from weekly_picks.edge import compare
from weekly_picks.pool import PoolSheet
from weekly_picks.recommend import MIN_EDGE, recommend, to_frame
from weekly_picks.schedule import current_week, load_games, market_lines

POOL_DIR = Path(__file__).resolve().parents[1] / "data" / "pool"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--min-edge", type=float, default=MIN_EDGE)
    parser.add_argument("--crowd-slope", type=float, default=None,
                        help="override the crowd model's slope (see crowd.py)")
    parser.add_argument("--csv", type=Path, default=None)
    args = parser.parse_args()

    games = load_games()
    season = args.season or int(games[games["kickoff"].notna()]["season"].max())
    week = args.week or current_week(games, season)

    sheet_path = POOL_DIR / f"{season}_wk{week:02d}.json"
    if not sheet_path.exists():
        raise SystemExit(
            f"no pool sheet at {sheet_path}\n"
            f"capture one first:  python3 scripts/pool_lines.py --week {week} --live"
        )

    sheet = PoolSheet.from_dict(json.loads(sheet_path.read_text()))
    calibration = EdgeCalibration.load()
    crowd = CrowdModel(slope=args.crowd_slope) if args.crowd_slope else CrowdModel()

    table = compare(sheet, market_lines(games, season, week), calibration)
    picks = recommend(table, crowd=crowd, min_edge=args.min_edge)
    frame = to_frame(picks)

    edges = [p for p in picks if p.edge_points >= args.min_edge]
    fades = [p for p in picks if p.edge_points < args.min_edge]

    print(f"\n{'=' * 78}")
    print(f"  {season} WEEK {week}   sheet captured {sheet.captured_at or 'n/a'}")
    print(f"  crowd model: {'fitted, n=' + str(crowd.observations) if crowd.calibrated else 'prior (not yet fitted to your pool)'}")
    print(f"{'=' * 78}\n")

    if edges:
        print(f"LINE EDGE — the pool's number differs from the market ({len(edges)})\n")
        print(f"  {'game':<12} {'pick':<5} {'line':>6} {'edge':>5} {'win%':>7}")
        print(f"  {'-' * 40}")
        for p in edges:
            line = "" if p.line is None else f"{p.line:>+6.1f}"
            print(f"  {p.away_team + ' @ ' + p.home_team:<12} {p.pick:<5} {line} "
                  f"{p.edge_points:>5.1f} {p.win_prob * 100:>6.1f}%")
        print()

    if fades:
        print(f"UNDERDOG RULE — lines agree, so take the dog ({len(fades)})\n")
        print(f"  {'game':<12} {'pick':<5} {'line':>6} {'win%':>7}  {'why':<26}")
        print(f"  {'-' * 62}")
        for p in fades:
            line = "" if p.line is None else f"{p.line:>+6.1f}"
            print(f"  {p.away_team + ' @ ' + p.home_team:<12} {p.pick:<5} {line} "
                  f"{p.win_prob * 100:>6.1f}%  {p.reason:<26}")

    expected = frame["win_prob"].sum()
    rate = expected / len(frame) if len(frame) else 0.5
    print(f"\n{'-' * 78}")
    print(f"  games {len(frame)}   line edges {len(edges)}   underdog rule {len(fades)}")
    print(f"  expected record {expected:.1f}-{len(frame) - expected:.1f}  ({rate * 100:.1f}%)")
    print(f"  average share of the pool on your side: "
          f"{frame['crowd_share'].mean() * 100:.0f}%")
    print(f"{'-' * 78}\n")

    if args.csv:
        frame.to_csv(args.csv, index=False)
        print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
