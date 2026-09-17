"""How much a line discrepancy is actually worth, measured from history.

The pool's line is fixed when the sheet is posted; the market keeps moving.
When the two disagree by `d` points, taking the side the discrepancy favors is
a bet at a better number than the market's own estimate of the game.

Rather than assume a normal distribution of outcomes, this measures the
empirical distribution of

    err = margin - closing_spread

over every graded game in the schedule file, and reads win probability
straight off it. That keeps the NFL's key numbers (3, 7, 10) in the answer
instead of smoothing them away.

Taking the home side at a pool line `d` points cheaper than the market:
    win  when margin > pool_line, i.e. err > -d
Taking the away side at a pool line `d` points cheaper:
    win  when margin < pool_line, i.e. err < +d

Both directions are averaged, since which one a given week hands you is
arbitrary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_JSON = ROOT / "data" / "edge_calibration.json"

# Half-point granularity to 10 points covers every realistic discrepancy.
GRID = [round(x, 1) for x in np.arange(0.0, 10.01, 0.5)]


@dataclass(frozen=True)
class EdgeOutcome:
    """Probability of each result when holding `edge` points of line value."""

    edge: float
    win: float
    push: float
    loss: float

    @property
    def win_pct_decided(self) -> float:
        """Win rate ignoring pushes — the number that matters in a pool where a
        push is replayed or voided rather than scored."""
        decided = self.win + self.loss
        return self.win / decided if decided else 0.5


class EdgeCalibration:
    """Empirical map from points of line edge to ATS win probability."""

    def __init__(self, table: dict[float, EdgeOutcome], n_games: int, seasons: tuple[int, int]):
        self._table = table
        self.n_games = n_games
        self.seasons = seasons

    # ── construction ─────────────────────────────────────────────────────────
    @classmethod
    def from_games(cls, games: pd.DataFrame) -> "EdgeCalibration":
        graded = games.dropna(subset=["result", "spread_line"])
        err = (graded["result"] - graded["spread_line"]).to_numpy(dtype=float)
        if len(err) == 0:
            raise ValueError("no graded games with spreads to calibrate on")

        table = {}
        for d in GRID:
            # Home-side and away-side readings of the same edge.
            home_win, home_push = float((err > -d).mean()), float((err == -d).mean())
            away_win, away_push = float((err < d).mean()), float((err == d).mean())
            win = (home_win + away_win) / 2
            push = (home_push + away_push) / 2
            table[d] = EdgeOutcome(d, win, push, max(0.0, 1.0 - win - push))

        seasons = (int(graded["season"].min()), int(graded["season"].max()))
        return cls(table, len(err), seasons)

    # ── lookup ───────────────────────────────────────────────────────────────
    def outcome(self, edge: float) -> EdgeOutcome:
        """Outcome probabilities for `edge` points, interpolating between grid
        points and clamping beyond the top of the grid."""
        edge = abs(float(edge))
        if edge >= GRID[-1]:
            return self._table[GRID[-1]]

        lower = max(g for g in GRID if g <= edge)
        if lower == edge:
            return self._table[lower]

        upper = min(g for g in GRID if g > edge)
        span = upper - lower
        frac = (edge - lower) / span
        lo, hi = self._table[lower], self._table[upper]
        return EdgeOutcome(
            edge,
            lo.win + (hi.win - lo.win) * frac,
            lo.push + (hi.push - lo.push) * frac,
            lo.loss + (hi.loss - lo.loss) * frac,
        )

    def win_probability(self, edge: float) -> float:
        """Win rate among decided games for `edge` points of line value."""
        return self.outcome(edge).win_pct_decided

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "edge_points": o.edge,
                    "win": o.win,
                    "push": o.push,
                    "loss": o.loss,
                    "win_pct_decided": o.win_pct_decided,
                }
                for o in (self._table[d] for d in GRID)
            ]
        )

    # ── persistence ──────────────────────────────────────────────────────────
    def save(self, path: Path | str = CALIBRATION_JSON) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "n_games": self.n_games,
            "seasons": list(self.seasons),
            "grid": [
                {"edge": o.edge, "win": o.win, "push": o.push, "loss": o.loss}
                for o in (self._table[d] for d in GRID)
            ],
        }
        path.write_text(json.dumps(payload, indent=2) + "\n")
        return path

    @classmethod
    def load(cls, path: Path = CALIBRATION_JSON) -> "EdgeCalibration":
        payload = json.loads(Path(path).read_text())
        table = {
            round(float(row["edge"]), 1): EdgeOutcome(
                float(row["edge"]), row["win"], row["push"], row["loss"]
            )
            for row in payload["grid"]
        }
        return cls(table, payload["n_games"], tuple(payload["seasons"]))
