"""Where the edge comes from: the pool's line vs. the market's line.

The pool posts its lines once and leaves them. The market keeps moving on
injuries, weather and money. Every point of daylight between the two is a bet
made at a better number than the market's own current estimate of the game,
and `calibration.py` measures what each of those points has historically been
worth.

Sign convention (see schedule.py): a spread is quoted for the HOME team, with
positive meaning home is favored, and the home team covers when

    margin > spread

A *higher* number is therefore worse for the home side. So:

    pool_spread > market_spread  ->  the pool makes home lay too much  ->  take AWAY
    pool_spread < market_spread  ->  home is cheap at the pool         ->  take HOME

and the edge is the gap between them, in points.
"""

from __future__ import annotations

import pandas as pd

from .calibration import EdgeCalibration
from .pool.models import PoolSheet


def compare(sheet: PoolSheet, market: pd.DataFrame, calibration: EdgeCalibration) -> pd.DataFrame:
    """Join the pool's sheet to the market and price every discrepancy.

    Games the pool posted but the schedule doesn't have (and vice versa) are
    reported rather than dropped — a silent mismatch on a Thursday is how you
    end up not making a pick.
    """
    by_teams = sheet.by_teams()
    rows = []

    for game in market.itertuples():
        teams = frozenset({game.home_team, game.away_team})
        line = by_teams.get(teams)

        pool_spread = line.home_spread(game.home_team) if line else None
        market_spread = None if pd.isna(game.market_spread) else float(game.market_spread)

        edge = side = pick = win_prob = None
        if pool_spread is not None and market_spread is not None:
            difference = pool_spread - market_spread
            edge = abs(difference)
            if edge == 0:
                side, pick = "none", None
            else:
                side = "away" if difference > 0 else "home"
                pick = game.away_team if side == "away" else game.home_team
            win_prob = calibration.win_probability(edge)

        rows.append(
            {
                "game_id": game.game_id,
                "kickoff": game.kickoff,
                "away_team": game.away_team,
                "home_team": game.home_team,
                "pool_spread": pool_spread,
                "market_spread": market_spread,
                "edge_points": edge,
                "side": side,
                "pick": pick,
                # The number the pick lays or takes, from the picker's side.
                "pick_line": _pick_line(pool_spread, side),
                "win_prob": win_prob,
                "status": _status(line, pool_spread, market_spread),
            }
        )

    frame = pd.DataFrame(rows)

    # Pool lines with no matching scheduled game — a parse error or a bye-week
    # mixup, either way something to look at before submitting.
    scheduled = {frozenset({g.home_team, g.away_team}) for g in market.itertuples()}
    for teams, line in by_teams.items():
        if teams not in scheduled:
            frame = pd.concat(
                [
                    frame,
                    pd.DataFrame([{
                        "game_id": None,
                        "away_team": line.underdog,
                        "home_team": line.favorite,
                        "pool_spread": None,
                        "market_spread": None,
                        "status": "pool line has no scheduled game",
                    }]),
                ],
                ignore_index=True,
            )

    return frame.sort_values("edge_points", ascending=False, na_position="last").reset_index(drop=True)


def _pick_line(pool_spread: float | None, side: str | None) -> float | None:
    """The pool's number as the picked side sees it (negative = laying points).

    `pool_spread` is quoted for the home team with positive meaning home is
    favored, so the home side *lays* that many points and its line is the
    negation.
    """
    if pool_spread is None or side in (None, "none"):
        return None
    return -pool_spread if side == "home" else pool_spread


def _status(line, pool_spread, market_spread) -> str:
    if line is None:
        return "no pool line"
    if market_spread is None:
        return "no market line"
    if pool_spread == market_spread:
        return "lines agree"
    return "ok"


def summarize(comparison: pd.DataFrame, min_edge: float = 0.5) -> dict:
    """Headline numbers for a week: how many games carry a real discrepancy and
    what the slate is worth if every edge is played."""
    playable = comparison[comparison["edge_points"].fillna(0) >= min_edge]
    return {
        "games": int(len(comparison)),
        "matched": int(comparison["edge_points"].notna().sum()),
        "with_edge": int(len(playable)),
        "total_edge_points": float(playable["edge_points"].sum()),
        "mean_win_prob": float(playable["win_prob"].mean()) if len(playable) else None,
        "expected_wins": float(playable["win_prob"].sum()) if len(playable) else 0.0,
        "problems": comparison[
            ~comparison["status"].isin(["ok", "lines agree"])
        ]["status"].value_counts().to_dict(),
    }
