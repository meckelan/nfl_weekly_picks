"""Thursday's run: turn the pool sheet and the market into a pick for every game.

    python3 scripts/make_picks.py                 # current week
    python3 scripts/make_picks.py --week 3
    python3 scripts/make_picks.py --week 3 --csv picks.csv

Every game gets a pick, because the pool requires one. They come from two very
different places, and the report keeps them apart:

  * games where the pool's line differs from the market — the pick is the side
    the discrepancy favors, and the edge is real and measurable
  * games where the two agree — there is no edge by construction, and the pick
    is a coin flip dressed up as an opinion until a margin model fills it in
"""

import _bootstrap  # noqa: F401
import argparse
import json
from pathlib import Path

import pandas as pd

from weekly_picks.calibration import EdgeCalibration
from weekly_picks.edge import compare, summarize
from weekly_picks.pool import PoolSheet
from weekly_picks.schedule import current_week, load_games, market_lines

POOL_DIR = Path(__file__).resolve().parents[1] / "data" / "pool"


def _fallback_pick(row: pd.Series) -> tuple[str | None, str]:
    """No discrepancy means no edge. Take the market favorite and say so."""
    if pd.isna(row["market_spread"]):
        return None, "no line"
    if row["market_spread"] == 0:
        return row["home_team"], "coin flip (pick'em)"
    favorite = row["home_team"] if row["market_spread"] > 0 else row["away_team"]
    return favorite, "coin flip (lines agree)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--min-edge", type=float, default=0.5)
    parser.add_argument("--csv", type=Path, default=None, help="also write the picks to CSV")
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
    market = market_lines(games, season, week)

    table = compare(sheet, market, calibration)

    picks, reasons = [], []
    for _, row in table.iterrows():
        if pd.notna(row["pick"]):   # None survives into the frame as NaN
            picks.append(row["pick"])
            reasons.append(f"{row['edge_points']:g} pts of line value")
        else:
            pick, reason = _fallback_pick(row)
            picks.append(pick)
            reasons.append(reason)
    table["final_pick"] = picks
    table["reason"] = reasons

    edges = table[table["edge_points"].fillna(0) >= args.min_edge]
    flat = table[~table.index.isin(edges.index)]
    stats = summarize(table, args.min_edge)

    print(f"\n{'=' * 78}")
    print(f"  {season} WEEK {week}   pool sheet captured {sheet.captured_at or 'n/a'}")
    print(f"  calibration: {calibration.n_games:,} games, "
          f"{calibration.seasons[0]}-{calibration.seasons[1]}")
    print(f"{'=' * 78}\n")

    if len(edges):
        print(f"EDGES — pool line differs from the market ({len(edges)} games)\n")
        print(f"  {'game':<12} {'pick':<6} {'line':>6} {'market':>7} {'edge':>5} {'win%':>7}")
        print(f"  {'-' * 52}")
        for row in edges.itertuples():
            print(f"  {row.away_team + ' @ ' + row.home_team:<12} {row.final_pick:<6} "
                  f"{row.pick_line:>+6.1f} {row.market_spread:>+7.1f} "
                  f"{row.edge_points:>5.1f} {row.win_prob * 100:>6.1f}%")
    else:
        print("EDGES — none. The pool's lines match the market everywhere this week.")

    if len(flat):
        print(f"\nNO EDGE — lines agree, these are coin flips ({len(flat)} games)\n")
        for row in flat.itertuples():
            pick = row.final_pick or "-"
            line = "" if row.market_spread is None or pd.isna(row.market_spread) else f"{row.market_spread:>+6.1f}"
            print(f"  {row.away_team + ' @ ' + row.home_team:<12} {pick:<6} {line:>7}   {row.reason}")

    expected = stats["expected_wins"] + 0.5 * len(flat)
    print(f"\n{'-' * 78}")
    print(f"  games {stats['games']}   with edge {stats['with_edge']}   "
          f"total edge {stats['total_edge_points']:.1f} pts")
    if stats["mean_win_prob"]:
        print(f"  mean win probability on edges: {stats['mean_win_prob'] * 100:.1f}%")
    print(f"  expected record this week: {expected:.1f}-{stats['games'] - expected:.1f} "
          f"(coin flips counted at 50%)")
    if stats["problems"]:
        print(f"  PROBLEMS: {stats['problems']}")
    print(f"{'-' * 78}\n")

    if args.csv:
        columns = ["game_id", "away_team", "home_team", "pool_spread", "market_spread",
                   "edge_points", "final_pick", "pick_line", "win_prob", "reason"]
        table[columns].to_csv(args.csv, index=False)
        print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
