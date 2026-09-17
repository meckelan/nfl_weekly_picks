import pytest

from weekly_picks.teams import UnknownTeamError, canonical, resolve


@pytest.mark.parametrize(
    "text,expected",
    [
        ("New England", "NE"), ("N.E. Patriots", "NE"), ("NWE", "NE"), ("Pats", "NE"),
        ("san francisco 49ers", "SF"), ("Niners", "SF"),
        ("New York Giants", "NYG"), ("NY Jets", "NYJ"), ("Jets", "NYJ"),
        ("Green Bay", "GB"), ("KC Chiefs", "KC"), ("Jags", "JAX"), ("JAC", "JAX"),
        ("WSH", "WAS"), ("Commanders", "WAS"), ("Washington Redskins", "WAS"),
        ("at New England", "NE"), ("@ Chiefs", "KC"), ("Cardinals (-3)", "ARI"),
    ],
)
def test_resolves_common_spellings(text, expected):
    assert resolve(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [("Oakland Raiders", "LV"), ("San Diego", "LAC"), ("St. Louis Rams", "LA")],
)
def test_relocated_franchises_map_to_current_code(text, expected):
    assert resolve(text) == expected


def test_la_teams_are_not_confused():
    assert resolve("Los Angeles Rams") == "LA"
    assert resolve("Los Angeles Chargers") == "LAC"


def test_canonical_maps_historical_codes():
    assert canonical("OAK") == "LV"
    assert canonical("SD") == "LAC"
    assert canonical("STL") == "LA"
    assert canonical("KC") == "KC"


def test_unknown_raises_rather_than_guessing():
    with pytest.raises(UnknownTeamError):
        resolve("Toronto Argonauts")


def test_default_suppresses_the_error():
    assert resolve("Toronto Argonauts", default="???") == "???"
