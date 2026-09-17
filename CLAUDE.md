# NFL Weekly Picks

## What this is

A season-long ATS pick'em pool run on poolhost.com: every player picks a side
against the spread in every game, every week. Picks are made **Thursday
afternoon**, all at once, before the first kickoff.

## The objective is accuracy, not winning outright

There is **no money and no prize** — it is bragging rights among extended
family. The stated goal is "finish above 50% for the season".

That matters, because it rules out a whole class of strategy. Optimising the
chance of finishing *first* favours being decorrelated from the field (see the
simulation below, kept for reference). Optimising your *hit rate* favours
simply being right as often as possible. They give different picks. **Optimise
accuracy.**

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

**Reality check from the first real sheet (2026 week 2): 14 of 16 pool lines
matched the market exactly**, total edge 1.5 points. PoolHost pulls a live
market feed, so the gap is movement since posting, not a hand-set number.

## Do not build a margin model — it was tried and it does not work

`scripts/research_market_efficiency.py` reproduces this. Walk-forward on Elo +
rolling EPA/play + rest + divisional, modelling the residual (margin − spread),
training only on prior seasons:

    4,135 out-of-sample picks (2006-2025) -> 2,077-2,058, 50.23%, z = +0.30

Elo correlates 0.84 with the market spread and EPA/play 0.78 — they re-derive
the number rather than adding to it. A 13-rule screen of structural biases
produced two survivors at |z| > 2 where chance predicts 0.7, and both say
"take the underdog", which the policy already does.

If you are about to add a model, run that script first.

## What actually beats 50%

A 39-factor screen (`scripts/research_factors.py`), every factor built as-of,
screened on 1999-2012 and confirmed on a held-out 2013-2025:

    every dog              51.11%   [99-12 51.19% | 13-25 51.03%]
    road dogs              51.67%   [99-12 51.79% | 13-25 51.54%]
    dogs, weeks 1-4        53.05%   [99-12 52.74% | 13-25 53.36%]
    road dogs, weeks 1-4   53.70%   [99-12 53.38% | 13-25 54.02%]

Era consistency is the evidence that matters here, not the z-score — screening
39 factors at z>2 yields about one false positive by chance. These four read
the same in two independent 13-year halves, and they have a mechanism: the
public likes favorites and home teams, books shade those lines, and the
shading comes out of the favorite's side.

Nothing else survived: turnover-luck regression, blowout overreaction, ATS
streaks, bye weeks, weather, totals, EPA-vs-record divergence, backup QBs.

Blended over a 272-pick season the rule is worth about **52%**, which is a
~73% chance of finishing above .500 versus ~48% for coin-flipping. The
season-to-season swing is ~8 games (1 SD), so this tilts the odds rather than
deciding anything.

## Reference only: differentiation (wrong objective here)

Best-record-wins pays the MAXIMUM, not the mean. Picking by the same process
as the field earns a fair share of the pot and nothing more. Simulated, 20
entrants, field at 85% favorites, nobody with an edge:

    always the underdog      34.3%   (6.9x fair share)
    coin flip                20.5%   (4.1x)
    pick like everyone else   4.9%   (1.0x)
    always the favorite       0.1%

This is real, but it optimises P(finish first), which is **not** this pool's
objective. Kept because the analysis is sound and `crowd.py` still reports
crowd share, and because it would become the right strategy if the pool ever
had a prize. Do not let it drive picks.

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

## The policy

    line edge >= 0.5 pts  ->  take that side (52.3% at 0.5, 60.1% at 3.0)
    otherwise             ->  take the underdog, at the best-matching rate:
                              early-season road dog 53.7% / early dog 53.0%
                              / road dog 51.7% / any dog 51.1%

## Status

Working end to end, 86 tests passing. Outstanding: the login flow has never run
against the live site (the sheet parser has, and is verified); grading captured
sheets against closing lines once a few weeks accumulate.
