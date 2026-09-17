# NFL Weekly Picks

A season-long ATS pick'em pool: every player picks a side against the spread in
every game, every week, and the best record at the end wins. This makes those
picks on Thursday afternoon, before the first kickoff.

Short version of what the data says:

1. **You cannot out-predict the closing spread.** Measured, not assumed.
2. **The pool's line sometimes lags the market.** That gap is a real edge, but
   it is thin — 2 of 16 games in the first week checked.
3. **Underdogs cover 51.1% of decided games**, and early-season road dogs
   53.7% — the only factors out of 39 screened that hold up in a held-out era.

## 1. The market is efficient

Over **6,983 graded games (1999-2026)** the closing spread is close to
perfectly calibrated:

| | |
|---|---|
| mean error (margin − spread) | **+0.06 points** |
| home teams covering | **48.96%** of decided games |
| std. deviation of the error | 13.19 points |

`scripts/research_market_efficiency.py` then tries to beat it. Elo and rolling
EPA/play ratings are built as-of each week, and used to model the *residual* —
what the market missed — with a walk-forward fit that only ever sees prior
seasons:

| | |
|---|---|
| out-of-sample picks | **4,135** (2006-2025) |
| record | 2,077-2,058 |
| hit rate | **50.23%** |
| 95% CI | [48.71%, 51.75%] |
| z vs. 50% | **+0.30** |

The reason shows up in the inputs: Elo correlates **0.84** with the market
spread, EPA/play **0.78**. They are not adding information, they are
re-deriving the number Vegas already posted.

Screening the classic structural biases does no better. Of 13 rules, two clear
|z| = 2 where chance alone predicts about 0.7 — and both just say *take the
underdog*:

| rule | n | hit% | since 2015 |
|---|---|---|---|
| weeks 1-3: take the dog | 1,251 | 53.40% | 54.22% |
| divisional: take the dog | 2,625 | 52.08% | 52.31% |
| take the dog, spread ≥ 10 | 845 | 52.19% | 50.43% |
| home underdog | 2,395 | 50.06% | 50.14% |

**So there is no margin model in this project.** That is a finding, not an
omission.

## 2. Stale pool lines — a real but thin edge

The pool posts its lines once. The market keeps moving on injuries, weather and
money. Where the two disagree, you are betting into a number the market itself
no longer believes — that is arithmetic, not forecasting.

Measured off the empirical distribution of `margin − closing_spread`, so the
NFL's key numbers (3, 7, 10) survive instead of being smoothed away by a normal
curve:

| pool line off by | win rate (decided) | vs. coin flip |
|---|---|---|
| 0.5 pts | 52.3% | +2.3 |
| 1.0 pts | 54.1% | +4.1 |
| 2.0 pts | 57.3% | +7.3 |
| 3.0 pts | **60.1%** | +10.1 |
| 7.0 pts | 72.3% | +22.3 |

In practice the gaps are small. On the first real sheet (2026 week 2),
**14 of 16 pool lines matched the market exactly** — 1.5 points of edge across
the slate. PoolHost pulls a live feed rather than hand-setting lines, so the
gap is only movement since posting.

Regenerate the table with `scripts/calibrate_edge.py`.

## 3. Underdogs cover a little more than half

A 39-factor screen (`scripts/research_factors.py`). Every factor is built
as-of, screened on **1999-2012**, then confirmed on a held-out **2013-2025**
the screen never saw:

| rule (take the underdog) | n | hit% | 1999-2012 | 2013-2025 |
|---|---|---|---|---|
| every dog | 6,793 | 51.11% | 51.19% | 51.03% |
| road dogs | 4,368 | 51.67% | 51.79% | 51.54% |
| dogs, weeks 1-4 | 1,640 | 53.05% | 52.74% | 53.36% |
| **road dogs, weeks 1-4** | 1,067 | **53.70%** | 53.38% | 54.02% |

The evidence here is the **era consistency**, not the z-score: screening 39
factors at z > 2 throws off about one false positive by chance, so a single
significant slice proves nothing. These four read the same across two
independent 13-year halves, and there is a mechanism — the public likes
favorites and home teams, books shade those lines, and the shading comes out of
the favorite's side. Early-season dogs do best, which fits: the market has the
least information in September and the public leans hardest on last year's
reputations.

**Nothing else survived.** Turnover-luck regression, blowout overreaction, ATS
streaks, bye weeks, cold, wind, totals, EPA-vs-record divergence, backup
quarterbacks — all noise.

## What it adds up to

Blended over a 272-pick season:

| strategy | blended | expected | P(finish above .500) |
|---|---|---|---|
| coin flip / take favorites | 50.00% | 136.0-136.0 | 48% |
| always take the underdog | 51.11% | 139.0-133.0 | 62% |
| **the rule below** | **51.99%** | **141.4-130.6** | **73%** |

A season swings ~8 games on luck alone (1 SD), so a 2-point edge is about a
quarter of a standard deviation. It tilts the odds. It does not decide the
season.

## The policy

```
pool line differs from the market  ->  take that side
   (52.3% at 0.5 pts, 60.1% at 3)

otherwise, take the underdog at the best-matching rate:
   early-season road dog   53.7%
   early-season dog        53.0%
   road dog                51.7%
   any dog                 51.1%
```

## Usage

```bash
pip install -r requirements.txt
python3 scripts/fetch_data.py          # nflverse schedule, results, market lines
python3 scripts/calibrate_edge.py      # rebuild the edge table (optional)

# only if you want to re-run the research that produced the findings above
python3 scripts/fetch_data.py --team-stats
python3 scripts/research_market_efficiency.py
```

Thursday, in two steps:

```bash
# 1. capture the pool's lines — whichever works
python3 scripts/pool_lines.py --live                  # scrape (needs .env)
python3 scripts/pool_lines.py --html saved_page.html  # a page saved from the browser
python3 scripts/pool_lines.py --text lines.txt        # pasted text; always works

# 2. make the picks
python3 scripts/make_picks.py --csv picks.csv
```

```
LINE EDGE — the pool's number differs from the market (2)
  game         pick    line  edge    win%
  DET @ BUF    BUF     -4.5   1.0   54.1%
  CIN @ HOU    CIN     +3.0   0.5   52.3%

FADE THE FIELD — lines agree, so take the unpopular side (14)
  game         pick    line  pool on you
  NO @ BAL     NO      +8.5          18%
  MIA @ SF     MIA    +13.5           8%
  ...
  average share of the pool on your side: 30% — lower is better here
```

For the paste route, anything readable works — `NE -3.5 BUF`,
`New England -3.5 at Buffalo Bills`, `Green Bay  -6.5  Chicago`, `KC PK LV`,
half-point glyphs, tab-separated columns out of a spreadsheet.

## Layout

```
src/weekly_picks/
  schedule.py     nflverse schedule, results and market lines
  calibration.py  what a point of line discrepancy is worth, from history
  edge.py         pool line vs market line -> a side and a win probability
  crowd.py        what share of the pool takes each side (reporting only)
  recommend.py    the policy: line edges first, underdog rule otherwise
  teams.py        free-text team names -> nflverse codes
  pool/
    client.py     login and fetch (login form discovered, not hardcoded)
    poolhost.py   PoolHost's sheet, matched to their real markup
    parse.py      generic sheet / pasted text -> lines
    models.py     PoolLine / PoolSheet
scripts/          fetch_data, calibrate_edge, pool_lines, make_picks,
                  research_market_efficiency (no model beats the spread),
                  research_factors (39-factor screen, held-out era)
tests/            86 tests, including guards on the upstream sign convention
```

### Conventions

One spread convention everywhere, matching nflverse:

```
spread_line > 0        the HOME team is favored by that many points
margin = home - away   (the `result` column)
home covers when       margin > spread_line
```

A *higher* number is worse for the home side, so `pool > market` means the pool
overprices the home team and the away side is the play. `tests/test_schedule.py`
asserts this against the real file, so if nflverse ever flips it the tests fail
instead of every pick silently inverting.

## Status

Working end to end, 86 tests passing.

- **The sheet parser is verified** against a real PoolHost sheet — all 16 games,
  correctly oriented. It reads each team from its logo filename
  (`/images/teamlogos/BUF.png`) rather than display text, because PoolHost
  writes the New York and Los Angeles teams as `New York (A)` / `New York (N)`
  and uses `AZ`, `JAC`, `LAR` where nflverse uses `ARI`, `JAX`, `LA`.
- **The login flow is not verified.** `poolhost.com` is blocked from the
  environment this was built in, so `client.py` has never authenticated. The
  form is discovered at runtime rather than hardcoded, but it needs one real
  run. `--html` and `--text` work regardless.
- **The edges are small and were found by screening.** ~+2 points of win rate.
  The defence is era-consistency and a plausible mechanism, not a big z-score.
  Treat a losing month as noise, not as the rule breaking.
- **`crowd.py` is reporting only.** It estimates what share of the pool takes
  each side. That would matter if the pool had a prize and you were optimising
  for first place rather than for accuracy; it does not drive picks.
- **The market line is nflverse's consensus**, not a live intraday quote. If
  both sources refresh on similar schedules, some of that 14/16 agreement is
  them agreeing with each other rather than the pool being sharp.
