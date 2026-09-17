"""Modelling what the rest of the pool will pick.

In a season-long, best-record-wins pool, your own hit rate is only half the
problem. The other half is *correlation with the field*: the pool pays the
maximum score, not the mean, so picking by the same process as everyone else
lands you a fair share of the pot and nothing more.

The field's default is the favorite, more reliably the bigger the spread.
That is modelled here as a logistic in the spread, and it can be replaced with
real numbers: PoolHost publishes a Pick Distribution page, and
`CrowdModel.fit()` will take those observations and calibrate to your actual
pool.

The default slope is a prior, not a measurement — 0.18 per point puts a
3-point favorite at 63% of the pool and a 10-point favorite at 86%, which is
the shape these pools usually show. Replace it with observations as soon as
you have them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_INTERCEPT = 0.0
DEFAULT_SLOPE = 0.18


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


@dataclass
class CrowdModel:
    """Estimates the share of the pool taking the favorite."""

    intercept: float = DEFAULT_INTERCEPT
    slope: float = DEFAULT_SLOPE
    observations: int = 0          # how many real games this was fit on; 0 = prior

    @property
    def calibrated(self) -> bool:
        return self.observations > 0

    def favorite_share(self, spread: float) -> float:
        """Fraction of the pool expected to take the favorite in this game."""
        return _logistic(self.intercept + self.slope * abs(float(spread)))

    def share_on(self, spread: float, side_is_favorite: bool) -> float:
        """Fraction of the pool expected to be on the given side."""
        favorite = self.favorite_share(spread)
        return favorite if side_is_favorite else 1.0 - favorite

    @classmethod
    def fit(cls, samples: list[tuple[float, float]]) -> "CrowdModel":
        """Least-squares fit of logit(favorite share) on |spread|.

        `samples` are (spread, observed favorite share) pairs, e.g. read off a
        Pick Distribution page. Needs at least two spreads that differ.
        """
        usable = [(abs(float(s)), _logit(float(share))) for s, share in samples]
        if len(usable) < 2:
            raise ValueError("need at least two observations to fit")

        xs = [x for x, _ in usable]
        ys = [y for _, y in usable]
        n = len(xs)
        mean_x, mean_y = sum(xs) / n, sum(ys) / n
        var_x = sum((x - mean_x) ** 2 for x in xs)
        if var_x == 0:
            raise ValueError("all observations are at the same spread")

        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / var_x
        return cls(intercept=mean_y - slope * mean_x, slope=slope, observations=n)
