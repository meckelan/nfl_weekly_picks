# NFL Weekly Picks

A season-long ATS pick'em pool: every player picks a side against the spread in
every game, every week, and the best record at the end wins. This makes those
picks on Thursday afternoon, before the first kickoff.

Short version of what the data says:

1. **You cannot out-predict the closing spread.** Measured, not assumed.
2. **The pool's line sometimes lags the market.** That gap is a real edge, but
   it is thin — 2 of 16 games in the first week checked.
3. **What actually wins a best-record pool is not being right, it is being
   different.** This is the big lever, and it is worth more than any
   handicapping edge you could realistically get.

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

## 3. Differentiation is the real lever

A best-record-wins pool pays the **maximum**, not the mean. Picking by the same
process as everyone else earns a fair share of the pot and nothing more.

Simulated: 20 entrants, a field that takes the favorite 85% of the time, nobody
with any real edge.

| your strategy | win rate | vs. 5% fair share |
|---|---|---|
| **always the underdog** | **34.3%** | **6.9×** |
| lean underdogs (30% favs) | 27.2% | 5.4× |
| coin flip | 20.5% | 4.1× |
| pick like everyone else | 4.9% | 1.0× |
| always the favorite | 0.1% | 0.0× |

The lesson is *not* "underdogs are undervalued". It is that **sharing the
field's coin flip is what costs you**. Any consistent rule away from the
field's centre does several times better. The underdog side wins the tiebreak
only because favorites cover **48.89%** of decided games (n=6,793) — so fading
costs nothing in accuracy and may gain a little.

Two things this depends on:

- **It is sensitive to the crowd being wrong.** If the crowd's side covers 52%
  rather than 48.9%, fading stops helping; at 54% it hurts. The measured 48.89%
  is what makes it safe, and it is worth re-checking.
- **It assumes winner-take-all.** If your pool pays 2nd and 3rd, fade less.

## The policy

```
pool line differs from the market  ->  take the side it favours,
   (a real, measured accuracy edge)     whatever the crowd is doing

lines agree                        ->  take the side the pool is
   (a coin flip on accuracy)            least likely to be on
```

Simulation put the threshold at **0.5 points**: take every line edge you find,
higher thresholds did worse.

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
  crowd.py        what share of the pool takes each side
  recommend.py    the policy: line edges first, fade the field otherwise
  teams.py        free-text team names -> nflverse codes
  pool/
    client.py     login and fetch (login form discovered, not hardcoded)
    poolhost.py   PoolHost's sheet, matched to their real markup
    parse.py      generic sheet / pasted text -> lines
    models.py     PoolLine / PoolSheet
scripts/          fetch_data, calibrate_edge, pool_lines, make_picks,
                  research_market_efficiency (reproduces the negative result)
tests/            82 tests, including guards on the upstream sign convention
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

Working end to end, 82 tests passing.

- **The sheet parser is verified** against a real PoolHost sheet — all 16 games,
  correctly oriented. It reads each team from its logo filename
  (`/images/teamlogos/BUF.png`) rather than display text, because PoolHost
  writes the New York and Los Angeles teams as `New York (A)` / `New York (N)`
  and uses `AZ`, `JAC`, `LAR` where nflverse uses `ARI`, `JAX`, `LA`.
- **The login flow is not verified.** `poolhost.com` is blocked from the
  environment this was built in, so `client.py` has never authenticated. The
  form is discovered at runtime rather than hardcoded, but it needs one real
  run. `--html` and `--text` work regardless.
- **The crowd model is a prior, not a measurement.** `crowd.py` assumes the
  field takes the favorite on a logistic curve in the spread (63% at −3, 86% at
  −10). PoolHost publishes a **Pick Distribution** page — feeding a few weeks of
  that into `CrowdModel.fit()` replaces the guess with your pool's actual
  behaviour. This is the highest-value thing left to do: the whole fade strategy
  is sized off this number.
- **Pool size and payout structure are unmodelled.** The simulation assumes 20
  entrants, winner-take-all.
- **The market line is nflverse's consensus**, not a live intraday quote. If
  both sources refresh on similar schedules, some of that 14/16 agreement is
  them agreeing with each other rather than the pool being sharp.
