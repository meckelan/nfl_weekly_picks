import pytest

from weekly_picks.crowd import CrowdModel


def test_pickem_splits_the_pool():
    assert CrowdModel().favorite_share(0) == pytest.approx(0.5)


def test_bigger_favorites_draw_more_of_the_pool():
    crowd = CrowdModel()
    shares = [crowd.favorite_share(s) for s in (0, 3, 7, 10, 14)]
    assert shares == sorted(shares)
    assert shares[-1] > 0.9


def test_sign_of_the_spread_does_not_matter():
    crowd = CrowdModel()
    assert crowd.favorite_share(-7) == crowd.favorite_share(7)


def test_shares_are_complementary():
    crowd = CrowdModel()
    assert crowd.share_on(7, True) + crowd.share_on(7, False) == pytest.approx(1.0)


def test_underdog_side_is_the_minority_on_a_real_favorite():
    assert CrowdModel().share_on(10, side_is_favorite=False) < 0.2


def test_fit_recovers_a_known_curve():
    truth = CrowdModel(intercept=-0.1, slope=0.25)
    samples = [(s, truth.favorite_share(s)) for s in (1, 3, 6, 9, 13)]
    fitted = CrowdModel.fit(samples)
    assert fitted.slope == pytest.approx(0.25, abs=1e-6)
    assert fitted.intercept == pytest.approx(-0.1, abs=1e-6)
    assert fitted.observations == 5


def test_prior_is_flagged_as_uncalibrated():
    assert not CrowdModel().calibrated
    assert CrowdModel.fit([(3, 0.6), (7, 0.8)]).calibrated


def test_fit_rejects_degenerate_input():
    with pytest.raises(ValueError):
        CrowdModel.fit([(3, 0.6)])
    with pytest.raises(ValueError):
        CrowdModel.fit([(3, 0.6), (3, 0.7)])
