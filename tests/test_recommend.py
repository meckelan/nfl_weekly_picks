import pandas as pd
import pytest

from weekly_picks.crowd import CrowdModel
from weekly_picks.recommend import recommend, to_frame


def row(**overrides):
    base = {
        "game_id": "g1", "away_team": "NE", "home_team": "BUF",
        "pool_spread": 3.0, "market_spread": 3.0, "edge_points": 0.0,
        "side": "none", "pick": None, "pick_line": None, "win_prob": 0.5,
        "status": "lines agree",
    }
    base.update(overrides)
    return pd.DataFrame([base])


def test_lines_agree_means_take_the_underdog():
    """No accuracy edge, so the pick goes to differentiation."""
    rec = recommend(row())[0]
    assert rec.pick == "NE"                 # BUF favored by 3, so NE is the dog
    assert rec.win_prob == 0.5
    assert "fade" in rec.reason


def test_underdog_is_the_minority_side():
    rec = recommend(row(pool_spread=10.0, market_spread=10.0))[0]
    assert rec.pick == "NE"
    assert rec.crowd_share < 0.2
    assert rec.differentiation > 0.8


def test_a_real_line_edge_overrides_the_fade():
    """Accuracy edge beats differentiation, even when it lands on the favorite."""
    rec = recommend(row(pool_spread=1.0, market_spread=3.0, edge_points=2.0,
                        side="home", pick="BUF", win_prob=0.573))[0]
    assert rec.pick == "BUF"
    assert rec.win_prob == pytest.approx(0.573)
    assert "line edge" in rec.reason


def test_edges_below_the_threshold_do_not_override():
    rec = recommend(row(pool_spread=2.5, market_spread=3.0, edge_points=0.5,
                        side="away", pick="NE", win_prob=0.523),
                    min_edge=1.0)[0]
    assert rec.win_prob == 0.5
    assert "fade" in rec.reason


def test_home_underdog_is_picked_when_the_road_team_is_favored():
    rec = recommend(row(pool_spread=-6.0, market_spread=-6.0))[0]
    assert rec.pick == "BUF"                # home team getting 6
    assert rec.line == pytest.approx(6.0)   # taking points


def test_line_is_negative_when_laying_points():
    rec = recommend(row(pool_spread=-4.0, market_spread=-8.0, edge_points=4.0,
                        side="away", pick="NE", win_prob=0.63))[0]
    assert rec.pick == "NE"
    assert rec.line == pytest.approx(-4.0)  # New England lays 4


def test_true_pickem_is_labelled_not_faded():
    rec = recommend(row(pool_spread=0.0, market_spread=0.0))[0]
    assert rec.crowd_share == pytest.approx(0.5)
    assert "pick'em" in rec.reason


def test_games_without_any_line_are_skipped():
    assert recommend(row(pool_spread=None, market_spread=None)) == []


def test_crowd_model_is_honoured():
    flat = CrowdModel(intercept=0.0, slope=0.0)      # a pool that ignores spreads
    rec = recommend(row(pool_spread=14.0, market_spread=14.0), crowd=flat)[0]
    assert rec.crowd_share == pytest.approx(0.5)


def test_frame_has_one_row_per_game():
    frame = to_frame(recommend(row()))
    assert len(frame) == 1
    assert {"pick", "reason", "win_prob", "crowd_share", "differentiation"} <= set(frame.columns)
