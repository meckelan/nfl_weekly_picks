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
