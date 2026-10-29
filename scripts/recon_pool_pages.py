"""Report the structure of the pool's results pages, without their contents.

    python3 scripts/recon_pool_pages.py

The standings and all-picks pages are what we need to study the field: who is
actually ahead, and what they pick. But they cannot be reached from a Claude
Code container, so the parser has to be written from a description produced
inside Actions — the same way the pick sheet was.

This prints **shape, never content**. Those pages carry the real names of
family members and every pick they have made, and this output lands in a log
on a public repository. So each cell is reported as a classification —
`num:12`, `team:KC`, `rec:5-2`, `text(len=14)` — and never as its text. That
is enough to write a parser and not enough to identify anyone.
"""

import _bootstrap  # noqa: F401
import re
import sys
from urllib.parse import urljoin

from weekly_picks.teams import UnknownTeamError, resolve

PAGES = (
    "/profootball/standings",
    "/profootball/allpicks",
    "/profootball/pickdistribution",
)

_RECORD = re.compile(r"^\d+\s*-\s*\d+(\s*-\s*\d+)?$")
_NUMBER = re.compile(r"^[+-]?\d+(\.\d+)?%?$")
_LOGO = re.compile(r"/teamlogos/([A-Za-z0-9]+)\.", re.IGNORECASE)


def classify(cell) -> str:
    """Describe one table cell without revealing what it says."""
    image = cell.find("img", src=True)
    if image:
        found = _LOGO.search(image["src"])
        if found:
            return f"logo:{found.group(1)}"
        return "img"

    text = " ".join(cell.get_text(" ", strip=True).split())
    if not text:
        return "-"
    if _NUMBER.match(text):
        return f"num:{text}"
    if _RECORD.match(text):
        return f"rec:{text}"
    try:
        return f"team:{resolve(text)}"
    except UnknownTeamError:
        return f"text(len={len(text)})"


def describe_tables(html: str, limit: int = 4) -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else "(no title)"
    tables = soup.find_all("table")
    print(f"    title       : {title}")
    print(f"    bytes       : {len(html):,}")
    print(f"    tables      : {len(tables)}")

    for index, table in enumerate(tables[:limit]):
        rows = table.find_all("tr")
        if not rows:
            continue
        print(f"    table[{index}]: {len(rows)} rows")
        header = rows[0].find_all(["th", "td"])
        # Header labels are column names, not anybody's data.
        print(f"      header ({len(header)} cols): "
              f"{[' '.join(c.get_text(' ', strip=True).split())[:18] for c in header]}")
        for row in rows[1:4]:
            cells = row.find_all(["td", "th"])
            print(f"      row: {[classify(c) for c in cells]}")

    if not tables:
        # Some PoolHost pages are div-based, as the pick sheet is.
        for selector in ("div.game-box", "div.team", "[class*=standing]",
                         "[class*=player]", "[class*=pick]", "[class*=row]"):
            found = soup.select(selector)
            if found:
                print(f"    {selector}: {len(found)}")


def describe_controls(html: str) -> None:
    """How the page lets you ask for a different week.

    allpicks defaults to the current week; the field's past picks are the
    point, so the selector has to be found. Values are printed because a week
    number or a form field name identifies nobody.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    for form in soup.find_all("form")[:3]:
        fields = [
            f"{f.get('name')}={f.get('type') or f.name}"
            for f in form.find_all(("input", "select")) if f.get("name")
        ]
        print(f"      form action={form.get('action')!r} method={form.get('method')!r}")
        print(f"        fields: {fields[:12]}")

    for select in soup.find_all("select")[:3]:
        options = [(o.get("value"), " ".join(o.get_text(" ", strip=True).split())[:14])
                   for o in select.find_all("option")[:12]]
        print(f"      select name={select.get('name')!r} id={select.get('id')!r}")
        print(f"        options: {options}")

    weekish = sorted({
        a["href"] for a in soup.find_all("a", href=True)
        if re.search(r"week|wk", a["href"], re.IGNORECASE)
    })[:10]
    if weekish:
        print(f"      week-ish links: {weekish}")

    scripts = " ".join(t.get_text() for t in BeautifulSoup(html, "lxml").find_all("script"))
    calls = sorted(set(re.findall(r"[A-Za-z_$][\w$.]*\((?=[^)]*[Ww]eek)[^)]{0,40}\)", scripts)))[:8]
    if calls:
        print(f"      week-ish script calls: {calls}")


def main() -> None:
    from weekly_picks.pool.client import PoolHostClient
    from weekly_picks.pool.poolhost import SheetNotFound, navigate_to_sheet

    client = PoolHostClient()
    try:
        client.login()
    except Exception as exc:                                       # noqa: BLE001
        print(f"login failed: {exc}", file=sys.stderr)

    # Reaching the sheet is what gives the session its pool context; every
    # other pool page needs that too.
    try:
        lines, trail = navigate_to_sheet(client)
        print(f"pool context established ({len(lines)} lines on the sheet)\n")
    except SheetNotFound as exc:
        print("could not establish pool context:", file=sys.stderr)
        for step in exc.trail:
            print(f"  {step}", file=sys.stderr)
        raise SystemExit(1)

    base = urljoin(client.url, "/")
    for path in PAGES:
        url = urljoin(base, path)
        print(f"  {path}")
        try:
            html = client.fetch(url, archive=False)
        except Exception as exc:                                   # noqa: BLE001
            print(f"    FAILED: {exc}\n")
            continue
        landed = client.last_url
        if landed and landed != url:
            print(f"    redirected  : -> {landed}")
        describe_tables(html)
        if path.endswith(("allpicks", "pickdistribution")):
            print("    controls:")
            describe_controls(html)
        print()


if __name__ == "__main__":
    main()
