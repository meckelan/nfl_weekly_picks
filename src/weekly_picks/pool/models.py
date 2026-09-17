"""The pool's posted line for one game.

Deliberately stores *who is favored and by how much* rather than a home-team
spread. Pool sheets don't reliably mark which team is at home, and they don't
need to: the schedule already knows. Orienting the line against the schedule's
home team at join time removes a whole class of silent sign errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass(frozen=True)
class PoolLine:
    favorite: str           # nflverse code of the favored team
    underdog: str           # nflverse code of the other team
    points: float           # how many points the favorite lays; >= 0
    raw: str = ""           # the source row, kept for debugging a bad parse

    # Filled in when the sheet says so (PoolHost does). Metadata only —
    # orientation still comes from the schedule, but these let the join warn
    # when the sheet and the schedule disagree about a game.
    kickoff: str = ""       # as printed on the sheet, e.g. "Thu. Sep. 17 - 08:15 PM"
    home_team: str = ""     # the side the sheet marks as home
    pool_game_id: str = ""  # the pool's own id, needed to submit a pick

    def __post_init__(self) -> None:
        if self.points < 0:
            raise ValueError(f"points must be non-negative, got {self.points}")
        if self.favorite == self.underdog:
            raise ValueError(f"a team cannot play itself: {self.favorite}")

    @property
    def teams(self) -> frozenset[str]:
        return frozenset({self.favorite, self.underdog})

    def home_spread(self, home_team: str) -> float:
        """This line on the home-favored-positive convention used everywhere else."""
        if home_team == self.favorite:
            return self.points
        if home_team == self.underdog:
            return -self.points
        raise ValueError(f"{home_team} is not in this game ({self.favorite}/{self.underdog})")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PoolSheet:
    """Every line the pool posted for one week, plus where it came from."""

    season: int
    week: int
    lines: list[PoolLine] = field(default_factory=list)
    source: str = ""
    captured_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def __len__(self) -> int:
        return len(self.lines)

    def by_teams(self) -> dict[frozenset[str], PoolLine]:
        return {line.teams: line for line in self.lines}

    def to_dict(self) -> dict:
        return {
            "season": self.season,
            "week": self.week,
            "source": self.source,
            "captured_at": self.captured_at,
            "lines": [line.to_dict() for line in self.lines],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "PoolSheet":
        return cls(
            season=int(payload["season"]),
            week=int(payload["week"]),
            lines=[PoolLine(**row) for row in payload.get("lines", [])],
            source=payload.get("source", ""),
            captured_at=payload.get("captured_at", ""),
        )
