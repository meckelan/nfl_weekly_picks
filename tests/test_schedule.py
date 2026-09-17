"""Guards on the upstream data.

The whole project reads a spread's sign one way. If nflverse ever flips that
convention, every pick inverts and nothing else in the code would notice — so
the convention is asserted against the real file rather than assumed.
"""

import pandas as pd
import pytest

from weekly_picks.schedule import GAMES_CSV, current_week, load_games, market_lines

pytestmark = pytest.mark.skipif(
    not GAMES_CSV.exists(), reason="run scripts/fetch_data.py first"
)


@pytest.fixture(scope="module")
def games():
    return load_games()


def test_result_is_the_home_margin(games):
    played = games.dropna(subset=["result", "home_score", "away_score"])
    assert ((played.home_score - played.away_score) == played.result).all()


def test_positive_spread_means_the_home_team_is_favored(games):
    played = games.dropna(subset=["result", "spread_line"])
    home_favored = played[played.spread_line > 0]
    away_favored = played[played.spread_line < 0]

    assert (home_favored.result > 0).mean() > 0.60
    assert (away_favored.result > 0).mean() < 0.40
    # Moneylines agree: the favored side is the one priced negative.
    assert home_favored.home_moneyline.mean() < 0


def test_the_closing_line_is_close_to_unbiased(games):
    played = games.dropna(subset=["result", "spread_line"])
    error = played.result - played.spread_line
    assert abs(error.mean()) < 0.5           # no systematic tilt to either side
    assert 12.5 < error.std() < 14.0         # the familiar NFL spread of outcomes
    assert 0.47 < (error > 0).mean() < 0.53  # neither side covers materially more


def test_current_week_is_the_next_one_to_kick_off(games):
    season = 2025
    slate = games[games.season == season]
    week3_start = slate[slate.week == 3].kickoff.min()
    assert current_week(games, season, now=week3_start - pd.Timedelta(hours=1)) == 3
    # Mid-week 3, once some games have kicked off, week 3 is still current.
    assert current_week(games, season, now=week3_start + pd.Timedelta(hours=1)) == 3


def test_market_lines_returns_one_row_per_game(games):
    week = market_lines(games, 2025, 1)
    assert len(week) == 16
    assert week.market_spread.notna().all()
    assert set(week.columns) >= {"game_id", "away_team", "home_team", "market_spread"}
