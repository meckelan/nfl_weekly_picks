"""Choosing a side for every game.

The goal is a season record above .500, so this optimises **accuracy** and
nothing else. (An earlier version optimised the chance of finishing first,
which favours being different from the field rather than being right. Those
are different objectives and they give different picks.)

Two measured things to work with, in priority order:

1. **The pool's line vs. the market's.** Where they differ you are betting into
   a number the market itself no longer believes. Worth 52.3% at half a point,
   60.1% at three. This is the strongest signal available, and it is
   arithmetic rather than forecasting.

2. **Underdogs cover slightly more than half the time.** Not because dogs are
   mispriced in any deep sense — the public likes favorites and home teams, so
   books shade those lines, and the shading comes out of the favorite's side.
   Measured over 6,793 decided games (1999-2025), split by era so a single
   lucky period cannot carry it:

       every dog              51.11%   [99-12 51.19% | 13-25 51.03%]
       road dogs              51.67%   [99-12 51.79% | 13-25 51.54%]
       dogs, weeks 1-4        53.05%   [99-12 52.74% | 13-25 53.36%]
       road dogs, weeks 1-4   53.70%   [99-12 53.38% | 13-25 54.02%]

   Early-season dogs do best, which is what you would expect: the market has
   the least information in September and the public leans hardest on last
   year's reputations.

What did *not* survive a 39-factor screen with a held-out era:
turnover-luck regression, blowout overreaction, ATS streaks, bye weeks,
weather, totals, EPA-vs-record divergence, backup quarterbacks. See
`scripts/research_factors.py`. And no margin model survived at all — see
`scripts/research_market_efficiency.py`.

These edges are small: about +2 points of win rate, against a season-to-season
swing of ~8 games. They tilt the odds, they do not decide the season.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .crowd import CrowdModel

# Below this, the line discrepancy is worth less than the underdog rule.
MIN_EDGE = 0.5

EARLY_SEASON_WEEKS = 4

# Measured hit rates, taking the underdog. Checked in both halves of the
# sample; see scripts/research_factors.py for the screen that produced them.
RATE_EARLY_ROAD_DOG = 0.5370
RATE_EARLY_DOG = 0.5305
RATE_ROAD_DOG = 0.5167
RATE_ANY_DOG = 0.5111
RATE_COIN_FLIP = 0.5000


@dataclass
class Recommendation:
    game_id: str
    away_team: str
    home_team: str
    pick: str
    line: float | None          # the pool's number from the picked side
    reason: str
    win_prob: float
    crowd_share: float          # share of the pool expected on your side
    edge_points: float

    @property
    def differentiation(self) -> float:
        return 1.0 - self.crowd_share


def underdog_rule(week: int | None, dog_is_road: bool) -> tuple[float, str]:
    """The measured hit rate for taking this underdog, and what to call it."""
    early = week is not None and week <= EARLY_SEASON_WEEKS
    if early and dog_is_road:
        return RATE_EARLY_ROAD_DOG, "early-season road underdog"
    if early:
        return RATE_EARLY_DOG, "early-season underdog"
    if dog_is_road:
        return RATE_ROAD_DOG, "road underdog"
    return RATE_ANY_DOG, "underdog"


def recommend(
    comparison: pd.DataFrame,
    crowd: CrowdModel | None = None,
    min_edge: float = MIN_EDGE,
) -> list[Recommendation]:
    """A pick for every game, best available signal first."""
    crowd = crowd or CrowdModel()
    out: list[Recommendation] = []

    for row in comparison.itertuples():
        pool_spread = getattr(row, "pool_spread", None)
        market_spread = getattr(row, "market_spread", None)
        edge = getattr(row, "edge_points", None)
        edge = 0.0 if edge is None or pd.isna(edge) else float(edge)

        # The pool's number is the one the game settles against.
        reference = pool_spread if pd.notna(pool_spread) else market_spread
        if reference is None or pd.isna(reference):
            continue
        reference = float(reference)

        week = getattr(row, "week", None)
        week = int(week) if week is not None and pd.notna(week) else None

        favorite = None if reference == 0 else (
            row.home_team if reference > 0 else row.away_team
        )
        underdog = None if favorite is None else (
            row.away_team if favorite == row.home_team else row.home_team
        )

        if edge >= min_edge and pd.notna(getattr(row, "pick", None)):
            pick = row.pick
            win_prob = float(row.win_prob)
            reason = f"line edge {edge:g} pts"
        elif underdog is not None:
            pick = underdog
            win_prob, reason = underdog_rule(week, dog_is_road=(underdog == row.away_team))
        else:
            pick = row.home_team
            win_prob, reason = RATE_COIN_FLIP, "pick'em — nothing to go on"

        # The number the pick lays or takes. Prefer the pool's own line, since
        # that is what the game settles against; fall back to the market's when
        # no sheet has been captured, so the pick is still readable.
        line = -reference if pick == row.home_team else reference

        out.append(
            Recommendation(
                game_id=getattr(row, "game_id", None),
                away_team=row.away_team,
                home_team=row.home_team,
                pick=pick,
                line=line,
                reason=reason,
                win_prob=win_prob,
                crowd_share=crowd.share_on(reference, side_is_favorite=(pick == favorite)),
                edge_points=edge,
            )
        )

    return out


def to_frame(recommendations: list[Recommendation]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": r.game_id,
                "away_team": r.away_team,
                "home_team": r.home_team,
                "pick": r.pick,
                "line": r.line,
                "reason": r.reason,
                "win_prob": r.win_prob,
                "crowd_share": r.crowd_share,
                "differentiation": r.differentiation,
                "edge_points": r.edge_points,
            }
            for r in recommendations
        ]
    )
