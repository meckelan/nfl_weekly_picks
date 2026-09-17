"""Resolving free-text team names to nflverse team codes.

The pool site writes team names however it likes ("New England", "N.E.
Patriots", "NWE", "Pats"). Everything downstream keys on nflverse codes, so
every string that crosses the boundary from the pool site goes through
`resolve()` first.

Relocated franchises are mapped to their *current* code (OAK -> LV, SD -> LAC,
STL -> LA), because pool lines are always for upcoming games. Historical
schedule rows keep their original codes; `canonical()` normalizes those when
joining old seasons.
"""

from __future__ import annotations

import re
import unicodedata

# code -> (city/region names, nicknames)
_TEAMS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "ARI": (("arizona", "phoenix"), ("cardinals", "cards")),
    "ATL": (("atlanta",), ("falcons",)),
    "BAL": (("baltimore",), ("ravens",)),
    "BUF": (("buffalo",), ("bills",)),
    "CAR": (("carolina",), ("panthers",)),
    "CHI": (("chicago",), ("bears",)),
    "CIN": (("cincinnati",), ("bengals",)),
    "CLE": (("cleveland",), ("browns",)),
    "DAL": (("dallas",), ("cowboys",)),
    "DEN": (("denver",), ("broncos",)),
    "DET": (("detroit",), ("lions",)),
    "GB":  (("green bay", "greenbay"), ("packers", "pack")),
    "HOU": (("houston",), ("texans",)),
    "IND": (("indianapolis", "indy"), ("colts",)),
    "JAX": (("jacksonville",), ("jaguars", "jags")),
    "KC":  (("kansas city", "kansascity"), ("chiefs",)),
    "LA":  (("los angeles rams", "la rams", "st louis", "saint louis"), ("rams",)),
    "LAC": (("los angeles chargers", "la chargers", "san diego"), ("chargers", "bolts")),
    "LV":  (("las vegas", "oakland", "vegas"), ("raiders",)),
    "MIA": (("miami",), ("dolphins", "fins")),
    "MIN": (("minnesota",), ("vikings", "vikes")),
    "NE":  (("new england", "newengland"), ("patriots", "pats")),
    "NO":  (("new orleans", "neworleans"), ("saints",)),
    "NYG": (("new york giants", "ny giants"), ("giants",)),
    "NYJ": (("new york jets", "ny jets"), ("jets",)),
    "PHI": (("philadelphia", "philly"), ("eagles",)),
    "PIT": (("pittsburgh",), ("steelers",)),
    "SEA": (("seattle",), ("seahawks", "hawks")),
    "SF":  (("san francisco", "sanfrancisco"), ("49ers", "niners", "forty niners")),
    "TB":  (("tampa bay", "tampabay", "tampa"), ("buccaneers", "bucs")),
    "TEN": (("tennessee",), ("titans",)),
    "WAS": (("washington",), ("commanders", "redskins", "football team")),
}

# Alternate abbreviations used by other data providers and by pool sites.
_ABBREV_ALIASES: dict[str, str] = {
    "ARZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
    "JAC": "JAX", "KAN": "KC", "KCC": "KC", "GNB": "GB", "GBP": "GB",
    "NWE": "NE", "NEP": "NE", "NOR": "NO", "NOS": "NO",
    "SFO": "SF", "SF49": "SF", "TAM": "TB", "TBB": "TB",
    "LVR": "LV", "OAK": "LV", "RAI": "LV",
    "SD": "LAC", "SDG": "LAC", "SND": "LAC", "LACH": "LAC",
    "STL": "LA", "LAR": "LA", "RAM": "LA", "LARM": "LA",
    "WSH": "WAS", "WFT": "WAS",
    "NYG": "NYG", "NYJ": "NYJ",
}

# Franchise moves: historical code -> current code.
RELOCATIONS = {"OAK": "LV", "SD": "LAC", "STL": "LA"}

VALID_CODES = frozenset(_TEAMS)


class UnknownTeamError(ValueError):
    """Raised when a string cannot be resolved to exactly one team."""


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)      # drops dots in "N.E."
    return re.sub(r"\s+", " ", text).strip()


def _build_index() -> dict[str, str]:
    index: dict[str, str] = {}

    def add(key: str, code: str) -> None:
        key = _normalize(key)
        if key and index.get(key, code) == code:
            index[key] = code

    for code, (cities, nicks) in _TEAMS.items():
        add(code, code)
        for city in cities:
            add(city, code)
            for nick in nicks:
                add(f"{city} {nick}", code)
        for nick in nicks:
            add(nick, code)

    for alias, code in _ABBREV_ALIASES.items():
        add(alias, code)

    return index


_INDEX = _build_index()

# Nickname-only lookups, used as a last resort for strings that carry extra
# words ("at New England Patriots", "Patriots (-3)").
_NICK_INDEX = {_normalize(n): c for c, (_, nicks) in _TEAMS.items() for n in nicks}
_CITY_INDEX = {_normalize(c): code for code, (cities, _) in _TEAMS.items() for c in cities}


def canonical(code: str) -> str:
    """Map a historical franchise code to the team's current code."""
    code = code.strip().upper()
    return RELOCATIONS.get(code, code)


def resolve(text: str, *, default: str | None = None) -> str:
    """Resolve free text to an nflverse team code.

    Tries an exact match on the normalized string first, then looks for a
    nickname or city name appearing anywhere in it. Raises UnknownTeamError if
    nothing matches or if the text is ambiguous, unless `default` is given.
    """
    if text is None:
        if default is not None:
            return default
        raise UnknownTeamError("cannot resolve team from None")

    key = _normalize(str(text))
    if not key:
        if default is not None:
            return default
        raise UnknownTeamError(f"cannot resolve team from {text!r}")

    if key in _INDEX:
        return _INDEX[key]

    # Strip common decorations: "at ", "@ ", "vs ", trailing lines/records.
    stripped = re.sub(r"^(at|vs|v|@)\s+", "", key)
    stripped = re.sub(r"\s*\(?[-+]?\d+(\.\d+)?\)?$", "", stripped).strip()
    if stripped in _INDEX:
        return _INDEX[stripped]

    words = stripped.split()
    # Longest multi-word city match first ("new york giants" before "new york").
    for size in range(min(3, len(words)), 0, -1):
        for start in range(len(words) - size + 1):
            phrase = " ".join(words[start : start + size])
            if phrase in _INDEX:
                return _INDEX[phrase]

    hits = {code for nick, code in _NICK_INDEX.items() if nick in stripped}
    hits |= {code for city, code in _CITY_INDEX.items() if city in stripped}
    if len(hits) == 1:
        return hits.pop()

    if default is not None:
        return default
    if len(hits) > 1:
        raise UnknownTeamError(f"{text!r} is ambiguous between {sorted(hits)}")
    raise UnknownTeamError(f"could not resolve {text!r} to an NFL team")
