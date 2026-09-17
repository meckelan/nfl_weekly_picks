"""Turning a pool sheet into PoolLine records.

Written markup-agnostically on purpose. Pool hosting sites rewrite their
templates without warning, and a parser pinned to `table.picks > tr > td:nth(3)`
breaks silently the first time they do — on a Thursday, with picks due. So
instead of matching a fixed structure, this scans every candidate row for the
two things a line always contains: two resolvable team names and a number.

Three layouts are recognized, in order of confidence:

  1. one cell holding both a team and its own signed number  ("New England -3.5")
  2. a row with two teams and one signed number adjacent to one of them
  3. two consecutive single-team rows with equal-and-opposite numbers

`parse_text` handles the same shapes from plain text, and is the fallback that
always works: copy the sheet out of the browser and paste it in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..teams import UnknownTeamError, resolve
from .models import PoolLine

# -3, +3.5, 3½, -7 1/2 ... and the pick'em spellings.
_NUMBER = re.compile(r"(?<![\w.])([+-]?\d{1,2}(?:\.\d|\s*[½¼¾]|\s*1/2)?)(?![\w.])")
_PICKEM = re.compile(r"\b(pk|pick|pick'?em|pickem|even)\b", re.IGNORECASE)
_HALF = {"½": 0.5, "¼": 0.25, "¾": 0.75}


class ParseError(ValueError):
    """Raised when a sheet yields no usable lines."""


@dataclass
class _Cell:
    text: str
    team: str | None
    number: float | None


def _to_float(token: str) -> float:
    token = token.strip().replace(" ", "")
    for glyph, value in _HALF.items():
        if token.endswith(glyph):
            base = float(token[: -len(glyph)] or "0")
            return base - value if base < 0 else base + value
    if token.endswith("1/2"):
        base = float(token[:-3] or "0")
        return base - 0.5 if base < 0 else base + 0.5
    return float(token)


def _numbers(text: str) -> list[float]:
    return [_to_float(m.group(1)) for m in _NUMBER.finditer(text)]


def _classify(text: str) -> _Cell:
    """Read one cell: which team it names, and which number it carries."""
    text = " ".join(text.split())
    if not text:
        return _Cell(text, None, None)

    # A record like "(3-1)" or a date must not be read as a spread. Strip the
    # common decorations before looking for a number.
    cleaned = re.sub(r"\(\s*\d+\s*-\s*\d+(\s*-\s*\d+)?\s*\)", " ", text)
    cleaned = re.sub(r"\b\d{1,2}[:/]\d{2}\s*(am|pm|et|ct|mt|pt)?\b", " ", cleaned, flags=re.I)

    nums = _numbers(cleaned)
    number = nums[0] if len(nums) == 1 else None
    if number is None and _PICKEM.search(cleaned):
        number = 0.0

    try:
        team = resolve(text)
    except UnknownTeamError:
        team = None

    return _Cell(text, team, number)


def _line_from_cells(cells: list[_Cell], raw: str) -> PoolLine | None:
    """Layouts 1 and 2: everything needed is inside a single row."""
    teams = [c for c in cells if c.team]
    # Dedupe while keeping order — a row may name the same team twice
    # (logo alt text plus the name, say).
    seen: set[str] = set()
    unique: list[_Cell] = []
    for cell in teams:
        if cell.team not in seen:
            seen.add(cell.team)
            unique.append(cell)
    if len(unique) != 2:
        return None

    # Layout 1: a team cell that carries its own number.
    owned = [c for c in unique if c.number is not None]
    if len(owned) == 1:
        holder, other = owned[0], next(c for c in unique if c is not owned[0])
        return _orient(holder.team, other.team, holder.number, raw)
    if len(owned) == 2:
        a, b = owned
        if a.number * b.number < 0:              # equal and opposite: trust the negative
            neg, pos = (a, b) if a.number < 0 else (b, a)
            return _orient(neg.team, pos.team, neg.number, raw)
        return None

    # Layout 2: a standalone number cell adjacent to one of the teams.
    numeric = [i for i, c in enumerate(cells) if c.team is None and c.number is not None]
    if len(numeric) != 1:
        return None
    idx = numeric[0]
    positions = {id(c): i for i, c in enumerate(cells)}
    first, second = unique
    d_first = abs(positions[id(first)] - idx)
    d_second = abs(positions[id(second)] - idx)

    if d_first == d_second:
        # "Green Bay  -6.5  Chicago" — the number belongs to the team it
        # follows, which is how every sheet in this shape reads. _orient
        # still sorts out favorite vs underdog from its sign.
        before = [c for c in unique if positions[id(c)] < idx]
        if len(before) != 1:
            return None
        nearer = before[0]
        farther = next(c for c in unique if c is not nearer)
    else:
        nearer, farther = (first, second) if d_first < d_second else (second, first)

    return _orient(nearer.team, farther.team, cells[idx].number, raw)


def _orient(team: str, other: str, number: float, raw: str) -> PoolLine | None:
    """Build a line from 'this number belongs to this team'."""
    if number == 0:
        return PoolLine(favorite=team, underdog=other, points=0.0, raw=raw)
    if number < 0:
        return PoolLine(favorite=team, underdog=other, points=abs(number), raw=raw)
    return PoolLine(favorite=other, underdog=team, points=abs(number), raw=raw)


def _rows_from_html(html: str) -> list[list[str]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()

    rows: list[list[str]] = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)

    if not rows:  # not a table-based sheet — fall back to visible text lines
        rows = [[line] for line in soup.get_text("\n").splitlines() if line.strip()]
    return rows


def _parse_rows(rows: list[list[str]]) -> list[PoolLine]:
    lines: list[PoolLine] = []
    used: set[frozenset[str]] = set()
    pending: tuple[_Cell, str] | None = None

    for cells_text in rows:
        raw = " | ".join(cells_text)
        cells = [_classify(t) for t in cells_text]

        line = _line_from_cells(cells, raw)
        if line is None:
            # Layout 3: one team and one number on this row; pair it with the
            # previous such row if the numbers are equal and opposite.
            # The team and its number may sit in one cell ("Miami +4.5") or in
            # separate cells of the same row; treat the row as a whole.
            row_teams = {c.team for c in cells if c.team}
            row_numbers = [c.number for c in cells if c.number is not None]
            if len(row_teams) == 1 and len(row_numbers) == 1:
                current = _Cell(raw, next(iter(row_teams)), row_numbers[0])
                if pending is not None:
                    prev, prev_raw = pending
                    if prev.team != current.team and prev.number == -current.number:
                        neg = prev if prev.number < 0 else current
                        pos = current if neg is prev else prev
                        line = _orient(neg.team, pos.team, neg.number, f"{prev_raw} || {raw}")
                        pending = None
                    else:
                        pending = (current, raw)
                else:
                    pending = (current, raw)
            else:
                pending = None

        if line is not None and line.teams not in used:
            used.add(line.teams)
            lines.append(line)
            pending = None

    return lines


def _strip_decorations(text: str) -> str:
    """Remove win-loss records and kickoff times, which look like numbers."""
    text = re.sub(r"\(\s*\d+\s*-\s*\d+(\s*-\s*\d+)?\s*\)", " ", text)
    text = re.sub(r"\b\d{1,2}[:/]\d{2}\s*(am|pm|et|ct|mt|pt)?\b", " ", text, flags=re.I)
    return " ".join(text.split())


def _text_row(line: str) -> list[str]:
    """Split one pasted line into cells.

    Tab- or column-separated text (a spreadsheet paste) already has cells.
    Otherwise split around the spread itself, which is the one token whose
    position is unambiguous — splitting on spaces would tear "New England"
    and "Green Bay" in half.
    """
    parts = [p.strip() for p in re.split(r"\t|\s{2,}", line.strip()) if p.strip()]
    if len(parts) >= 2:
        return parts

    cleaned = _strip_decorations(line)
    match = _NUMBER.search(cleaned) or _PICKEM.search(cleaned)
    if match is None:
        return [cleaned]
    return [cleaned[: match.start()], match.group(), cleaned[match.end() :]]


def parse_sheet(html: str) -> list[PoolLine]:
    """Extract every line from a pool sheet's HTML."""
    lines = _parse_rows(_rows_from_html(html))
    if not lines:
        raise ParseError(
            "no lines found in the page. Save it with --save-html and check "
            "whether the sheet rendered (a login wall returns a valid page "
            "with no lines in it)."
        )
    return lines


def parse_text(text: str) -> list[PoolLine]:
    """Extract lines from pasted text: one game per line, any of

        NE -3.5 BUF
        New England -3.5 at Buffalo
        Buffalo +3.5 New England
        KC PK LV
    """
    lines = _parse_rows([_text_row(line) for line in text.splitlines() if line.strip()])
    if not lines:
        raise ParseError("no lines found in the pasted text")
    return lines
