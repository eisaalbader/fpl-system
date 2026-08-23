"""
Baseline predictors.

Purpose: give the sophisticated pipeline something to beat. A model that cannot
out-predict "how many points did he score last week" is not earning its
complexity, however elegant its internals.

Every baseline here is STRICTLY point-in-time. Features for gameweek G are built
only from rows with GW < G in the same season, plus complete prior seasons.
Nothing in this file may read the target row.

The `xP` column is never used and is not present in history.parquet - it is
quarantined at ingest in backfill.py because it is computed post-match.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict

import numpy as np
import pandas as pd

log = logging.getLogger("baselines")

# Columns that describe the OUTCOME of the row being predicted. Touching any of
# these when building features for that row is look-ahead bias.
_OUTCOME_COLS = frozenset({
    "total_points", "minutes", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "saves", "bonus", "bps", "yellow_cards", "red_cards",
    "own_goals", "penalties_saved", "penalties_missed", "starts",
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded", "clearances_blocks_interceptions",
    "recoveries", "tackles", "defensive_contribution", "mins_bucket",
})


def add_lagged_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build lagged, point-in-time features for every player-gameweek row.

    All rolling windows are shifted by one gameweek so that row G never sees
    its own outcome. Season boundaries are respected: a player's first gameweek
    of a season has no within-season history, by construction.
    """
    df = df.sort_values(["season", "element", "GW"]).copy()
    g = df.groupby(["season", "element"], sort=False)

    # --- previous gameweek ---------------------------------------------------
    df["lag_points"] = g["total_points"].shift(1)
    df["lag_minutes"] = g["minutes"].shift(1)
    df["lag_starts"] = g["starts"].shift(1)

    # --- rolling form, shifted so the current row is excluded ----------------
    for w in (3, 5, 10):
        df[f"form{w}_points"] = (
            g["total_points"].shift(1)
            .groupby([df["season"], df["element"]], sort=False)
            .rolling(w, min_periods=1).mean().reset_index(level=[0, 1], drop=True)
        )
        df[f"form{w}_minutes"] = (
            g["minutes"].shift(1)
            .groupby([df["season"], df["element"]], sort=False)
            .rolling(w, min_periods=1).mean().reset_index(level=[0, 1], drop=True)
        )

    # --- season to date (expanding, shifted) ---------------------------------
    df["std_points"] = (
        g["total_points"].shift(1)
        .groupby([df["season"], df["element"]], sort=False)
        .expanding().sum().reset_index(level=[0, 1], drop=True)
    )
    df["std_minutes"] = (
        g["minutes"].shift(1)
        .groupby([df["season"], df["element"]], sort=False)
        .expanding().sum().reset_index(level=[0, 1], drop=True)
    )
    df["std_apps"] = (
        (g["minutes"].shift(1) > 0)
        .groupby([df["season"], df["element"]], sort=False)
        .expanding().sum().reset_index(level=[0, 1], drop=True)
    )

    df["ppg"] = df["std_points"] / df["std_apps"].replace(0, np.nan)
    df["ppm"] = df["std_points"] / df["std_minutes"].replace(0, np.nan)

    # --- expected-involvement rates, shifted ---------------------------------
    if "expected_goal_involvements" in df.columns:
        df["std_xgi"] = (
            g["expected_goal_involvements"].shift(1)
            .groupby([df["season"], df["element"]], sort=False)
            .expanding().sum().reset_index(level=[0, 1], drop=True)
        )
        df["xgi90"] = 90.0 * df["std_xgi"] / df["std_minutes"].replace(0, np.nan)

    # price is known BEFORE the deadline, so `value` on the target row is legal
    df["price"] = df["value"] / 10.0

    return df


# --------------------------------------------------------------------------
# Baselines. Each takes the feature frame and returns a prediction Series.
# --------------------------------------------------------------------------

def b_naive_last(df: pd.DataFrame) -> pd.Series:
    """Last gameweek's points. The dumbest defensible forecast."""
    return df["lag_points"].fillna(0.0)


def b_form5(df: pd.DataFrame) -> pd.Series:
    """Mean points over the last 5 gameweeks. What most humans eyeball."""
    return df["form5_points"].fillna(0.0)


def b_ppg(df: pd.DataFrame) -> pd.Series:
    """Season-to-date points per appearance."""
    return df["ppg"].fillna(0.0)


def b_price(df: pd.DataFrame) -> pd.Series:
    """
    Price as a forecast. FPL prices embed the crowd's view of a player, so this
    is a surprisingly strong baseline and a good proxy for 'pick expensive
    players'. Scaled to points via a fixed factor rather than fitted, to keep
    it honest as a baseline rather than a model.
    """
    return (df["price"] - 3.8).clip(lower=0.0) * 0.55


def b_minutes_x_ppm(df: pd.DataFrame) -> pd.Series:
    """Expected minutes (recent mean) times season-to-date points per minute."""
    return (df["form5_minutes"].fillna(0.0) * df["ppm"].fillna(0.0)).clip(0, 25)


def b_xgi(df: pd.DataFrame) -> pd.Series:
    """
    Expected goal involvements per 90, scaled by recent minutes, plus a flat
    appearance term. Tests whether underlying numbers alone beat points history.
    """
    if "xgi90" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    mins = df["form5_minutes"].fillna(0.0)
    app = np.where(mins >= 60, 2.0, np.where(mins > 0, 1.0, 0.0))
    return app + 4.0 * df["xgi90"].fillna(0.0) * mins / 90.0


BASELINES: Dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    "naive_last": b_naive_last,
    "form5": b_form5,
    "ppg": b_ppg,
    "price": b_price,
    "minutes_x_ppm": b_minutes_x_ppm,
    "xgi": b_xgi,
}
