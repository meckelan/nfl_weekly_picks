"""Reaching the sheet when the session has no pool selected yet.

PoolHost scopes the pick sheet to a "current pool" kept in the session.
Requesting the picks page without it redirects to /home — a 200 response, a
valid page, no games on it — which is indistinguishable from a parse failure
unless you look at where you landed. These tests drive that path with a stub
client, since the real one cannot be exercised from CI.
"""

from pathlib import Path

import pytest

from weekly_picks.pool.poolhost import SheetNotFound, navigate_to_sheet

SHEET = (Path(__file__).parent / "fixtures" / "poolhost_sheet.html").read_text()
HOME = ("<html><head><title>Office Pool Manager - Home</title></head><body>"
        "<h3>NFL</h3><h3>College Bowl</h3></body></html>")
POOL_LIST = ('<html><body><a href="/profootball/poolhome">The Memorial NFL Pool</a>'
             '<a href="/profootball/picks">Make/Change Picks</a></body></html>')


class StubClient:
    """Serves pages by path and records every request."""

    def __init__(self, pages: dict[str, str], url="https://www.poolhost.com/profootball/picks"):
        self.pages = pages
        self.url = url
        self.last_url = ""
        self.requested: list[str] = []

    def fetch(self, url=None):
        target = url or self.url
        path = target.replace("https://www.poolhost.com", "")
        self.requested.append(path)
        body, landed = self.pages.get(path, (HOME, "/home/True")) if isinstance(
            self.pages.get(path), tuple) else (self.pages.get(path, HOME), path)
        self.last_url = f"https://www.poolhost.com{landed}"
        return body


def test_a_session_that_already_has_a_pool_goes_straight_there():
    client = StubClient({"/profootball/picks": SHEET})
    lines, trail = navigate_to_sheet(client)
    assert len(lines) == 3
    assert client.requested == ["/profootball/picks"]     # no needless warm-up
    assert len(trail) == 1


def test_pool_home_warms_up_the_context():
    """First picks request redirects home; after /poolhome it works."""
    served = {"picks": 0}

    class Warming(StubClient):
        def fetch(self, url=None):
            target = url or self.url
            path = target.replace("https://www.poolhost.com", "")
            self.requested.append(path)
            if path == "/profootball/picks":
                served["picks"] += 1
                if served["picks"] == 1:
                    self.last_url = "https://www.poolhost.com/home/True"
                    return HOME
                self.last_url = target
                return SHEET
            self.last_url = target
            return HOME

    client = Warming({})
    lines, trail = navigate_to_sheet(client)
    assert len(lines) == 3
    assert client.requested == [
        "/profootball/picks", "/profootball/poolhome", "/profootball/picks"
    ]


def test_falls_back_to_stepping_through_the_pool_list():
    """Neither the sheet nor pool home works until a pool is entered."""
    state = {"entered": False}

    class ViaList(StubClient):
        def fetch(self, url=None):
            target = url or self.url
            path = target.replace("https://www.poolhost.com", "")
            self.requested.append(path)
            self.last_url = target
            if path == "/mypools":
                return POOL_LIST
            if path == "/profootball/poolhome":
                state["entered"] = True
                return HOME
            if path == "/profootball/picks":
                return SHEET if state["entered"] and "/mypools" in self.requested else HOME
            return HOME

    client = ViaList({})
    lines, _ = navigate_to_sheet(client)
    assert len(lines) == 3
    assert "/mypools" in client.requested


def test_gives_up_with_the_trail_it_walked():
    client = StubClient({})                                # every page is /home
    with pytest.raises(SheetNotFound) as caught:
        navigate_to_sheet(client)
    error = caught.value
    assert "/profootball/picks" in " ".join(error.trail)
    assert "/mypools" in " ".join(error.trail)
    assert error.last_html == HOME                         # kept for diagnostics
    assert "game-box=0" in " ".join(error.trail)


# ── finding the link that selects a pool ─────────────────────────────────────
NAV_AND_POOLS = """<html><body>
  <a href="/home">Home</a><a href="/mypools">Switch Pools</a>
  <a href="/signout">Log Out</a><a href="/nfl/spreads">Point Spreads</a>
  <a href="/profootball/poolhome">Pool Home</a>
  <a href="/profootball/poolhome/48213">The Memorial NFL Pool</a>
  <a href="/selectpool/48213">Enter</a>
  <a href="javascript:;">Picks</a><a href="https://twitter.com/PoolHost">x</a>
</body></html>"""


def test_pool_entry_candidates_prefers_links_carrying_an_id():
    from weekly_picks.pool.poolhost import pool_entry_candidates

    candidates = pool_entry_candidates(NAV_AND_POOLS)
    assert candidates[0] in ("/selectpool/48213", "/profootball/poolhome/48213")
    # The bare nav page is known to redirect without a pool selected, so it
    # must not be tried before the id-bearing links.
    assert candidates.index("/profootball/poolhome") > 1


def test_pool_entry_candidates_drops_the_site_nav():
    from weekly_picks.pool.poolhost import pool_entry_candidates

    candidates = pool_entry_candidates(NAV_AND_POOLS)
    for nav in ("/home", "/mypools", "/signout", "javascript:;",
                "https://twitter.com/PoolHost"):
        assert nav not in candidates


def test_href_shape_masks_ids_for_public_logs():
    from weekly_picks.pool.poolhost import _href_shape

    assert _href_shape("/profootball/poolhome/48213") == "/profootball/poolhome/N"
