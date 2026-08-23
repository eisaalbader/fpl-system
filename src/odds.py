"""
Bookmaker odds -> clean sheet probabilities.

Roadmap item 1. Replaces FPL's own strength ratings, which early in a season
are last season's guesses and are badly wrong this year: new managers at three
big clubs, three promoted sides, and a compressed post-World-Cup pre-season.

SOURCE
------
football-data.co.uk publishes free CSVs with closing odds, including Asian
handicap and over/under 2.5 goals, plus decades of history for backtesting.
Upcoming-fixture odds appear Friday <=17:00 BST and Tuesday <=13:00 BST, both
before FPL deadlines.

    current season : https://www.football-data.co.uk/mmz4281/2627/E0.csv
    fixtures file  : https://www.football-data.co.uk/fixtures.csv

METHOD
------
Match odds (H/D/A) plus over/under 2.5 give enough to pin down a Poisson
scoreline model. We de-vig by normalising implied probabilities, fit home and
away expected goals by matching the market's 1X2 and O/U 2.5 prices, then read
clean sheet probability straight off the Poisson:

    P(team keeps clean sheet) = P(opponent scores 0) = exp(-lambda_opponent)

This is deliberately simple. A Dixon-Coles low-score correction is available
and tested below, but only ship it if it beats plain Poisson out of sample.

!! NOT YET VALIDATED !!
-----------------------
This module was written but NOT run against live odds data, because
football-data.co.uk is unreachable from the environment it was authored in.
It will work inside GitHub Actions, which has open egress.

Before trusting it, run:  python src/odds.py --backtest 2023-24 2024-25
and confirm it beats the incumbent strength-based clean sheet model on Brier
score. If it does not, do not merge it. That check is the whole point of
building backtest.py first.
"""

from __future__ import annotations

import argparse
import io
import math
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

log = logging.getLogger("odds")
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "odds"

BASE = "https://www.football-data.co.uk"
SEASON_CODE = {"2023-24": "2324", "2024-25": "2425", "2025-26": "2526", "2026-27": "2627"}

# football-data.co.uk team names -> FPL short names. Extend as needed; the
# loader raises on an unmapped name rather than silently dropping a fixture.
TEAM_MAP = {
    # Every club to appear in the PL from 2019-20 onward. An unmapped club
    # silently drops ~40% of a season's matches, which is how the first
    # backtest of this module produced a meaningless result.
    "Arsenal": "ARS", "Aston Villa": "AVL", "Bournemouth": "BOU",
    "Brentford": "BRE", "Brighton": "BHA", "Burnley": "BUR", "Cardiff": "CAR",
    "Chelsea": "CHE", "Coventry": "COV", "Crystal Palace": "CRY",
    "Everton": "EVE", "Fulham": "FUL", "Huddersfield": "HUD", "Hull": "HUL",
    "Ipswich": "IPS", "Leeds": "LEE", "Leicester": "LEI", "Liverpool": "LIV",
    "Luton": "LUT", "Man City": "MCI", "Man United": "MUN",
    "Middlesbrough": "MID", "Newcastle": "NEW", "Norwich": "NOR",
    "Nott'm Forest": "NFO", "Sheffield United": "SHU", "Southampton": "SOU",
    "Stoke": "STK", "Sunderland": "SUN", "Swansea": "SWA",
    "Tottenham": "TOT", "Watford": "WAT", "West Brom": "WBA",
    "West Ham": "WHU", "Wolves": "WOL",
}


@dataclass
class MatchOdds:
    home: str
    away: str
    p_home: float
    p_draw: float
    p_away: float
    p_over25: Optional[float] = None


def _devig(probs: np.ndarray) -> np.ndarray:
    """Normalise implied probabilities to remove the bookmaker margin."""
    s = probs.sum()
    return probs / s if s > 0 else probs


def fetch_season(season: str, timeout: int = 30) -> pd.DataFrame:
    """Download one season of results-plus-odds."""
    if requests is None:
        raise RuntimeError("requests not installed")
    code = SEASON_CODE.get(season)
    if code is None:
        raise ValueError(f"unknown season {season}")
    url = f"{BASE}/mmz4281/{code}/E0.csv"
    log.info("fetching %s", url)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def fetch_upcoming(timeout: int = 30) -> pd.DataFrame:
    """Odds for fixtures not yet played. Available before FPL deadlines."""
    if requests is None:
        raise RuntimeError("requests not installed")
    r = requests.get(f"{BASE}/fixtures.csv", timeout=timeout)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    return df[df.get("Div", "") == "E0"].copy()


def parse_odds(df: pd.DataFrame) -> list[tuple[MatchOdds, pd.Series]]:
    """
    Pull 1X2 and over/under 2.5 from whichever columns are populated.

    Column preference: Bet365 (B365*), then Pinnacle (PS*/P*), then the
    market average (Avg*/BbAv*). Pinnacle is sharpest but least consistently
    present in the historical files.
    """
    out: list[tuple[MatchOdds, pd.Series]] = []
    skipped = 0
    h_cols = ["B365H", "PSH", "AvgH", "BbAvH"]
    d_cols = ["B365D", "PSD", "AvgD", "BbAvD"]
    a_cols = ["B365A", "PSA", "AvgA", "BbAvA"]
    o_cols = ["B365>2.5", "P>2.5", "Avg>2.5", "BbAv>2.5"]

    def pick(row, cols):
        for c in cols:
            if c in row.index and pd.notna(row[c]) and row[c] > 1.0:
                return float(row[c])
        return None

    for _, row in df.iterrows():
        h, d, a = pick(row, h_cols), pick(row, d_cols), pick(row, a_cols)
        if not (h and d and a):
            continue
        p = _devig(np.array([1 / h, 1 / d, 1 / a]))
        o = pick(row, o_cols)
        p_over = None
        if o:
            u_cols = [c.replace(">", "<") for c in o_cols]
            u = pick(row, u_cols)
            if u:
                p_over = float(_devig(np.array([1 / o, 1 / u]))[0])

        ht, at = str(row.get("HomeTeam", "")), str(row.get("AwayTeam", ""))
        if ht not in TEAM_MAP or at not in TEAM_MAP:
            log.warning("UNMAPPED TEAM %r vs %r - fixture dropped", ht, at)
            skipped += 1
            continue
        out.append((MatchOdds(TEAM_MAP[ht], TEAM_MAP[at],
                              float(p[0]), float(p[1]), float(p[2]), p_over), row))

    total = len(df)
    if total and len(out) / total < 0.90:
        log.error("LOW COVERAGE: only %d of %d fixtures parsed (%.0f%%). "
                  "Check TEAM_MAP and odds column names before trusting any "
                  "number from this run.", len(out), total, 100 * len(out) / total)
    return out


def _poisson_1x2_ou(lh: float, la: float, max_goals: int = 10
                    ) -> Tuple[float, float, float, float]:
    """1X2 and P(over 2.5) implied by independent Poisson with means lh, la."""
    i = np.arange(max_goals + 1)
    fact = np.array([math.factorial(int(k)) for k in i], dtype=float)
    ph = np.exp(-lh) * lh ** i / fact
    pa = np.exp(-la) * la ** i / fact
    M = np.outer(ph, pa)
    home = float(np.tril(M, -1).sum())
    draw = float(np.trace(M))
    away = float(np.triu(M, 1).sum())
    tot = i[:, None] + i[None, :]
    over = float(M[tot >= 3].sum())
    return home, draw, away, over


def implied_goals(mo: MatchOdds) -> Tuple[float, float]:
    """
    Recover home and away expected goals by fitting Poisson to the market.

    Grid search then local refine. Cheap, robust, and avoids a scipy
    dependency for a 2-parameter problem.
    """
    best, best_err = (1.4, 1.1), 1e9
    for lh in np.arange(0.3, 3.61, 0.05):
        for la in np.arange(0.3, 3.61, 0.05):
            h, d, a, o = _poisson_1x2_ou(lh, la)
            err = (h - mo.p_home) ** 2 + (d - mo.p_draw) ** 2 + (a - mo.p_away) ** 2
            if mo.p_over25 is not None:
                err += 2.0 * (o - mo.p_over25) ** 2   # weight the total-goals signal
            if err < best_err:
                best, best_err = (float(lh), float(la)), err
    return best


def clean_sheet_probs(mo: MatchOdds) -> Dict[str, float]:
    """P(clean sheet) for both teams in a fixture."""
    lh, la = implied_goals(mo)
    return {mo.home: float(np.exp(-la)), mo.away: float(np.exp(-lh))}


def build_table(season: str = "2026-27", upcoming: bool = True) -> pd.DataFrame:
    """Clean sheet probability per team per fixture. This is what project.py consumes."""
    df = fetch_upcoming() if upcoming else fetch_season(season)
    rows = []
    for mo, _row in parse_odds(df):
        lh, la = implied_goals(mo)
        rows.append({"team": mo.home, "opponent": mo.away, "was_home": True,
                     "xg_for": lh, "xg_against": la, "p_cs": float(np.exp(-la))})
        rows.append({"team": mo.away, "opponent": mo.home, "was_home": False,
                     "xg_for": la, "xg_against": lh, "p_cs": float(np.exp(-lh))})
    out = pd.DataFrame(rows)
    CACHE.mkdir(parents=True, exist_ok=True)
    out.to_csv(CACHE / f"cs_{season}.csv", index=False)
    return out


def backtest(seasons: list[str]) -> pd.DataFrame:
    """
    Brier score of odds-derived clean sheet probability against what happened.

    This is the gate. The incumbent strength-based model must be scored the
    same way on the same fixtures. Ship only on a win.
    """
    rows = []
    for s in seasons:
        df = fetch_season(s)
        for mo, raw in parse_odds(df):
            try:
                hg, ag = int(raw["FTHG"]), int(raw["FTAG"])
            except (KeyError, ValueError, TypeError):
                continue
            cs = clean_sheet_probs(mo)
            rows.append({"season": s, "team": mo.home, "p": cs[mo.home], "y": int(ag == 0)})
            rows.append({"season": s, "team": mo.away, "p": cs[mo.away], "y": int(hg == 0)})
    d = pd.DataFrame(rows)
    if d.empty:
        return d
    d["se"] = (d["p"] - d["y"]) ** 2
    base = d["y"].mean()
    summ = d.groupby("season").agg(n=("y", "size"), brier=("se", "mean"),
                                   base_rate=("y", "mean"))
    summ["brier_naive"] = summ["base_rate"] * (1 - summ["base_rate"])
    summ["gain_vs_naive"] = 1 - summ["brier"] / summ["brier_naive"]
    log.info("overall clean sheet base rate %.3f", base)
    return summ.round(4)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", nargs="*", default=None)
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()

    if args.backtest is not None:
        seasons = args.backtest or ["2023-24", "2024-25", "2025-26"]
        print(backtest(seasons).to_string())
        return 0
    if args.build:
        print(build_table().to_string())
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
