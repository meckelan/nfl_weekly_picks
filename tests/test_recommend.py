import pandas as pd
import pytest

from weekly_picks.crowd import CrowdModel
from weekly_picks.recommend import (
    RATE_ANY_DOG, RATE_EARLY_ROAD_DOG, RATE_ROAD_DOG,
    recommend, to_frame, underdog_rule,
)


def row(**overrides):
    base = {
        "game_id": "g1", "season": 2026, "week": 9,
        "away_team": "NE", "home_team": "BUF",
        "pool_spread": 3.0, "market_spread": 3.0, "edge_points": 0.0,
        "side": "none", "pick": None, "pick_line": None, "win_prob": 0.5,
        "status": "lines agree",
    }
    base.update(overrides)
    return pd.DataFrame([base])


# ── the underdog rule ────────────────────────────────────────────────────────
def test_lines_agree_means_take_the_underdog():
    rec = recommend(row())[0]
    assert rec.pick == "NE"                 # BUF favored by 3, NE is the dog
    assert "underdog" in rec.reason


def test_road_dog_rate_beats_the_generic_one():
    assert RATE_ROAD_DOG > RATE_ANY_DOG
    rec = recommend(row())[0]               # NE is the away dog
    assert rec.win_prob == pytest.approx(RATE_ROAD_DOG)


def test_home_dog_gets_the_generic_rate():
    rec = recommend(row(pool_spread=-6.0, market_spread=-6.0))[0]
    assert rec.pick == "BUF"                # home team getting 6
    assert rec.win_prob == pytest.approx(RATE_ANY_DOG)
    assert rec.line == pytest.approx(6.0)


def test_early_season_road_dogs_rate_highest():
    rec = recommend(row(week=2))[0]
    assert rec.win_prob == pytest.approx(RATE_EARLY_ROAD_DOG)
    assert "early-season road" in rec.reason


def test_week_five_is_no_longer_early_season():
    assert underdog_rule(4, dog_is_road=True)[0] == RATE_EARLY_ROAD_DOG
    assert underdog_rule(5, dog_is_road=True)[0] == RATE_ROAD_DOG


def test_missing_week_falls_back_to_the_generic_rule():
    assert underdog_rule(None, dog_is_road=False)[0] == RATE_ANY_DOG


# ── line edges take priority ─────────────────────────────────────────────────
def test_a_real_line_edge_overrides_the_underdog_rule():
    rec = recommend(row(pool_spread=1.0, market_spread=3.0, edge_points=2.0,
                        side="home", pick="BUF", win_prob=0.573))[0]
    assert rec.pick == "BUF"                # the favorite, because the edge says so
    assert rec.win_prob == pytest.approx(0.573)
    assert "line edge" in rec.reason


def test_edges_below_the_threshold_do_not_override():
    rec = recommend(row(pool_spread=2.5, market_spread=3.0, edge_points=0.5,
                        side="away", pick="NE", win_prob=0.523),
                    min_edge=1.0)[0]
    assert "underdog" in rec.reason


def test_line_is_negative_when_laying_points():
    rec = recommend(row(pool_spread=-4.0, market_spread=-8.0, edge_points=4.0,
                        side="away", pick="NE", win_prob=0.63))[0]
    assert rec.pick == "NE"
    assert rec.line == pytest.approx(-4.0)  # New England lays 4


# ── edges ────────────────────────────────────────────────────────────────────
def test_true_pickem_has_no_underdog_to_take():
    rec = recommend(row(pool_spread=0.0, market_spread=0.0))[0]
    assert rec.win_prob == 0.5
    assert "pick'em" in rec.reason


def test_games_without_any_line_are_skipped():
    assert recommend(row(pool_spread=None, market_spread=None)) == []


def test_crowd_share_is_still_reported():
    rec = recommend(row(pool_spread=10.0, market_spread=10.0))[0]
    assert rec.crowd_share < 0.2            # taking the dog is the unpopular side
    assert rec.differentiation > 0.8


def test_crowd_model_is_honoured():
    flat = CrowdModel(intercept=0.0, slope=0.0)
    rec = recommend(row(pool_spread=14.0, market_spread=14.0), crowd=flat)[0]
    assert rec.crowd_share == pytest.approx(0.5)


def test_frame_has_one_row_per_game():
    frame = to_frame(recommend(row()))
    assert len(frame) == 1
    assert {"pick", "reason", "win_prob", "crowd_share"} <= set(frame.columns)
