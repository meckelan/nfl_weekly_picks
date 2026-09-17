# NFL Weekly Picks

## What this is

A season-long ATS pick'em pool run on poolhost.com: every player picks a side
against the spread in every game, every week. Best record over the season wins.
Picks are made **Thursday afternoon**, all at once, before the first kickoff.

## The core insight — don't lose it

Do not build this as "a model that predicts games." The closing spread is
essentially unbiased (measured: +0.06 points of mean error, 48.96% home cover
rate over 6,983 games) and a margin model realistically gains a point or two at
most.

The edge is that **the pool's posted lines are stale**. They are set once and
left; the market keeps moving. Every point of gap is a bet at a number the
market no longer believes, and that is worth far more than forecasting:

    0.5 pts -> 52.3%    2 pts -> 57.3%    3 pts -> 60.1%    7 pts -> 72.3%

`calibration.py` measures this from the empirical distribution of
`margin - closing_spread`, which keeps the key numbers (3, 7, 10) intact.

A margin model is still worth building, but only for the games where the pool
and the market agree — there is no edge in those by construction.

## Conventions

Matching nflverse, everywhere in this codebase:

- `spread_line > 0` means the **home** team is favored by that many points.
- `margin = home_score - away_score` (the `result` column).
- Home covers when `margin > spread_line`, so a **higher** number is worse for
  the home side.
- Therefore `pool_spread > market_spread` -> the pool overprices the home team
  -> **take the away side**.

`tests/test_schedule.py` asserts this against the real data file. If nflverse
flips the convention upstream, those tests fail rather than every pick
inverting silently.

`PoolLine` stores *who is favored and by how much*, not a home-team spread,
because pool sheets don't reliably mark the home team. Orientation happens at
join time against the schedule.

## Data

Everything comes from one public nflverse release asset, no key required:

    https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv

~2 MB, 1999-present, carries the schedule, kickoff times, final scores, the
consensus spread, totals, moneylines and rest days. `scripts/fetch_data.py`
refreshes it. It is gitignored — regenerable in seconds.

Weekly team stats (EPA) live at the `stats_team` release under
`stats_team_week_{year}.csv` if/when a margin model needs them. The sibling
project `meckelan/NFL-Survivor-Pool` already has EPA, Elo, QB-Elo and rest
providers worth porting rather than rewriting. Note it has no shared database:
its Supabase script was a one-off that nothing reads from.

## Environment notes

`poolhost.com` is blocked by the egress proxy in Claude Code web sessions, so
the scraper cannot be exercised there. Develop it against saved HTML
(`--html`), and run `--live` locally or in Actions.

## Status

Working end to end, 55 tests passing. Outstanding: the scraper has never met
the live site; no margin model yet for the lines-agree games.
