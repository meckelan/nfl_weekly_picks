# NFL Weekly Picks — beating the pool's spread

A weekly ATS pick'em pool: every player picks a winner against the spread in
every game, and the best season-long record wins. This project makes those
picks on Thursday afternoon, before the first kickoff.

## The idea

The closing spread is very hard to beat. Measured over **6,983 games
(1999–2026)**, the market's line is close to perfectly calibrated:

| | |
|---|---|
| mean error (margin − spread) | **+0.06 points** |
| home teams covering | **48.96%** of decided games |
| standard deviation of the error | 13.19 points |

A model that predicts game margins is trying to out-forecast that. The
realistic ceiling is a percentage point or two, and most attempts land under
50%.

**But the pool isn't offering the closing line.** It posts its lines once, when
the sheet goes up, and leaves them there. The market keeps moving all week on
injuries, weather and money. Wherever the pool's number and the current market
number disagree, you can take the side the disagreement favors — and you're
betting into a number the market itself no longer believes.

That edge is not a forecast. It's arithmetic, and it is far larger than
anything a margin model produces:

| pool line differs by | win rate (decided games) | vs. a coin flip |
|---|---|---|
| 0.5 pts | 52.3% | +2.3 |
| 1.0 pts | 54.1% | +4.1 |
| 1.5 pts | 55.7% | +5.7 |
| 2.0 pts | 57.3% | +7.3 |
| 2.5 pts | 58.7% | +8.7 |
| 3.0 pts | **60.1%** | +10.1 |
| 3.5 pts | 61.6% | +11.6 |
| 7.0 pts | 72.3% | +22.3 |

Measured, not assumed: these come from the empirical distribution of
`margin − closing_spread` over every graded game, so the NFL's key numbers
(3, 7, 10) are baked in rather than smoothed away by a normal curve.
Regenerate with `scripts/calibrate_edge.py`.

So the strategy is:

1. **Find the discrepancies.** Scrape the pool's lines, compare to the market,
   take every side with daylight. This is where essentially all the edge is.
2. **Everything else is a coin flip** until there's a margin model, and the
   report labels those games honestly rather than dressing them up.

## Usage

```bash
pip install -r requirements.txt
python3 scripts/fetch_data.py          # nflverse schedule, results, market lines
python3 scripts/calibrate_edge.py      # rebuild the edge table (optional)
```

Thursday, in two steps:

```bash
# 1. capture the pool's lines — pick whichever works
python3 scripts/pool_lines.py --live                  # scrape (needs .env)
python3 scripts/pool_lines.py --html saved_page.html  # a page saved from the browser
python3 scripts/pool_lines.py --text lines.txt        # pasted text; always works

# 2. make the picks
python3 scripts/make_picks.py --csv picks.csv
```

```
EDGES — pool line differs from the market (5 games)

  game         pick     line  market  edge    win%
  ----------------------------------------------------
  NO @ BAL     BAL      -5.5    +8.5   3.0   60.1%
  JAX @ DEN    JAX      +4.0    +2.5   1.5   55.7%
  ...

NO EDGE — lines agree, these are coin flips (11 games)
  CIN @ HOU    HOU       +2.5   coin flip (lines agree)
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
  teams.py        free-text team names -> nflverse codes
  pool/
    client.py     login and fetch (login form discovered, not hardcoded)
    parse.py      sheet HTML or pasted text -> lines
    models.py     PoolLine / PoolSheet
scripts/          fetch_data, calibrate_edge, pool_lines, make_picks
tests/            55 tests, including guards on the upstream sign convention
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

## How big is the edge in practice?

Smaller than the table above might suggest. On the first real sheet read
(2026 week 2), **14 of 16 pool lines matched the market exactly**:

| game | pool | market | edge |
|---|---|---|---|
| DET @ BUF | BUF −4.5 | BUF −5.5 | 1.0 |
| CIN @ HOU | HOU −3.0 | HOU −2.5 | 0.5 |
| the other 14 | — | — | 0 |

1.5 points of edge across the whole slate, worth about +0.06 expected wins.
PoolHost is clearly pulling a real market feed rather than setting lines by
hand and leaving them, so the gap is line *movement* since the sheet posted,
not a lazy number.

That is one week, and it is the wrong week to judge from: the market moves most
between Thursday and Sunday, and this comparison was made on Thursday. The
honest read is that the edge is real but thin, and its size is an open
empirical question.

**Measuring it properly is the next step and it is nearly free.** Each captured
sheet is committed to `data/pool/`, and nflverse's `spread_line` becomes the
*closing* line once a game is played. So after a few weeks, pool line vs.
closing line can be graded directly — no extra data collection needed, just
time.

## Status

Working end to end, 64 tests passing.

- **The sheet parser is verified** against a real PoolHost sheet — all 16 games,
  correctly oriented. It reads each team from its logo filename
  (`/images/teamlogos/BUF.png`) rather than its display text, which matters
  because PoolHost writes the New York and Los Angeles teams as `New York (A)`
  / `New York (N)`, and uses `AZ`, `JAC` and `LAR` where nflverse uses `ARI`,
  `JAX` and `LA`.
- **The login flow is not verified.** `poolhost.com` is blocked from the
  environment this was built in, so `client.py` has never authenticated. The
  form is discovered at runtime rather than hardcoded, which should survive a
  template change, but it needs one real run. `--html` and `--text` both work
  today regardless.
- **The market line is nflverse's consensus**, not a live intraday quote. If
  the two sources turn out to refresh on similar schedules, some of the 14/16
  agreement above is them agreeing with each other rather than the pool being
  sharp — a real-time odds feed would settle that.
- **No margin model yet.** EPA/play, Elo and rest are the obvious inputs, and
  the sibling survivor-pool project already has providers for all three. Given
  how many games come back with no line discrepancy, this matters more than it
  looked at the start: 14 of 16 games this week were coin flips.
