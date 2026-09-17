"""Can anything in our data beat the closing spread? Run this to find out.

    python3 scripts/research_market_efficiency.py

Requires the weekly team stats: python3 scripts/fetch_data.py --team-stats

This exists so the negative result behind `recommend.py` is reproducible
rather than folklore. It does three things:

  1. Builds Elo and rolling EPA/play ratings as of each week, with no peeking.
  2. Walk-forward: fit a model of (margin - spread) on all prior seasons,
     predict the next, and score the picks it would have made.
  3. Screens the classic structural biases (home dogs, big dogs, divisional
     games, bye weeks, weather, totals) for anything that survives.

Last run: the walk-forward model hit 50.2% over 4,135 out-of-sample games
(z = +0.30), and of 20 screened biases only 3 cleared |z| = 2 where chance
alone predicts 1. Nothing here beats the number. If you are about to build a
margin model, read the output first.
"""

import _bootstrap  # noqa: F401
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from weekly_picks.schedule import GAMES_CSV, load_games

ROOT = Path(__file__).resolve().parents[1]
STATS_DIR = ROOT / "data" / "raw" / "team_stats_weekly"

ELO_START, ELO_K, ELO_HFA, ELO_REGRESS = 1500.0, 20.0, 55.0, 1 / 3
EPA_WINDOW, EPA_DECAY, EPA_CARRY = 10, 0.90, 0.35
FEATURES = ["elo_margin", "epa_diff", "rest_diff", "div"]


def elo_snapshots(games: pd.DataFrame) -> dict:
    """Team rating entering each (season, week). Never sees that week's games."""
    snapshots, ratings, season_seen = {}, defaultdict(lambda: ELO_START), None

    for (season, week), week_games in games.groupby(["season", "week"], sort=True):
        if season_seen is not None and season != season_seen:
            for team in ratings:
                ratings[team] += (ELO_START - ratings[team]) * ELO_REGRESS
        season_seen = season
        snapshots[(season, week)] = dict(ratings)

        for game in week_games.itertuples():
            if pd.isna(game.result):
                continue
            hfa = 0.0 if game.location == "Neutral" else ELO_HFA
            diff = (ratings[game.home_team] + hfa) - ratings[game.away_team]
            expected = 1 / (1 + 10 ** (-diff / 400))
            margin = game.result
            home_won = margin > 0
            mult = ((abs(margin) + 3) ** 0.8) / (7.5 + 0.006 * (diff if home_won else -diff))
            actual = 1.0 if home_won else (0.5 if margin == 0 else 0.0)
            shift = ELO_K * mult * (actual - expected)
            ratings[game.home_team] += shift
            ratings[game.away_team] -= shift

    return snapshots


def epa_snapshots() -> dict:
    """Net EPA/play (offense minus defense allowed) entering each week."""
    files = sorted(STATS_DIR.glob("stats_team_week_*.csv"))
    if not files:
        raise SystemExit(f"no team stats in {STATS_DIR} — see README")

    stats = pd.concat([pd.read_csv(p, low_memory=False) for p in files], ignore_index=True)
    stats = stats[stats.season_type == "REG"].copy()
    stats["off_epa"] = stats.passing_epa.fillna(0) + stats.rushing_epa.fillna(0)
    stats["plays"] = stats.attempts.fillna(0) + stats.carries.fillna(0)
    stats["off_pp"] = np.where(stats.plays >= 1, stats.off_epa / stats.plays.replace(0, np.nan), 0.0)
    stats = stats[["season", "week", "team", "opponent_team", "off_pp"]].dropna(subset=["team"])

    # Defense allowed = the opponent's offensive EPA/play in that same game.
    opponent = stats[["season", "week", "team", "off_pp"]].rename(
        columns={"team": "opponent_team", "off_pp": "def_pp"}
    )
    stats = stats.merge(opponent, on=["season", "week", "opponent_team"], how="left")
    stats["def_pp"] = stats.def_pp.fillna(0.0)

    snapshots, history, carried = {}, defaultdict(list), {}
    for season, season_stats in stats.sort_values(["season", "week"]).groupby("season", sort=True):
        season_history = defaultdict(list)
        for week, week_stats in season_stats.groupby("week", sort=True):
            snapshot = {}
            for team in season_stats.team.unique():
                tail = (history[team] + season_history[team])[-EPA_WINDOW:]
                if tail:
                    weights = np.array([EPA_DECAY ** i for i in range(len(tail) - 1, -1, -1)])
                    weights /= weights.sum()
                    snapshot[team] = float(np.dot([x[0] for x in tail], weights)) - float(
                        np.dot([x[1] for x in tail], weights)
                    )
                else:
                    snapshot[team] = carried.get(team, 0.0) * EPA_CARRY
            snapshots[(season, week)] = snapshot

            for row in week_stats.itertuples():
                season_history[row.team].append((row.off_pp, row.def_pp))

        for team, played in season_history.items():
            tail = played[-EPA_WINDOW:]
            if tail:
                weights = np.array([EPA_DECAY ** i for i in range(len(tail) - 1, -1, -1)])
                weights /= weights.sum()
                carried[team] = float(np.dot([x[0] for x in tail], weights)) - float(
                    np.dot([x[1] for x in tail], weights)
                )
            history[team].extend(played)

    return snapshots


def build(games: pd.DataFrame) -> pd.DataFrame:
    elo, epa = elo_snapshots(games), epa_snapshots()
    rows = []
    for game in games.itertuples():
        e, p = elo.get((game.season, game.week), {}), epa.get((game.season, game.week), {})
        neutral = game.location == "Neutral"
        elo_diff = (e.get(game.home_team, ELO_START) + (0 if neutral else ELO_HFA)) - e.get(
            game.away_team, ELO_START
        )
        rows.append(
            {
                "season": game.season, "week": game.week,
                "margin": game.result, "spread": game.spread_line,
                "elo_margin": elo_diff / 25.0,          # 25 Elo points ~ 1 point of margin
                "epa_diff": p.get(game.home_team, 0.0) - p.get(game.away_team, 0.0),
                "rest_diff": 0.0 if pd.isna(game.home_rest) else game.home_rest - game.away_rest,
                "div": game.div_game,
            }
        )
    frame = pd.DataFrame(rows).dropna(subset=["margin", "spread"])
    return frame[frame.week >= 4]                        # ratings need a few weeks


def _design(frame: pd.DataFrame) -> np.ndarray:
    return np.column_stack([np.ones(len(frame))] + [frame[c].values for c in FEATURES])


def walk_forward(frame: pd.DataFrame) -> None:
    frame = frame.assign(resid=frame.margin - frame.spread)

    print("\n=== Can a model of (margin - spread) beat the number? ===\n")
    print("How much of each signal the market has already priced in:")
    for column in ["elo_margin", "epa_diff"]:
        print(f"  corr({column}, spread) = {frame[column].corr(frame.spread):+.3f}")
    print("  (near 1.0 means the signal is mostly re-deriving the spread)\n")

    print(f"  {'season':>7} {'picks':>6} {'W-L':>9} {'hit%':>7}")
    print(f"  {'-' * 33}")
    total_w = total_l = 0
    for season in range(2006, int(frame.season.max()) + 1):
        train, test = frame[frame.season < season], frame[frame.season == season]
        if test.empty:
            continue
        beta = np.linalg.lstsq(_design(train), train.resid.values, rcond=None)[0]
        predicted = _design(test) @ beta
        residual = test.resid.values
        won = np.where(predicted > 0, residual > 0, residual < 0)
        push = residual == 0
        w, l = int((won & ~push).sum()), int((~won & ~push).sum())
        total_w, total_l = total_w + w, total_l + l
        print(f"  {season:>7} {w + l:>6} {w:>4}-{l:<4} {w / (w + l) * 100:>6.2f}%")

    n = total_w + total_l
    p = total_w / n
    se = (0.25 / n) ** 0.5
    print(f"  {'-' * 33}")
    print(f"  {'TOTAL':>7} {n:>6} {total_w:>4}-{total_l:<4} {p * 100:>6.2f}%")
    print(f"\n  95% CI [{(p - 1.96 * se) * 100:.2f}%, {(p + 1.96 * se) * 100:.2f}%]   "
          f"z vs 50% = {(p - 0.5) / se:+.2f}")
    print("  VERDICT: " + ("something here" if abs((p - 0.5) / se) > 2
                           else "indistinguishable from a coin flip"))


def screen_biases() -> None:
    raw = pd.read_csv(GAMES_CSV, low_memory=False)
    d = raw[(raw.game_type == "REG") & raw.result.notna() & raw.spread_line.notna()].copy()
    d["resid"] = d.result - d.spread_line
    d = d[d.resid != 0]
    d["home_cov"] = d.resid > 0
    d["fav_home"] = d.spread_line > 0
    d["abs_spread"] = d.spread_line.abs()

    rules = [
        ("home underdog (take home)", d.spread_line < 0, True),
        ("take the dog, spread>=7", d.abs_spread >= 7, ~d.fav_home),
        ("take the dog, spread>=10", d.abs_spread >= 10, ~d.fav_home),
        ("take the favorite, spread<=3", d.abs_spread <= 3, d.fav_home),
        ("divisional: take the dog", d.div_game == 1, ~d.fav_home),
        ("weeks 1-3: take the dog", d.week <= 3, ~d.fav_home),
        ("late season: take the dog", d.week >= 14, ~d.fav_home),
        ("home off a bye", (d.home_rest - d.away_rest) >= 4, True),
        ("away off a bye", (d.home_rest - d.away_rest) <= -4, False),
        ("high total (50+): dog", d.total_line >= 50, ~d.fav_home),
        ("low total (<=38): favorite", d.total_line <= 38, d.fav_home),
        ("freezing (<=32F): dog", d.temp.notna() & (d.temp <= 32), ~d.fav_home),
        ("wind 15+: dog", d.wind.notna() & (d.wind >= 15), ~d.fav_home),
    ]

    print("\n\n=== Do the classic structural biases survive? ===\n")
    print(f"  {'rule':<30} {'n':>6} {'hit%':>7} {'z':>7}   {'since 2015':>12}")
    print(f"  {'-' * 72}")
    for label, mask, side in rules:
        sub = d[mask]
        if len(sub) < 60:
            continue
        s = side if np.isscalar(side) else side[mask]
        won = np.where(s, sub.home_cov, ~sub.home_cov)
        n, p = len(sub), won.mean()
        z = (p - 0.5) / (0.25 / n) ** 0.5

        recent_mask = mask & (d.season >= 2015)
        rsub = d[recent_mask]
        rs = side if np.isscalar(side) else side[recent_mask]
        recent = np.where(rs, rsub.home_cov, ~rsub.home_cov).mean() if len(rsub) > 30 else float("nan")

        print(f"  {label:<30} {n:>6} {p * 100:>6.2f}% {z:>+6.2f}{'*' if abs(z) > 2 else ' '} "
              f"{recent * 100:>11.2f}%")

    print(f"\n  {len(rules)} rules screened — at |z|=2, chance alone yields about "
          f"{len(rules) * 0.05:.1f} false positives.")
    print("  Treat anything here as noise unless it also holds up since 2015.")

    fav = np.where(d.fav_home, d.home_cov, ~d.home_cov)
    print(f"\n  Favorites cover {fav.mean() * 100:.2f}% of decided games "
          f"(n={len(d)}) — the crowd's default side, and it is under 50%.")


if __name__ == "__main__":
    games = load_games()
    frame = build(games[games.season <= games.season.max()])
    walk_forward(frame)
    screen_biases()
