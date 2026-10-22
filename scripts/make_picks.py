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

ROOT = Path(__file__).resolve().parents[1]
POOL_DIR = ROOT / "data" / "pool"
PICKS_DIR = ROOT / "data" / "picks"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--min-edge", type=float, default=MIN_EDGE)
    parser.add_argument("--crowd-slope", type=float, default=None,
                        help="override the crowd model's slope (see crowd.py)")
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None,
                        help="write a GitHub-flavoured summary, first line the title")
    parser.add_argument("--save", action="store_true",
                        help="also record the picks under data/picks/ for later grading")
    args = parser.parse_args()

    games = load_games()
    season = args.season or int(games[games["kickoff"].notna()]["season"].max())
    week = args.week or current_week(games, season)

    calibration = EdgeCalibration.load()
    crowd = CrowdModel(slope=args.crowd_slope) if args.crowd_slope else CrowdModel()
    market = market_lines(games, season, week)

    sheet_path = POOL_DIR / f"{season}_wk{week:02d}.json"
    have_sheet = sheet_path.exists()
    if have_sheet:
        sheet = PoolSheet.from_dict(json.loads(sheet_path.read_text()))
        captured = sheet.captured_at or "n/a"
    else:
        # The underdog rule only needs the market line, so a missing sheet costs
        # the line-edge comparison and nothing else. Worth running anyway.
        sheet = PoolSheet(season=season, week=week, source="none — market lines only")
        captured = "NO POOL SHEET"

    table = compare(sheet, market, calibration)
    picks = recommend(table, crowd=crowd, min_edge=args.min_edge)
    frame = to_frame(picks)

    edges = [p for p in picks if p.edge_points >= args.min_edge]
    fades = [p for p in picks if p.edge_points < args.min_edge]

    print(f"\n{'=' * 78}")
    print(f"  {season} WEEK {week}   pool sheet: {captured}")
    print(f"  crowd model: {'fitted, n=' + str(crowd.observations) if crowd.calibrated else 'prior (not yet fitted to your pool)'}")
    print(f"{'=' * 78}\n")

    if not have_sheet:
        print("  No pool sheet for this week, so line edges cannot be checked —")
        print("  every pick below comes from the underdog rule off the market line.")
        print(f"  To add them:  python3 scripts/pool_lines.py --week {week} --html <saved page>\n")

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

    if args.markdown:
        args.markdown.write_text(
            _markdown(season, week, edges, fades, frame, have_sheet, expected)
        )
        print(f"wrote {args.markdown}")

    if args.save:
        # Grading later must use the picks as issued. Re-deriving them from a
        # refreshed games.csv silently swaps in closing lines, which changes
        # which side the rule picks and quietly flatters or punishes the record
        # — exactly the hindsight a backtest is supposed to avoid.
        PICKS_DIR.mkdir(parents=True, exist_ok=True)
        recorded = PICKS_DIR / f"{season}_wk{week:02d}.csv"
        frame.to_csv(recorded, index=False)
        print(f"recorded the picks as issued -> {recorded}")


def _markdown(season, week, edges, fades, frame, have_sheet, expected) -> str:
    """A summary that reads well in a GitHub notification email.

    The first line is the title, so a caller can split it off and use the rest
    as the body.
    """
    out = [f"# {season} Week {week} picks", ""]

    if not have_sheet:
        out += [
            "> **No pool sheet this week** — the scrape did not produce one, so "
            "every pick below comes from the underdog rule off the market line "
            "and line edges could not be checked.",
            "",
        ]

    if edges:
        out += [
            f"### Line edges — the pool's number differs from the market ({len(edges)})",
            "",
            "| game | pick | line | edge | win% |",
            "|---|---|---|---|---|",
        ]
        out += [
            f"| {p.away_team} @ {p.home_team} | **{p.pick}** | "
            f"{p.line:+g} | {p.edge_points:g} | {p.win_prob * 100:.1f}% |"
            for p in edges
        ]
        out.append("")

    if fades:
        out += [
            f"### Underdog rule — lines agree ({len(fades)})",
            "",
            "| game | pick | line | win% |",
            "|---|---|---|---|",
        ]
        out += [
            f"| {p.away_team} @ {p.home_team} | **{p.pick}** | "
            f"{p.line:+g} | {p.win_prob * 100:.1f}% |"
            for p in fades
        ]
        out.append("")

    rate = expected / len(frame) if len(frame) else 0.5
    out += [
        f"**{len(frame)} games** · {len(edges)} line edge(s) · "
        f"{len(fades)} underdog rule",
        "",
        f"Expected record **{expected:.1f}-{len(frame) - expected:.1f}** "
        f"({rate * 100:.1f}%).",
    ]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
