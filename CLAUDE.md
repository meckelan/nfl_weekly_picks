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

**Reality check from the first real sheet (2026 week 2): 14 of 16 pool lines
matched the market exactly**, total edge 1.5 points. PoolHost is pulling a live
market feed, so the gap is movement since posting, not a hand-set number. The
stale-line edge is real but thin, and one Thursday is not enough to size it.
Because captured sheets are committed and nflverse's `spread_line` becomes the
closing line after kickoff, pool-vs-closing can be graded after a few weeks
with no extra collection. Do that before concluding anything.

Practical consequence: with most games carrying no discrepancy, the margin
model is more important than it first appeared, not less.

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

## PoolHost specifics

Learned from a real sheet, `tests/fixtures/poolhost_sheet.html` is a trimmed,
synthetic copy of the markup (the repo is public — do not commit a real sheet,
it carries the username and pool name).

- Each game is `div.game-box`; the two sides are `div.team.away-team` and
  `div.team.home-team`.
- **Read the team from its logo filename** (`/images/teamlogos/BUF.png`), not
  the display text: PoolHost writes the New York and Los Angeles teams as
  `New York (A)` / `New York (N)` (A = AFC, N = NFC).
- Their codes are not all nflverse codes: `AZ` -> `ARI`, `JAC` -> `JAX`,
  `LAR` -> `LA`. `teams.py` handles these.
- `div.team-spread` sits inside one team's block and is quoted from that team's
  point of view (negative = laying). On every game seen so far it is on the
  home side, but the parser reads whichever side carries it rather than
  assuming.
- `WeekGames[N].GameId` and the `onTeamSelect(this, <teamId>)` handler are
  captured — enough to *submit* picks programmatically later, which is not
  built and should not be without asking first.

## Status

Working end to end, 64 tests passing. Outstanding: the login flow has never run
against the live site (the sheet parser has, and is verified); no margin model
yet for the lines-agree games, which is most of them.
