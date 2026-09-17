"""Measure what a point of line discrepancy is worth, and cache the answer.

    python3 scripts/calibrate_edge.py
    python3 scripts/calibrate_edge.py --since 2010

Writes data/edge_calibration.json, which the weekly run reads so it never
needs the full history at pick time.
"""

import _bootstrap  # noqa: F401
import argparse

from weekly_picks.calibration import CALIBRATION_JSON, EdgeCalibration
from weekly_picks.schedule import load_games


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=int, default=None, help="first season to include")
    parser.add_argument("--dest", default=str(CALIBRATION_JSON))
    args = parser.parse_args()

    games = load_games()
    if args.since:
        games = games[games["season"] >= args.since]

    calibration = EdgeCalibration.from_games(games)
    calibration.save(args.dest)

    seasons = f"{calibration.seasons[0]}-{calibration.seasons[1]}"
    print(f"Calibrated on {calibration.n_games:,} graded games ({seasons})\n")
    print(f"{'edge':>6} {'win':>8} {'push':>7} {'loss':>8} {'win% (decided)':>16}")
    print("-" * 49)
    for row in calibration.to_frame().itertuples():
        if row.edge_points * 2 % 1 == 0 and row.edge_points <= 7:
            print(
                f"{row.edge_points:>6.1f} {row.win * 100:>7.2f}% {row.push * 100:>6.2f}% "
                f"{row.loss * 100:>7.2f}% {row.win_pct_decided * 100:>15.2f}%"
            )
    print(f"\nwrote {args.dest}")


if __name__ == "__main__":
    main()
