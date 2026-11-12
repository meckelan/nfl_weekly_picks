"""The market reference, and why it is taken as a median.

nflverse publishes one spread a day. The line-edge signal lives at half-point
resolution, so a single stale or odd number invents edges that are not there —
it was caught reading 1.5 on a game books were showing at 2.5. Taking the
median across books is the fix, and these tests pin that behaviour down.
"""

import os

import pandas as pd
import pytest

from weekly_picks.market import (
    NflverseMarket, OddsApiMarket, Quote, resolve_source, save_snapshot,
)


def event(home, away, points, key="spreads"):
    """One API event whose books quote `points` for the home team."""
    return {
        "home_team": home, "away_team": away,
        "bookmakers": [
            {"key": f"book{i}", "markets": [{"key": key, "outcomes": [
                {"name": home, "price": -110, "point": p},
                {"name": away, "price": -110, "point": -p},
            ]}]}
            for i, p in enumerate(points)
        ],
    }


# ── the sign convention, which is the thing most likely to invert ───────────
def test_a_book_spread_is_negated_to_our_convention():
    """Books quote -2.5 for a home favourite; we store +2.5."""
    quotes = OddsApiMarket.parse([event("New York Giants", "Washington Commanders", [-2.5])])
    assert quotes[frozenset({"NYG", "WAS"})].home_spread == 2.5


def test_a_home_underdog_comes_through_negative():
    quotes = OddsApiMarket.parse([event("Dallas Cowboys", "San Francisco 49ers", [4.5])])
    assert quotes[frozenset({"DAL", "SF"})].home_spread == -4.5


# ── the median, which is the point of the exercise ──────────────────────────
def test_the_median_ignores_a_single_odd_book():
    """Two books at -2.5 and one at -1.5: the answer is 2.5, not 2.17."""
    quotes = OddsApiMarket.parse(
        [event("New York Giants", "Washington Commanders", [-2.5, -2.5, -1.5])]
    )
    quote = quotes[frozenset({"NYG", "WAS"})]
    assert quote.home_spread == 2.5
    assert quote.books == 3
    assert quote.spread_of_books == 1.0      # how far apart the books were


def test_book_disagreement_is_reported():
    quotes = OddsApiMarket.parse(
        [event("Kansas City Chiefs", "Denver Broncos", [-3.0, -3.5, -2.5, -7.0])]
    )
    assert quotes[frozenset({"KC", "DEN"})].spread_of_books == 4.5


# ── robustness, since this payload comes from outside ──────────────────────
def test_non_spread_markets_are_ignored():
    payload = [event("Chicago Bears", "Green Bay Packers", [-3.0], key="totals")]
    assert OddsApiMarket.parse(payload) == {}


def test_unresolvable_teams_are_skipped_not_guessed():
    payload = [event("Some College Team", "Another Club", [-3.0])]
    assert OddsApiMarket.parse(payload) == {}


def test_a_book_with_no_point_is_skipped():
    payload = [{
        "home_team": "Miami Dolphins", "away_team": "New England Patriots",
        "bookmakers": [{"key": "b", "markets": [{"key": "spreads", "outcomes": [
            {"name": "Miami Dolphins", "price": -110},            # no point
        ]}]}],
    }]
    assert OddsApiMarket.parse(payload) == {}


def test_missing_key_raises_rather_than_fetching():
    with pytest.raises(RuntimeError, match="ODDS_API_KEY"):
        OddsApiMarket(api_key="").fetch()


# ── the fallback path ───────────────────────────────────────────────────────
def test_nflverse_source_reads_the_schedule():
    games = pd.DataFrame([
        {"season": 2026, "week": 10, "away_team": "WAS", "home_team": "NYG", "spread_line": 1.5},
        {"season": 2026, "week": 10, "away_team": "SF", "home_team": "DAL", "spread_line": None},
    ])
    quotes = NflverseMarket(games).quotes(2026, 10)
    assert quotes[frozenset({"WAS", "NYG"})].home_spread == 1.5
    assert frozenset({"SF", "DAL"}) not in quotes      # no line, not a zero
    assert quotes[frozenset({"WAS", "NYG"})].books == 0


def test_source_choice_follows_the_key(monkeypatch):
    games = pd.DataFrame(columns=["season", "week", "away_team", "home_team", "spread_line"])
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    source, note = resolve_source(games)
    assert isinstance(source, NflverseMarket) and "no ODDS_API_KEY" in note

    monkeypatch.setenv("ODDS_API_KEY", "x")
    source, note = resolve_source(games)
    assert isinstance(source, OddsApiMarket) and "median" in note


# ── the snapshot, so grading cannot re-read a moved market ─────────────────
def test_snapshot_records_what_the_market_said(tmp_path):
    quotes = {frozenset({"WAS", "NYG"}): Quote("WAS", "NYG", 2.5, books=7, spread_of_books=1.0)}
    path = save_snapshot(quotes, 2026, 10, "test source", directory=tmp_path)
    import json
    saved = json.loads(path.read_text())
    assert saved["week"] == 10 and saved["source"] == "test source"
    assert saved["quotes"][0]["home_spread"] == 2.5
    assert saved["quotes"][0]["books"] == 7
    assert saved["fetched_at"].endswith("Z")
