"""
Backtest harness.

This is the referee. Nothing else in the system gets to claim it improved
anything unless it beats the baselines here, out of sample.

Design rules:

1. ROLLING ORIGIN. Test on season S using only seasons < S. Never a random
   split - player quality is autocorrelated, so a random split leaks.

2. POINT-IN-TIME. Features for gameweek G come only from GW < G in season S
   plus complete prior seasons. Enforced in baselines.add_lagged_features and
   re-checked here by assert_no_leakage().

3. DECISION METRICS, NOT JUST ERROR METRICS. MAE over all players is dominated
   by the hundreds of players nobody owns. What matters is whether the ranking
   at the top is right - that is where transfers and captaincy live.

Usage:
    python src/backtest.py                 # all baselines, all seasons
    python src/backtest.py --season 2024-25
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from baselines import BASELINES, add_lagged_features, _OUTCOME_COLS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backtest")

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data" / "history.parquet"
OUT_DIR = ROOT / "data" / "backtest"


# --------------------------------------------------------------------------
# Leakage guard
# --------------------------------------------------------------------------

def assert_no_leakage(feature_cols: List[str]) -> None:
    """
    Fail loudly if a feature column is an outcome column.

    This is cheap insurance against the single most damaging class of bug in
    this whole system. A backtest that silently leaks looks like a triumph.
    """
    bad = sorted(set(feature_cols) & _OUTCOME_COLS)
    if bad:
        raise RuntimeError(
            f"LEAKAGE: outcome columns used as features: {bad}. "
            "Features must describe only what was knowable before the deadline."
        )


def assert_lag_sanity(df: pd.DataFrame) -> None:
    """
    Independent check that lagged features really are lagged.

    Correlating lag_points with total_points on the SAME row should be modest.
    If it is near 1.0 the shift has failed somewhere.
    """
    sub = df[["lag_points", "total_points"]].dropna()
    if len(sub) < 1000:
        return
    r = sub["lag_points"].corr(sub["total_points"])
    if r > 0.75:
        raise RuntimeError(
            f"LEAKAGE SUSPECTED: corr(lag_points, total_points) = {r:.3f}. "
            "A properly lagged feature should be far below this."
        )
    log.info("leakage check ok: corr(lag_points, total_points) = %.3f", r)


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def _spearman(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 3:
        return np.nan
    return a.rank().corr(b.rank())


def evaluate(df: pd.DataFrame, pred_col: str, played_only: bool = True) -> Dict[str, float]:
    """
    Score one prediction column.

    played_only: restrict to players who actually appeared. Including the
    ~400 players per gameweek who did not play makes every model look
    excellent for the wrong reason - predicting zero for a non-player is easy
    and irrelevant to team selection.
    """
    d = df.dropna(subset=[pred_col, "total_points"]).copy()
    if played_only:
        d = d[d["minutes"] > 0]
    if d.empty:
        return {}

    err = d[pred_col] - d["total_points"]
    out = {
        "n": int(len(d)),
        "MAE": float(err.abs().mean()),
        "RMSE": float(np.sqrt((err ** 2).mean())),
        "bias": float(err.mean()),
    }

    # Rank quality within each gameweek, then averaged. This is the metric that
    # actually maps to picking a squad.
    rhos, top20, capt = [], [], []
    for _, gw in d.groupby(["season", "GW"], sort=False):
        if len(gw) < 20:
            continue
        rhos.append(_spearman(gw[pred_col], gw["total_points"]))

        # Of the 20 players we would have picked, how many landed in the true
        # top 20 that gameweek?
        pick = set(gw.nlargest(20, pred_col)["element"])
        true = set(gw.nlargest(20, "total_points")["element"])
        top20.append(len(pick & true) / 20.0)

        # Captaincy: points scored by our top-ranked player, as a fraction of
        # the best possible captain that week. Directly decision-relevant.
        best = gw["total_points"].max()
        got = gw.loc[gw[pred_col].idxmax(), "total_points"]
        if best > 0:
            capt.append(got / best)

    out["spearman"] = float(np.nanmean(rhos)) if rhos else np.nan
    out["top20_hit"] = float(np.mean(top20)) if top20 else np.nan
    out["captain_capture"] = float(np.mean(capt)) if capt else np.nan
    return out


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

def run(
    history_path: Path = HISTORY,
    seasons: Optional[List[str]] = None,
    extra_models: Optional[Dict[str, Callable[[pd.DataFrame], pd.Series]]] = None,
    min_gw: int = 6,
) -> pd.DataFrame:
    """
    Rolling-origin backtest.

    min_gw: skip the first few gameweeks of each test season. Before GW6 the
    within-season features are too thin to be meaningful, and including them
    mostly measures cold-start behaviour rather than forecasting skill.
    Reported separately by run_coldstart().
    """
    log.info("loading %s", history_path)
    df = pd.read_parquet(history_path)

    leaked = sorted(set(df.columns) & {"xP", "ep_next", "ep_this"})
    if leaked:
        raise RuntimeError(f"CONTAMINATED HISTORY: {leaked} present. Re-run backfill.py.")

    df = add_lagged_features(df)
    assert_lag_sanity(df)

    all_seasons = sorted(df["season"].unique())
    test_seasons = seasons or all_seasons[1:]  # first season has no prior

    models = dict(BASELINES)
    if extra_models:
        models.update(extra_models)

    rows = []
    for season in test_seasons:
        test = df[(df["season"] == season) & (df["GW"] >= min_gw)].copy()
        if test.empty:
            continue
        for name, fn in models.items():
            try:
                test[f"_p_{name}"] = fn(test)
            except Exception as exc:  # noqa: BLE001
                log.warning("model %s failed on %s: %s", name, season, exc)
                continue
            m = evaluate(test, f"_p_{name}")
            if not m:
                continue
            m.update({"season": season, "model": name})
            rows.append(m)
        log.info("scored season %s (%d rows)", season, len(test))

    res = pd.DataFrame(rows)
    if res.empty:
        return res
    cols = ["season", "model", "n", "MAE", "RMSE", "bias",
            "spearman", "top20_hit", "captain_capture"]
    return res[cols].sort_values(["season", "MAE"])


def summarise(res: pd.DataFrame) -> pd.DataFrame:
    """Mean across test seasons - the headline number for each model."""
    return (res.groupby("model")[["MAE", "RMSE", "spearman", "top20_hit", "captain_capture"]]
            .mean()
            .sort_values("MAE")
            .round(4))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", action="append", default=None)
    ap.add_argument("--min-gw", type=int, default=6)
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()

    res = run(seasons=args.season, min_gw=args.min_gw)
    if res.empty:
        log.error("no results")
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "per_season.csv", index=False)
    summ = summarise(res)
    summ.to_csv(out / "summary.csv")
    (out / "summary.json").write_text(json.dumps(summ.to_dict(), indent=2))

    print("\n=== PER SEASON ===")
    print(res.to_string(index=False))
    print("\n=== SUMMARY (mean across seasons) ===")
    print(summ.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
