"""Choosing a side for every game.

Two findings drive this, both measured rather than assumed (see
`scripts/research_market_efficiency.py`):

1. **You cannot out-predict the closing spread.** Elo and rolling EPA/play
   correlate 0.84 and 0.78 with the market's own number — they mostly
   re-derive it — and a walk-forward model of the residual hit 50.2% over
   4,135 out-of-sample games. There is no margin model here because the
   evidence does not support one.

2. **Correlation with the field is the lever that actually moves a pool.**
   Best-record-wins pays the maximum, not the mean, so picking by the same
   process as everyone else returns a fair share of the pot. A consistent rule
   that sits away from the field's centre does several times better.

So the policy is:

    if the pool's line differs from the market   ->  take the side that favours
    (a real, measurable accuracy edge)               regardless of the crowd

    otherwise                                    ->  take the side the field is
    (a coin flip on accuracy)                        least likely to be on

Fading costs nothing in accuracy here: underdogs cover 51.1% of decided games
against 48.9% for favorites (1999-2025), so the contrarian side is, if
anything, marginally the better one.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .crowd import CrowdModel

# Below this many points the discrepancy is not worth surrendering
# differentiation for. Chosen by simulation: taking every edge from 0.5 points
# up beat every higher threshold.
MIN_EDGE = 0.5


@dataclass
class Recommendation:
    game_id: str
    away_team: str
    home_team: str
    pick: str
    line: float | None          # the pool's number from the picked side
    reason: str
    win_prob: float             # accuracy estimate; 0.5 when it is a coin flip
    crowd_share: float          # share of the pool expected on your side
    edge_points: float          # line discrepancy, 0 when the lines agree

    @property
    def differentiation(self) -> float:
        """Share of the pool expected to be on the *other* side."""
        return 1.0 - self.crowd_share


def _favorite(spread: float, home_team: str, away_team: str) -> str | None:
    if spread == 0:
        return None
    return home_team if spread > 0 else away_team


def recommend(
    comparison: pd.DataFrame,
    crowd: CrowdModel | None = None,
    min_edge: float = MIN_EDGE,
) -> list[Recommendation]:
    """Turn a pool-vs-market comparison into a pick for every game."""
    crowd = crowd or CrowdModel()
    out: list[Recommendation] = []

    for row in comparison.itertuples():
        pool_spread = getattr(row, "pool_spread", None)
        market_spread = getattr(row, "market_spread", None)
        edge = getattr(row, "edge_points", None)
        edge = 0.0 if edge is None or pd.isna(edge) else float(edge)

        # The number the crowd reacts to is the one on their sheet.
        reference = pool_spread if pd.notna(pool_spread) else market_spread
        if reference is None or pd.isna(reference):
            continue
        reference = float(reference)

        favorite = _favorite(reference, row.home_team, row.away_team)
        underdog = (
            row.away_team if favorite == row.home_team
            else row.home_team if favorite == row.away_team
            else None
        )

        if edge >= min_edge and pd.notna(getattr(row, "pick", None)):
            pick = row.pick
            win_prob = float(row.win_prob)
            reason = f"line edge {edge:g} pts"
        elif underdog is not None:
            pick = underdog
            win_prob = 0.5
            reason = "fade the field (underdog)"
        else:
            # A true pick'em: no favorite, so no crowd to fade. Take the home
            # side and mark it as the coin flip it is.
            pick = row.home_team
            win_prob = 0.5
            reason = "pick'em — no edge either way"

        line = None
        if pd.notna(pool_spread):
            line = -float(pool_spread) if pick == row.home_team else float(pool_spread)

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
