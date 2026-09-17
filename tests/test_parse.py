import pytest

from weekly_picks.pool.parse import ParseError, parse_sheet, parse_text


def as_tuples(lines):
    return [(l.favorite, l.points, l.underdog) for l in lines]


def test_team_cell_carrying_its_own_number():
    html = """<table>
    <tr><td>1</td><td>New England -3.5</td><td>Buffalo Bills</td></tr>
    <tr><td>2</td><td>Dallas Cowboys</td><td>Philadelphia -2.5</td></tr></table>"""
    assert as_tuples(parse_sheet(html)) == [("NE", 3.5, "BUF"), ("PHI", 2.5, "DAL")]


def test_standalone_spread_cell_belongs_to_the_team_before_it():
    html = """<table>
    <tr><td>Sun 1:00</td><td>Green Bay</td><td>-6.5</td><td>Chicago</td></tr>
    <tr><td>Sun 4:25</td><td>Houston</td><td>+2.5</td><td>Indianapolis</td></tr></table>"""
    assert as_tuples(parse_sheet(html)) == [("GB", 6.5, "CHI"), ("IND", 2.5, "HOU")]


def test_two_rows_per_game_with_equal_and_opposite_numbers():
    html = """<table>
    <tr><td>Miami</td><td>+4.5</td></tr>
    <tr><td>New York Jets</td><td>-4.5</td></tr></table>"""
    assert as_tuples(parse_sheet(html)) == [("NYJ", 4.5, "MIA")]


def test_mismatched_pair_is_rejected_not_guessed():
    html = """<table>
    <tr><td>Miami</td><td>+4.5</td></tr>
    <tr><td>Jets</td><td>-7</td></tr></table>"""
    with pytest.raises(ParseError):
        parse_sheet(html)


def test_records_and_kickoff_times_are_not_read_as_spreads():
    html = """<table><tr><td>Sun 4:25 PM</td><td>Baltimore (3-1)</td>
    <td>-6.5</td><td>Cincinnati (2-2)</td></tr></table>"""
    assert as_tuples(parse_sheet(html)) == [("BAL", 6.5, "CIN")]


def test_pickem_is_a_zero_point_line():
    html = "<table><tr><td>Denver</td><td>PK</td><td>Raiders</td></tr></table>"
    line = parse_sheet(html)[0]
    assert line.points == 0 and line.teams == {"DEN", "LV"}


def test_login_wall_raises_instead_of_returning_an_empty_sheet():
    with pytest.raises(ParseError):
        parse_sheet("<html><body><form>Please log in</form></body></html>")


def test_text_keeps_multi_word_team_names_together():
    text = "New England -3.5 at Buffalo Bills\nGreen Bay -6.5 Chicago Bears"
    assert as_tuples(parse_text(text)) == [("NE", 3.5, "BUF"), ("GB", 6.5, "CHI")]


def test_text_reads_the_underdog_side_correctly():
    assert as_tuples(parse_text("Buffalo +3.5 Kansas City")) == [("KC", 3.5, "BUF")]


@pytest.mark.parametrize("text,points", [
    ("Seattle -3½ Arizona", 3.5),
    ("Tampa Bay -7 1/2 Atlanta", 7.5),
    ("Seattle -3 Arizona", 3.0),
])
def test_half_point_spellings(text, points):
    assert parse_text(text)[0].points == points


def test_tab_separated_paste():
    assert as_tuples(parse_text("Green Bay\t-6.5\tChicago")) == [("GB", 6.5, "CHI")]
