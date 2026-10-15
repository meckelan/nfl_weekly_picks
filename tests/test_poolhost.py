"""The PoolHost sheet reader, against a trimmed copy of the real markup."""

from pathlib import Path

import pytest

from weekly_picks.pool import parse_sheet
from weekly_picks.pool.poolhost import looks_like_poolhost, parse_poolhost

FIXTURE = Path(__file__).parent / "fixtures" / "poolhost_sheet.html"


@pytest.fixture(scope="module")
def lines():
    return parse_poolhost(FIXTURE.read_text())


def test_reads_every_game_and_skips_empty_columns(lines):
    assert len(lines) == 3


def test_home_favorite(lines):
    """Buffalo at home, quoted -4.5, so Buffalo lays 4.5."""
    line = lines[0]
    assert (line.favorite, line.points, line.underdog) == ("BUF", 4.5, "DET")
    assert line.home_team == "BUF"


def test_home_underdog_flips_the_favorite(lines):
    """The Jets at home quoted +3.5 means Green Bay is favored."""
    line = lines[1]
    assert (line.favorite, line.points, line.underdog) == ("GB", 3.5, "NYJ")
    assert line.home_team == "NYJ"


def test_zero_is_a_pickem(lines):
    assert lines[2].points == 0
    assert lines[2].teams == {"SEA", "ARI"}


def test_conference_tagged_city_names(lines):
    """PoolHost writes the Jets as 'New York (A)'; the logo settles it anyway."""
    assert lines[1].home_team == "NYJ"


def test_poolhost_abbreviations_are_translated(lines):
    """AZ -> ARI. Their logo codes are not all nflverse codes."""
    assert lines[2].home_team == "ARI"


def test_carries_the_pool_game_id_and_kickoff(lines):
    assert [line.pool_game_id for line in lines] == ["65", "71", "76"]
    assert lines[0].kickoff == "Thu. Sep. 17 - 08:15 PM"


def test_detected_and_routed_automatically(lines):
    html = FIXTURE.read_text()
    assert looks_like_poolhost(html)
    assert [l.teams for l in parse_sheet(html)] == [l.teams for l in lines]


def test_generic_sheets_are_not_mistaken_for_poolhost():
    assert not looks_like_poolhost("<table><tr><td>Green Bay</td><td>-6.5</td></tr></table>")


# ── diagnostics ──────────────────────────────────────────────────────────────
def test_describe_page_identifies_a_login_page():
    from weekly_picks.pool.poolhost import describe_page

    report = describe_page(
        '<html><head><title>PoolHost - Login</title></head><body>'
        '<form action="/login.asp"><input name="u"><input type="password" name="p">'
        '</form></body></html>',
        "https://www.poolhost.com/login.asp",
    )
    assert "this is a login page" in report
    assert "login.asp" in report
    assert "div.game-box  : 0" in report


def test_describe_page_identifies_a_real_sheet():
    from weekly_picks.pool.poolhost import describe_page

    report = describe_page(FIXTURE.read_text(), "https://www.poolhost.com/profootball/picks")
    assert "div.game-box  : 3" in report
    assert "password input: no" in report
