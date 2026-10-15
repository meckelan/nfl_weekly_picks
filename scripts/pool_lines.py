"""Capture the pool's posted lines for a week.

Three ways in, in order of how much can go wrong:

    # scrape the live site (needs POOLHOST_* in the environment)
    python3 scripts/pool_lines.py --week 3 --live

    # re-parse a page you saved from the browser
    python3 scripts/pool_lines.py --week 3 --html saved.html

    # paste the sheet (always works, no scraping involved)
    python3 scripts/pool_lines.py --week 3 --text lines.txt

Writes data/pool/<season>_wk<week>.json, which is what the picks run reads.
Re-running overwrites that week, so a bad scrape is never permanent.
"""

import _bootstrap  # noqa: F401
import argparse
import json
import sys
from pathlib import Path

from weekly_picks.pool import ParseError, PoolSheet, parse_sheet, parse_text
from weekly_picks.schedule import current_week, load_games

POOL_DIR = Path(__file__).resolve().parents[1] / "data" / "pool"


def _fingerprint(sheet: PoolSheet) -> set[tuple[str, str, float]]:
    """The lines themselves, ignoring when and where they were captured."""
    return {(line.favorite, line.underdog, line.points) for line in sheet.lines}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--live", action="store_true", help="scrape poolhost")
    source.add_argument("--html", type=Path, help="parse a saved HTML file")
    source.add_argument("--text", type=Path, help="parse a pasted text file ('-' for stdin)")
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--url", default=None, help="override POOLHOST_URL")
    args = parser.parse_args()

    games = load_games()
    season = args.season or int(games[games["kickoff"].notna()]["season"].max())
    week = args.week or current_week(games, season)

    if args.live:
        from weekly_picks.pool.client import PoolHostClient
        from weekly_picks.pool.poolhost import SheetNotFound, describe_page, navigate_to_sheet

        client = PoolHostClient(url=args.url)
        login_note = "reported success"
        try:
            client.login()
        except Exception as exc:                                  # noqa: BLE001
            login_note = f"FAILED — {exc}"
            print(f"login failed ({exc}); trying the page unauthenticated", file=sys.stderr)

        try:
            lines, trail = navigate_to_sheet(client)
            for step in trail:
                print(f"  tried {step}", file=sys.stderr)
        except SheetNotFound as exc:
            # Nearly always "we were handed the wrong page" rather than a
            # parsing bug, so say which page. login() can only check that no
            # password box came back, which a site whose login lives on its
            # own page will pass while still being logged out.
            print(f"\n{exc}\n", file=sys.stderr)
            print(f"  login         : {login_note}", file=sys.stderr)
            for step in exc.trail:
                print(f"  tried         : {step}", file=sys.stderr)
            print(describe_page(exc.last_html, exc.last_url), file=sys.stderr)
            print(
                "\nIf 'password input' says YES, or the fetched url is not the picks\n"
                "page, the session is not authenticated — check POOLHOST_USERNAME and\n"
                "POOLHOST_PASSWORD, and set POOLHOST_LOGIN_URL if the login form lives\n"
                "on a different page. If div.game-box is 0 on a page that looks right,\n"
                "the sheet markup changed and the parser needs updating.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        origin = client.last_url or client.url
    elif args.html:
        lines, origin = parse_sheet(args.html.read_text(encoding="utf-8")), str(args.html)
    else:
        raw = sys.stdin.read() if str(args.text) == "-" else args.text.read_text(encoding="utf-8")
        lines, origin = parse_text(raw), str(args.text)

    sheet = PoolSheet(season=season, week=week, lines=lines, source=origin)

    POOL_DIR.mkdir(parents=True, exist_ok=True)
    out = POOL_DIR / f"{season}_wk{week:02d}.json"

    # Re-running must not rewrite an unchanged sheet: only captured_at would
    # differ, which commits a line of noise every week and makes the timestamp
    # meaningless. Left alone, captured_at reads as "when these lines were
    # first seen", which is what matters for judging how stale they are. A
    # genuine mid-week line move still rewrites the file.
    unchanged = False
    if out.exists():
        previous = PoolSheet.from_dict(json.loads(out.read_text()))
        unchanged = _fingerprint(previous) == _fingerprint(sheet)

    if unchanged:
        print(f"{len(sheet)} lines for {season} week {week} unchanged since "
              f"{previous.captured_at} — leaving {out} alone\n")
    else:
        out.write_text(json.dumps(sheet.to_dict(), indent=2) + "\n")
        print(f"{len(sheet)} lines captured for {season} week {week} -> {out}\n")
    for line in sheet.lines:
        points = "PK" if line.points == 0 else f"-{line.points:g}"
        print(f"  {line.favorite:>3} {points:>5}  over  {line.underdog}")

    expected = len(games[(games.season == season) & (games.week == week)])
    if expected and len(sheet) != expected:
        print(f"\nWARNING: schedule has {expected} games this week, sheet has {len(sheet)}.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
