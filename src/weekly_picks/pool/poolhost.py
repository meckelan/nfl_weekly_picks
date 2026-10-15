"""Parsing PoolHost's pick sheet.

Written against a real sheet, so this is structure-matched rather than
guesswork. Each game is a `div.game-box` holding two `div.team` blocks:

    <div class="team away-team ...">
      <img src="/images/teamlogos/DET.png" />
      <div class="team-name">Detroit</div>
    </div>
    <div class="team home-team ...">
      <img src="/images/teamlogos/BUF.png" />
      <div class="team-name">Buffalo</div>
      <div class="team-spread">-4.5</div>
    </div>

Two things make this reliable:

  * the team's abbreviation is in its logo filename, so identification never
    depends on matching display text (PoolHost writes the New York and Los
    Angeles teams as "New York (A)" / "New York (N)", which needs conference
    knowledge to read)
  * `div.team-spread` sits inside one of the two team blocks, so the number's
    owner is explicit rather than inferred from column order

The spread is quoted from its own team's point of view: negative means that
team is laying the points.
"""

from __future__ import annotations

import re

from ..teams import UnknownTeamError, resolve
from .models import PoolLine

# PoolHost scopes the sheet to a "current pool" held in the session. Landing on
# /profootball/picks without that context silently redirects to /home, which
# looks exactly like a parse failure. Visiting the pool's own home page (or, as
# a fallback, the pool list) sets it.
PICKS_PATH = "/profootball/picks"
POOL_LIST_PATH = "/mypools"
WARMUP_PATHS = ("/profootball/poolhome", POOL_LIST_PATH)

# Links in the site-wide nav, taken from a real signed-in page. Anything else
# on the pool list is a candidate for entering a pool.
_GLOBAL_NAV = frozenset({
    "/home", "/home/", "/mypools", "/create-a-pool", "/joinprivatepool",
    "/joinpublicpool", "/editprofile", "/changepassword", "/emailverification",
    "/signout", "/faq/faqs", "/help/supportrequest", "/help/contact",
    "/help/aboutus",
})
_NAV_PREFIXES = ("/nfl/", "/ncaatourney/", "/ncaawtourney/", "/worldcup/",
                 "/womenworldcup/", "/collegebowl/", "/profootball/")

_LOGO = re.compile(r"/teamlogos/([A-Za-z0-9]+)\.", re.IGNORECASE)
_GAME_ID = re.compile(r"WeekGames\[(\d+)\]\.GameId", re.IGNORECASE)
_SPREAD = re.compile(r"[+-]?\d+(?:\.\d+)?")


def looks_like_poolhost(html: str) -> bool:
    return "game-box" in html and "team-spread" in html


def describe_page(html: str, url: str = "") -> str:
    """What this page actually is, for when a parse comes back empty.

    A failed scrape is almost always "we were handed the wrong page", not bad
    parsing — so the useful thing to report is the page's identity, not a
    stack trace. Deliberately reports shape rather than content: the sheet
    carries the pool name and member handles, and this output goes into CI
    logs.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else "(no title)"
    headings = [h.get_text(" ", strip=True)[:60]
                for h in soup.find_all(["h1", "h2", "h3"])[:4]]
    forms = [
        f"{(f.get('action') or '(self)')[:60]}"
        f"{' [has password]' if f.find('input', {'type': 'password'}) else ''}"
        for f in soup.find_all("form")[:5]
    ]

    lines = [
        f"  fetched url   : {url or '(unknown)'}",
        f"  page title    : {title}",
        f"  bytes         : {len(html):,}",
        f"  div.game-box  : {len(soup.select('div.game-box'))}",
        f"  div.team      : {len(soup.select('div.team'))}",
        f"  .team-spread  : {len(soup.select('.team-spread'))}",
        f"  <table>       : {len(soup.find_all('table'))}",
        f"  password input: {'YES — this is a login page' if soup.find('input', {'type': 'password'}) else 'no'}",
        f"  headings      : {headings or '(none)'}",
        f"  forms         : {forms or '(none)'}",
    ]
    return "\n".join(lines)


def _team_code(block) -> str | None:
    """Prefer the logo filename; fall back to the display name."""
    image = block.select_one("img[src]")
    if image:
        match = _LOGO.search(image["src"])
        if match:
            try:
                return resolve(match.group(1))
            except UnknownTeamError:
                pass

    name = block.select_one(".team-name")
    if name:
        try:
            return resolve(name.get_text(strip=True))
        except UnknownTeamError:
            return None
    return None


def parse_poolhost(html: str) -> list[PoolLine]:
    """Extract every posted line from a PoolHost pick sheet."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    lines: list[PoolLine] = []

    for box in soup.select("div.game-box"):
        date_node = box.select_one(".game-date")
        kickoff = " ".join(date_node.get_text(" ", strip=True).split()) if date_node else ""

        game_id = ""
        for hidden in box.select('input[type="hidden"][name]'):
            if _GAME_ID.search(hidden.get("name", "")):
                game_id = hidden.get("value", "")
                break

        sides: dict[str, str] = {}
        spread: float | None = None
        spread_side: str | None = None

        for block in box.select("div.team"):
            classes = block.get("class", [])
            side = "home" if "home-team" in classes else "away" if "away-team" in classes else None
            if side is None:
                continue

            code = _team_code(block)
            if code is None:
                continue
            sides[side] = code

            spread_node = block.select_one(".team-spread")
            if spread_node:
                match = _SPREAD.search(spread_node.get_text(strip=True).replace("−", "-"))
                if match:
                    spread, spread_side = float(match.group()), side

        if len(sides) != 2 or spread is None or spread_side is None:
            continue   # a bye slot or an empty column, not a game

        quoted, other = sides[spread_side], sides["away" if spread_side == "home" else "home"]
        favorite, underdog = (quoted, other) if spread <= 0 else (other, quoted)

        lines.append(
            PoolLine(
                favorite=favorite,
                underdog=underdog,
                points=abs(spread),
                raw=f"{sides['away']} at {sides['home']} ({spread_side} {spread:+g})",
                kickoff=kickoff,
                home_team=sides["home"],
                pool_game_id=str(game_id),
            )
        )

    return lines


class SheetNotFound(RuntimeError):
    """Could not reach a page with games on it. Carries the pages tried."""

    def __init__(self, message: str, trail: list[str], last_html: str, last_url: str):
        super().__init__(message)
        self.trail = trail
        self.last_html = last_html
        self.last_url = last_url


def _href_shape(href: str) -> str:
    """A href with its digits masked, safe to print in a public CI log."""
    return re.sub(r"\d+", "N", href)


def pool_entry_candidates(html: str) -> list[str]:
    """Links on the pool list that might select a pool.

    The site-wide nav is known, so anything outside it is a candidate —
    ordered so that the most pool-looking links are tried first.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    seen, candidates = set(), []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if (not href or href.startswith(("javascript:", "#", "http"))
                or href in _GLOBAL_NAV or href in seen):
            continue
        seen.add(href)
        candidates.append(href)

    def rank(href: str) -> tuple:
        # An id in the path is the strongest signal: the bare /profootball/
        # pages are nav, and we already know they redirect without a pool set.
        has_id = bool(re.search(r"/\d+", href))
        pool_ish = "pool" in href.lower() or "select" in href.lower()
        return (not has_id, not pool_ish, href.startswith(_NAV_PREFIXES), len(href))

    return sorted(candidates, key=rank)


def navigate_to_sheet(client, picks_url: str | None = None) -> tuple[list[PoolLine], list[str]]:
    """Fetch the pick sheet, establishing the session's pool context if needed.

    Tries the picks page directly first, since a session that already has a
    pool selected needs nothing else. If that comes back without games, walks
    the warm-up paths — the pool's home page, then the pool list, following the
    first link into a pool — and retries. Returns the lines and a trail of what
    was tried, which is what you want in a log when none of it worked.
    """
    from urllib.parse import urljoin

    picks_url = picks_url or client.url
    base = urljoin(picks_url, "/")
    trail: list[str] = []
    last_html, last_url = "", ""

    def attempt(url: str) -> str:
        nonlocal last_html, last_url
        html = client.fetch(url)
        last_html, last_url = html, client.last_url or url
        boxes = html.count('class="game-box')
        landed = "" if client.last_url in (url, "") else f" -> {client.last_url}"
        trail.append(f"{url}{landed}  ({len(html):,}B, game-box={boxes})")
        return html

    lines = parse_poolhost(attempt(picks_url))
    if lines:
        return lines, trail

    for path in WARMUP_PATHS:
        warm_html = attempt(urljoin(base, path))

        # On the pool list, step into a pool before retrying the sheet. The
        # link that does this is not documented anywhere, so try the few most
        # pool-looking ones and record every candidate's shape for the log.
        if path == POOL_LIST_PATH:
            candidates = pool_entry_candidates(warm_html)
            shapes = sorted({_href_shape(h) for h in candidates})
            trail.append(f"  pool-list candidates ({len(candidates)}): {shapes[:14]}")
            for candidate in candidates[:4]:
                attempt(urljoin(base, candidate))
                lines = parse_poolhost(attempt(picks_url))
                if lines:
                    return lines, trail

        lines = parse_poolhost(attempt(picks_url))
        if lines:
            return lines, trail

    raise SheetNotFound(
        "could not reach a page with games on it", trail, last_html, last_url
    )
