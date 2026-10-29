"""Is anyone in the pool actually beating chance?

    python3 scripts/analyze_field.py

Reads the season standings — every player's weekly win counts — and tests the
field against luck. Pick-level data is not needed for this: a player's record
is the sufficient statistic for their accuracy, so the standings carry all the
information the question requires.

Three tests, weakest to strongest:

  1. **Each player against 50%.** Honest but weak, and it ignores that there
     are seventeen of them.
  2. **The leader against the best of seventeen coin-flippers.** Someone has
     to finish first; the right benchmark for the top record is the maximum of
     the field, not the mean.
  3. **The spread of the whole field.** The sharpest test available here. If
     some players are genuinely better than others, season records must spread
     out *more* than binomial noise allows. If the observed spread matches
     binomial, there is no skill to find anywhere in the pool — and this uses
     all seventeen players rather than just the one in front.

Plus a persistence check: do the first half's leaders lead in the second half?
Skill persists; luck does not.

Players are labelled by standings rank. No name is ever read or printed —
this output lands in a log on a public repository.
"""

import _bootstrap  # noqa: F401
import re
import sys
from urllib.parse import urljoin

import numpy as np

STANDINGS_PATH = "/profootball/standings"
_RECORD = re.compile(r"^(\d+)\s*-\s*(\d+)(?:\s*-\s*(\d+))?$")


def parse_standings(html: str) -> list[dict]:
    """One row per player: weekly win counts and the season record.

    Names are skipped on purpose — the column is located so it can be ignored.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 5:
            continue
        header = [" ".join(c.get_text(" ", strip=True).split())
                  for c in rows[0].find_all(["th", "td"])]
        week_columns = [i for i, h in enumerate(header) if re.fullmatch(r"Week \d+", h)]
        record_column = next(
            (i for i, h in enumerate(header) if "W-L" in h.upper().replace("[", "")), None
        )
        if not week_columns or record_column is None:
            continue

        players = []
        for rank, row in enumerate(rows[1:], start=1):
            cells = row.find_all(["td", "th"])
            if len(cells) <= record_column:
                continue
            weekly = []
            for i in week_columns:
                text = cells[i].get_text(strip=True)
                weekly.append(int(text) if text.isdigit() else None)
            found = _RECORD.match(cells[record_column].get_text(strip=True))
            if not found:
                continue
            wins, losses, ties = (int(found.group(1)), int(found.group(2)),
                                  int(found.group(3) or 0))
            players.append({
                "label": f"Player {rank:02d}",
                "weekly": weekly,
                "wins": wins, "losses": losses, "ties": ties,
            })
        if players:
            return players
    raise SystemExit("could not find the standings table")


def report(players: list[dict]) -> None:
    from math import erf, sqrt

    rng = np.random.default_rng(17)
    n = len(players)
    decided = [p["wins"] + p["losses"] for p in players]
    picks = max(decided)

    print(f"{n} players, {picks} decided picks at the top of the table.\n")
    print("=== 1. Each player against a coin flip ===\n")
    print(f"  {'player':<11} {'record':>12} {'win%':>7} {'z':>6} {'p':>7}")
    print(f"  {'-' * 48}")
    for p in players:
        d = p["wins"] + p["losses"]
        rate = p["wins"] / d
        z = (rate - 0.5) / sqrt(0.25 / d)
        two_sided = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
        flag = "  *" if two_sided < 0.05 else ""
        print(f"  {p['label']:<11} {p['wins']:>4}-{p['losses']:<3}{('-' + str(p['ties'])) if p['ties'] else '   ':<4} "
              f"{rate * 100:>6.1f}% {z:>+6.2f} {two_sided:>7.3f}{flag}")
    print(f"\n  At p<0.05 two-sided, chance alone flags about {n * 0.05:.1f} of {n} players.")

    print("\n\n=== 2. The leader against the best of the field ===\n")
    leader = max(p["wins"] for p in players)
    draws = rng.binomial(picks, 0.5, size=(200_000, n))
    best = draws.max(axis=1)
    beat = (best >= leader).mean()
    print(f"  observed leader                : {leader}-{picks - leader} "
          f"({leader / picks * 100:.1f}%)")
    print(f"  best of {n} coin-flippers, mean : {best.mean():.1f}-{picks - best.mean():.1f} "
          f"({best.mean() / picks * 100:.1f}%)")
    print(f"  P(luck alone reaches {leader}+)      : {beat * 100:.1f}%")
    print(f"  VERDICT: {'the leader is beyond luck' if beat < 0.05 else 'the leader is what luck looks like'}")

    print("\n\n=== 3. The spread of the whole field (the sharpest test) ===\n")
    wins = np.array([p["wins"] for p in players], dtype=float)
    observed_sd = wins.std(ddof=1)
    expected_sd = np.sqrt(picks * 0.25)
    sim_sds = draws.std(axis=1, ddof=1)
    p_spread = (sim_sds >= observed_sd).mean()
    print(f"  observed spread of win totals  : {observed_sd:.2f}")
    print(f"  binomial expectation           : {expected_sd:.2f}")
    print(f"  P(luck produces a spread this wide or wider): {p_spread * 100:.1f}%")
    print("""
  If some players were genuinely better, season records would have to spread
  out MORE than coin flips allow. A spread at or below the binomial figure
  means there is no skill anywhere in the pool to find.""")
    print(f"  VERDICT: {'the field is more spread out than luck allows' if p_spread < 0.05 else 'the spread is indistinguishable from luck'}")

    print("\n\n=== 4. Does performance persist? ===\n")
    weeks = len(players[0]["weekly"])
    half = weeks // 2
    first, second = [], []
    for p in players:
        a = [w for w in p["weekly"][:half] if w is not None]
        b = [w for w in p["weekly"][half:] if w is not None]
        if a and b:
            first.append(sum(a)); second.append(sum(b))
    if len(first) > 3:
        r = float(np.corrcoef(first, second)[0, 1])
        print(f"  correlation between first-half and second-half wins: r = {r:+.3f}")
        print(f"  (n = {len(first)} players)")
        print("""
  Skill persists across halves of a season; luck does not. A correlation near
  zero means this week's leaders are not last week's, which is the signature
  of a pool of coin-flippers.""")
        print(f"  VERDICT: {'performance persists' if r > 0.5 else 'no persistence — leaders do not stay leaders'}")


def main() -> None:
    from weekly_picks.pool.client import PoolHostClient
    from weekly_picks.pool.poolhost import SheetNotFound, navigate_to_sheet

    client = PoolHostClient()
    try:
        client.login()
    except Exception as exc:                                       # noqa: BLE001
        print(f"login failed: {exc}", file=sys.stderr)
    try:
        navigate_to_sheet(client)
    except SheetNotFound:
        print("could not establish pool context", file=sys.stderr)
        raise SystemExit(1)

    html = client.fetch(urljoin(client.url, STANDINGS_PATH), archive=False)
    report(parse_standings(html))


if __name__ == "__main__":
    main()
