"""
Backfill 7 seasons of per-gameweek FPL data.

Source: vaastav/Fantasy-Premier-League (per-gameweek merged files).

LEAKAGE QUARANTINE
------------------
The `xP` column is dropped on ingest and never written to disk. The upstream
repo's own documentation warns it is scraped AFTER each gameweek ends and may
reflect post-match information rather than the pre-match projection managers
actually saw. It would silently inflate any backtest. It is not "cleaned" or
"shifted" here - it is deleted, because a quarantined column that still exists
in the file is a column someone will eventually use by accident.

Also note: `value` is the price DURING that gameweek and `selected` is
ownership DURING that gameweek. Both are safe as features for that same GW
(they were knowable before the deadline). Do not use them for earlier GWs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pandas as pd
import requests

log = logging.getLogger("backfill")

BASE = ("https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/"
        "master/data/{season}/gws/merged_gw.csv")

SEASONS = ["2019-20", "2020-21", "2021-22", "2022-23",
           "2023-24", "2024-25", "2025-26"]

# Never persisted. See docstring.
QUARANTINE = ["xP"]

# Columns we keep if present. Seasons have different schemas, so everything
# is optional and missing columns become NaN rather than an exception.
KEEP = [
    "name", "position", "team", "element", "GW", "round",
    "minutes", "starts", "total_points", "goals_scored", "assists",
    "clean_sheets", "goals_conceded", "saves", "bonus", "bps",
    "yellow_cards", "red_cards", "own_goals",
    "penalties_saved", "penalties_missed",
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded",
    "clearances_blocks_interceptions", "recoveries", "tackles",
    "defensive_contribution",
    "value", "selected", "transfers_in", "transfers_out",
    "was_home", "opponent_team", "kickoff_time", "fixture",
]


def fetch_season(season: str, cache_dir: Path) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"gw_{season}.csv"

    if cached.exists():
        df = pd.read_csv(cached, low_memory=False)
    else:
        url = BASE.format(season=season)
        log.info("downloading %s", season)
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        cached.write_bytes(r.content)
        df = pd.read_csv(cached, low_memory=False)

    # --- quarantine before anything else touches the frame ---
    for col in QUARANTINE:
        if col in df.columns:
            df = df.drop(columns=[col])

    df["season"] = season

    # --- position normalisation -------------------------------------------
    # Seasons disagree on labels: 'GK' vs 'GKP', and one season emits 'AM'
    # (attacking midfielder). Left unnormalised this silently corrupts BOTH
    # the minutes model (the pos_GKP feature would be 0 for ~18k goalkeeper
    # rows) and the empirical-Bayes priors (GK population split in two).
    # It throws no error - it just quietly makes the model worse.
    if "position" in df.columns:
        df["position"] = df["position"].replace({"GK": "GKP", "AM": "MID"})
    keep = [c for c in KEEP if c in df.columns]
    df = df[keep + ["season"]].copy()

    # GW column is named differently across seasons
    if "GW" not in df.columns and "round" in df.columns:
        df["GW"] = df["round"]

    # Older seasons have no `starts` column. Derive a conservative proxy:
    # 60+ minutes almost always means a start. This is imperfect for players
    # subbed on early, so it is flagged rather than silently trusted.
    if "starts" not in df.columns:
        df["starts"] = (df["minutes"] >= 60).astype(int)
        df["starts_is_proxy"] = 1
    else:
        df["starts_is_proxy"] = 0

    return df


def build(cache_dir: Path, out_path: Path,
          seasons: List[str] = None) -> pd.DataFrame:
    seasons = seasons or SEASONS
    frames = []
    for s in seasons:
        try:
            frames.append(fetch_season(s, cache_dir))
        except Exception as e:
            log.warning("skipping %s: %s", s, e)

    df = pd.concat(frames, ignore_index=True, sort=False)

    # normalised join key: names drift in punctuation/accents between seasons
    df["pkey"] = df["name"].map(_norm)

    # minutes bucket - the actual prediction target
    df["mins_bucket"] = pd.cut(
        df["minutes"], bins=[-1, 0, 59, 89, 200],
        labels=["none", "sub", "partial", "full"],
    ).astype(str)

    df = df.sort_values(["season", "GW", "pkey"]).reset_index(drop=True)

    # fail loudly if normalisation ever misses a new label
    bad = set(df["position"].dropna().unique()) - {"GKP", "DEF", "MID", "FWD"}
    if bad:
        raise ValueError(f"unrecognised position labels after normalisation: {bad}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    log.info("wrote %s (%d rows, %d seasons)", out_path, len(df), df["season"].nunique())
    return df


def _norm(s: str) -> str:
    import unicodedata
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().replace("-", " ").replace("'", "").split())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(__file__).resolve().parent.parent
    build(root / "data" / "cache", root / "data" / "history.parquet")
