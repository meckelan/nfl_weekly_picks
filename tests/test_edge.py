import pandas as pd
import pytest

from weekly_picks.calibration import EdgeCalibration
from weekly_picks.edge import compare
from weekly_picks.pool.models import PoolLine, PoolSheet


@pytest.fixture(scope="module")
def calibration():
    games = pd.DataFrame(
        {
            "season": [2020] * 8,
            # errors: -4 -2 -1 0 +1 +2 +4 +6  (margin - spread)
            "result": [0, 2, 3, 4, 5, 6, 8, 10],
            "spread_line": [4] * 8,
        }
    )
    return EdgeCalibration.from_games(games)


def market_frame(**overrides):
    row = {
        "game_id": "2026_05_NE_BUF", "season": 2026, "week": 5,
        "kickoff": pd.Timestamp("2026-10-04 13:00"), "weekday": "Sunday",
        "away_team": "NE", "home_team": "BUF", "market_spread": 3.0,
        "total_line": 44.5, "away_moneyline": 140, "home_moneyline": -165,
        "location": "Home",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def sheet_with(favorite, underdog, points):
    return PoolSheet(season=2026, week=5,
                     lines=[PoolLine(favorite=favorite, underdog=underdog, points=points)])


# ── the sign convention, which is the thing most likely to silently invert ──
def test_home_spread_is_positive_when_home_is_favored():
    line = PoolLine(favorite="BUF", underdog="NE", points=3.0)
    assert line.home_spread("BUF") == 3.0
    assert line.home_spread("NE") == -3.0


def test_pool_asking_home_to_lay_more_than_market_means_take_the_away_side(calibration):
    # market: BUF -3. pool: BUF -5. Buffalo is overpriced at the pool.
    row = compare(sheet_with("BUF", "NE", 5.0), market_frame(), calibration).iloc[0]
    assert row["side"] == "away"
    assert row["pick"] == "NE"
    assert row["edge_points"] == 2.0
    assert row["pick_line"] == 5.0        # New England taking +5


def test_pool_asking_home_to_lay_less_than_market_means_take_the_home_side(calibration):
    # market: BUF -3. pool: BUF -1. Buffalo is cheap at the pool.
    row = compare(sheet_with("BUF", "NE", 1.0), market_frame(), calibration).iloc[0]
    assert row["side"] == "home"
    assert row["pick"] == "BUF"
    assert row["edge_points"] == 2.0
    assert row["pick_line"] == -1.0       # Buffalo laying 1


def test_agreement_yields_no_pick(calibration):
    row = compare(sheet_with("BUF", "NE", 3.0), market_frame(), calibration).iloc[0]
    assert row["edge_points"] == 0
    assert row["pick"] is None
    assert row["status"] == "lines agree"


def test_underdog_flip_is_handled(calibration):
    # market has the home team as a 3-point dog; the pool has it as a 1-point dog.
    row = compare(sheet_with("NE", "BUF", 1.0), market_frame(market_spread=-3.0), calibration).iloc[0]
    assert row["pool_spread"] == -1.0
    assert row["side"] == "away" and row["pick"] == "NE"
    assert row["edge_points"] == 2.0


def test_missing_pool_line_is_reported_not_dropped(calibration):
    empty = PoolSheet(season=2026, week=5)
    row = compare(empty, market_frame(), calibration).iloc[0]
    assert row["status"] == "no pool line"
    assert pd.isna(row["edge_points"])


def test_pool_line_for_an_unscheduled_game_is_surfaced(calibration):
    sheet = sheet_with("BUF", "NE", 3.0)
    sheet.lines.append(PoolLine(favorite="KC", underdog="LV", points=7.0))
    table = compare(sheet, market_frame(), calibration)
    assert "pool line has no scheduled game" in set(table["status"])


# ── calibration ────────────────────────────────────────────────────────────
def test_zero_edge_is_a_coin_flip(calibration):
    assert calibration.win_probability(0) == pytest.approx(0.5)


def test_win_probability_rises_with_the_edge(calibration):
    probs = [calibration.win_probability(d) for d in (0, 1, 2, 3, 4)]
    assert probs == sorted(probs)
    assert probs[-1] > probs[0]


def test_edge_sign_does_not_matter(calibration):
    assert calibration.win_probability(-2) == calibration.win_probability(2)


def test_roundtrip_through_disk(tmp_path, calibration):
    path = calibration.save(tmp_path / "cal.json")
    assert EdgeCalibration.load(path).win_probability(2) == calibration.win_probability(2)
