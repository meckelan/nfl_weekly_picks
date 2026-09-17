"""Screen factors for anything that picks against the spread better than 50%.

    python3 scripts/fetch_data.py --team-stats
    python3 scripts/research_factors.py

Method, and the reason to trust the output more than a single backtest:

  * Every factor is built **as-of** — a team's state entering a game uses only
    games already played.
  * The sample is split in half by era. Factors are screened on **1999-2012**,
    and only the ones that clear there are then checked on **2013-2025**, which
    the screen never saw. Screening 38 factors at z>2 produces about one false
    positive by chance, so a factor that only shows up in discovery means
    nothing.
  * Era consistency is weighted more heavily than the headline z. A factor that
    reads 51.8% and 51.5% across two independent 13-year halves is more
    believable than one that reads 56% in a single slice.

What survived, taking the underdog:

    every dog               n=6,793   51.11%   [99-12 51.19% | 13-25 51.03%]
    road dogs               n=4,368   51.67%   [99-12 51.79% | 13-25 51.54%]
    dogs, weeks 1-4         n=1,640   53.05%   [99-12 52.74% | 13-25 53.36%]
    road dogs, weeks 1-4    n=1,067   53.70%   [99-12 53.38% | 13-25 54.02%]

These are small. They are also mechanistically plausible: the public likes
favorites and home teams, books shade those lines accordingly, and the shading
has to come out of the favorite's side.

What did NOT survive, despite being plausible: turnover-luck regression,
blowout overreaction, ATS streaks, bye weeks, weather, totals, EPA-vs-record
divergence, backup quarterbacks.
"""

import _bootstrap  # noqa: F401
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GAMES = ROOT / "data" / "raw" / "games.csv"
STATS = ROOT / "data" / "raw" / "team_stats_weekly"

DISCOVERY_END = 2012      # screen here
VALIDATION_START = 2013   # confirm here


def team_stats() -> dict:
    """(season, week, team) -> (turnover margin, net EPA/play) for that game."""
    files = sorted(STATS.glob("stats_team_week_*.csv"))
    if not files:
        raise SystemExit("run: python3 scripts/fetch_data.py --team-stats")

    stats = pd.concat([pd.read_csv(p, low_memory=False) for p in files], ignore_index=True)
    stats = stats[stats.season_type == "REG"].copy()
    lost = ["passing_interceptions", "sack_fumbles_lost",
            "rushing_fumbles_lost", "receiving_fumbles_lost"]
    for column in lost:
        if column not in stats:
            stats[column] = 0
    stats["giveaways"] = sum(stats[c].fillna(0) for c in lost)
    stats["plays"] = stats.attempts.fillna(0) + stats.carries.fillna(0)
    stats["off_pp"] = np.where(
        stats.plays >= 1,
        (stats.passing_epa.fillna(0) + stats.rushing_epa.fillna(0)) / stats.plays.replace(0, np.nan),
        0.0,
    )
    stats = stats[["season", "week", "team", "opponent_team", "giveaways", "off_pp"]]

    # A team's takeaways are its opponent's giveaways in the same game.
    opponent = stats[["season", "week", "team", "giveaways", "off_pp"]].rename(
        columns={"team": "opponent_team", "giveaways": "takeaways", "off_pp": "def_pp"}
    )
    stats = stats.merge(opponent, on=["season", "week", "opponent_team"], how="left")
    stats["takeaways"] = stats.takeaways.fillna(0)
    stats["def_pp"] = stats.def_pp.fillna(0)

    return {
        (r.season, r.week, r.team): (r.takeaways - r.giveaways, r.off_pp - r.def_pp)
        for r in stats.itertuples()
    }


def build_state() -> pd.DataFrame:
    """Each game, plus what both teams looked like entering it."""
    games = pd.read_csv(GAMES, low_memory=False)
    games = games[games.game_type == "REG"].copy()
    games["kick"] = pd.to_datetime(
        games.gameday.astype(str) + " " + games.gametime.fillna("13:00").astype(str),
        errors="coerce",
    )
    games = games.sort_values(["season", "week", "kick"]).reset_index(drop=True)

    stat_index = team_stats()
    history: dict[str, list[dict]] = defaultdict(list)
    rows = []

    for game in games.itertuples():
        record = {"game_id": game.game_id}
        for side in ("home", "away"):
            team = game.home_team if side == "home" else game.away_team
            played = [x for x in history[team] if x["season"] == game.season]
            previous = played[-1] if played else None

            record[f"{side}_prev_margin"] = previous["margin"] if previous else np.nan

            covers = 0
            for entry in reversed(played):
                if entry["ats"] == 1:
                    covers += 1
                else:
                    break
            misses = 0
            for entry in reversed(played):
                if entry["ats"] == 0:
                    misses += 1
                else:
                    break
            record[f"{side}_cover_streak"] = covers
            record[f"{side}_fail_streak"] = misses

            recent = played[-4:]
            record[f"{side}_to_roll"] = np.mean([x["to_margin"] for x in recent]) if recent else np.nan
            record[f"{side}_epa_roll"] = np.mean([x["epa_net"] for x in recent]) if recent else np.nan
            record[f"{side}_gp"] = len(played)

            qb = game.home_qb_name if side == "home" else game.away_qb_name
            record[f"{side}_qb_change"] = int(
                bool(previous and previous["qb"] and qb and previous["qb"] != qb)
            )
        rows.append(record)

        if pd.isna(game.result):
            continue
        for side in ("home", "away"):
            team = game.home_team if side == "home" else game.away_team
            margin = game.result if side == "home" else -game.result
            ats = np.nan
            if not pd.isna(game.spread_line):
                residual = game.result - game.spread_line
                if residual != 0:
                    ats = float(residual > 0) if side == "home" else float(residual < 0)
            turnovers, epa = stat_index.get((game.season, game.week, team), (np.nan, np.nan))
            history[team].append(
                dict(season=game.season, week=game.week, margin=margin, ats=ats,
                     to_margin=turnovers, epa_net=epa,
                     qb=game.home_qb_name if side == "home" else game.away_qb_name)
            )

    return games.merge(pd.DataFrame(rows), on="game_id", how="left")


def factors(d: pd.DataFrame, dog: pd.Series) -> dict:
    """name -> mask. Every factor is scored by taking the underdog."""
    hour = pd.to_datetime(d.gametime, format="%H:%M", errors="destructive"
                          if False else "coerce").dt.hour
    always = pd.Series(True, index=d.index)
    fav_side = lambda col: pd.Series(np.where(dog, d[f"away_{col}"], d[f"home_{col}"]), index=d.index)
    dog_side = lambda col: pd.Series(np.where(dog, d[f"home_{col}"], d[f"away_{col}"]), index=d.index)

    return {
        "all dogs": always,
        "home dogs": d.spread_line < 0,
        "road dogs": d.spread_line > 0,
        "dogs, spread<=3": d.absp <= 3,
        "dogs, spread 3.5-6.5": d.absp.between(3.5, 6.5),
        "dogs, spread 7-9.5": d.absp.between(7, 9.5),
        "dogs, spread 10+": d.absp >= 10,
        "weeks 1-3 dogs": d.week <= 3,
        "weeks 1-4 dogs": d.week <= 4,
        "weeks 5-13 dogs": d.week.between(5, 13),
        "weeks 14+ dogs": d.week >= 14,
        "primetime dogs": hour >= 19,
        "thursday dogs": d.weekday == "Thursday",
        "monday dogs": d.weekday == "Monday",
        "non-primetime dogs": (hour < 19) | hour.isna(),
        "road dogs, non-primetime": (d.spread_line > 0) & ((hour < 19) | hour.isna()),
        "road dogs, weeks 1-4": (d.spread_line > 0) & (d.week <= 4),
        "divisional dogs": d.div_game == 1,
        "divisional home dogs": (d.div_game == 1) & (d.spread_line < 0),
        "dog off a bye": dog_side("rest") >= 10,
        "fav off a bye": fav_side("rest") >= 10,
        "rest edge to the dog": dog_side("rest") > fav_side("rest"),
        "fav on a short week": fav_side("rest") <= 4,
        "outdoor dogs": d.roof == "outdoors",
        "dogs indoors": d.roof.isin(["dome", "closed"]),
        "cold (<=32F) dogs": d.temp <= 32,
        "wind 15+ dogs": d.wind >= 15,
        "grass dogs": d.surface == "grass",
        "high total (50+) dogs": d.total_line >= 50,
        "low total (<=40) dogs": d.total_line <= 40,
        "fade fav off a blowout win": fav_side("prev_margin") >= 17,
        "back dog off a blowout loss": dog_side("prev_margin") <= -17,
        "fade a 3+ ATS cover streak": fav_side("cover_streak") >= 3,
        "back a 3+ ATS fail streak": dog_side("fail_streak") >= 3,
        "fade fav w/ lucky turnovers": fav_side("to_roll") >= 1.0,
        "back dog w/ unlucky turnovers": dog_side("to_roll") <= -1.0,
        "dog better by EPA": (dog_side("epa_roll") > fav_side("epa_roll")) & (d.home_gp >= 4),
        "fav has a new QB": fav_side("qb_change") == 1,
        "dog has a new QB": dog_side("qb_change") == 1,
    }


def score(d: pd.DataFrame, dog: pd.Series, mask: pd.Series, minimum: int = 40):
    sub = d[mask]
    if len(sub) < minimum:
        return None
    side = dog.reindex(sub.index)
    won = np.where(side, sub.home_cov, ~sub.home_cov)
    n, p = len(sub), won.mean()
    return n, p, (p - 0.5) / (0.25 / n) ** 0.5


def main() -> None:
    d = build_state()
    d = d[d.result.notna() & d.spread_line.notna()].copy()
    d["resid"] = d.result - d.spread_line
    d = d[d.resid != 0]                       # a push is neither won nor lost
    d["home_cov"] = d.resid > 0
    d["absp"] = d.spread_line.abs()
    dog = d.spread_line <= 0                  # True -> the home team is the dog

    table = {k: v.fillna(False).astype(bool) for k, v in factors(d, dog).items()}
    discovery = d[d.season <= DISCOVERY_END]
    validation = d[d.season >= VALIDATION_START]

    print(f"\n{len(d)} decided games. discovery {len(discovery)}, validation {len(validation)}\n")
    print(f"{'factor':<30} {'n':>6} {'disc%':>7} {'z':>6} {'   ':>3} {'n':>6} {'val%':>7} {'z':>6}")
    print("-" * 78)

    survivors = []
    for name, mask in table.items():
        a = score(discovery, dog, mask.reindex(discovery.index, fill_value=False))
        b = score(validation, dog, mask.reindex(validation.index, fill_value=False))
        if a is None:
            continue
        an, ap, az = a
        line = f"{name:<30} {an:>6} {ap * 100:>6.2f}% {az:>+6.2f}"
        if b:
            bn, bp, bz = b
            line += f" {'->':>3} {bn:>6} {bp * 100:>6.2f}% {bz:>+6.2f}"
            if az > 2:
                survivors.append((name, az, bn, bp, bz))
                line += "  **" if bz > 1 else "  *"
        print(line)

    print(f"\n{len(table)} factors screened. {len(survivors)} cleared z>2 on discovery; "
          f"chance alone gives about {len(table) * 0.025:.1f}.")
    for name, az, bn, bp, bz in survivors:
        verdict = "HOLDS" if bz > 1 else "weak" if bz > 0 else "FAILS"
        print(f"  {name:<30} discovery z={az:+.2f} -> validation {bp * 100:.2f}% "
              f"(n={bn}, z={bz:+.2f})  {verdict}")

    print("\n\n=== The rules worth using, full sample and both eras ===\n")
    for name in ["all dogs", "road dogs", "weeks 1-4 dogs", "road dogs, weeks 1-4",
                 "divisional dogs", "dogs indoors"]:
        mask = table[name]
        n, p, z = score(d, dog, mask)
        _, e1, _ = score(d[d.season <= DISCOVERY_END], dog,
                         mask.reindex(d[d.season <= DISCOVERY_END].index, fill_value=False))
        _, e2, _ = score(d[d.season >= VALIDATION_START], dog,
                         mask.reindex(d[d.season >= VALIDATION_START].index, fill_value=False))
        print(f"  {name:<24} n={n:>5}  {p * 100:>6.2f}%  z={z:>+5.2f}   "
              f"[99-12 {e1 * 100:.2f}% | 13-25 {e2 * 100:.2f}%]")


if __name__ == "__main__":
    main()
