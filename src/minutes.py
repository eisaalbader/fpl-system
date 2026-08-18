"""
Minutes model.

WHY THIS IS THE MOST IMPORTANT MODULE
-------------------------------------
58% of all player-gameweek rows are zero minutes. A player with elite per-90
output and a 55% start probability is worth less than a mediocre nailed
starter. Get minutes wrong and every downstream number is wrong, no matter
how good the attacking model is.

WHY BUCKETS, NOT REGRESSION
---------------------------
FPL appearance points are a STEP function (1 pt for any appearance, 2 pts at
60 minutes) and clean-sheet eligibility has a HARD 60-minute gate. Predicting
"63 expected minutes" is nearly useless: it cannot distinguish "always plays
63" from "half the time 90, half the time benched". So we predict the
distribution over four buckets and let the points model integrate over it.

    none    : 0 minutes
    sub     : 1-59
    partial : 60-89
    full    : 90+

TWO MODELS, BECAUSE GW1 IS A DIFFERENT PROBLEM
-----------------------------------------------
  cold  : no current-season data exists. Features come from last season plus
          price. Used for GW1-2. Validated by training on GW1s of past
          seasons and testing on a held-out season's GW1.
  live  : from GW3, rolling current-season windows dominate.

Both are calibrated and both report out-of-sample scores rather than
in-sample fit, because in-sample fit on football data is meaningless.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger("minutes")

BUCKETS = ["none", "sub", "partial", "full"]

# Representative minutes for each bucket, used when converting a bucket
# distribution into expected minutes. Derived from the data, not guessed.
BUCKET_MINUTES = {"none": 0.0, "sub": 28.0, "partial": 74.0, "full": 90.0}


# ---------------------------------------------------------------------------
# Feature construction
# ---------------------------------------------------------------------------

def prev_season_aggregates(hist: pd.DataFrame, season: str) -> pd.DataFrame:
    """
    Per-player totals from the season BEFORE `season`.

    Strictly backward-looking: only rows from the prior season are touched.
    """
    seasons = sorted(hist["season"].unique())
    if season not in seasons or seasons.index(season) == 0:
        return pd.DataFrame(columns=["pkey"])

    prev = seasons[seasons.index(season) - 1]
    p = hist[hist["season"] == prev]

    g = p.groupby("pkey").agg(
        prev_minutes=("minutes", "sum"),
        prev_starts=("starts", "sum"),
        prev_apps=("minutes", lambda s: int((s > 0).sum())),
        prev_gws=("GW", "nunique"),
        prev_points=("total_points", "sum"),
        prev_goals=("goals_scored", "sum"),
        prev_assists=("assists", "sum"),
        prev_bps=("bps", "sum"),
    ).reset_index()

    g["prev_start_rate"] = g["prev_starts"] / g["prev_gws"].clip(lower=1)
    g["prev_mins_per_gw"] = g["prev_minutes"] / g["prev_gws"].clip(lower=1)
    g["prev_pts_per90"] = np.where(
        g["prev_minutes"] > 0, g["prev_points"] / g["prev_minutes"] * 90.0, 0.0)
    g["prev_season"] = prev
    return g


COLD_FEATURES = [
    "price", "prev_minutes", "prev_starts", "prev_start_rate",
    "prev_mins_per_gw", "prev_pts_per90", "is_new",
    "pos_GKP", "pos_DEF", "pos_MID", "pos_FWD",
]


def build_cold_features(rows: pd.DataFrame, prev_agg: pd.DataFrame) -> pd.DataFrame:
    """rows must contain: pkey, position, price."""
    df = rows.merge(prev_agg, on="pkey", how="left")

    df["is_new"] = df["prev_minutes"].isna().astype(int)
    for c in ["prev_minutes", "prev_starts", "prev_start_rate",
              "prev_mins_per_gw", "prev_pts_per90"]:
        df[c] = df[c].fillna(0.0)

    for pos in ("GKP", "DEF", "MID", "FWD"):
        df[f"pos_{pos}"] = (df["position"] == pos).astype(int)

    return df


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class MinutesModel:
    """
    Multinomial logistic regression over the four buckets.

    Deliberately a simple, well-regularised linear model rather than a
    gradient-boosted ensemble. The published FPL literature repeatedly finds
    simple methods competitive or better out-of-sample at this data scale,
    and a linear model's coefficients can be inspected when it goes wrong.
    If a GBM demonstrably beats this out-of-sample later, swap it - but
    measure first.
    """

    def __init__(self, features: List[str] = None):
        self.features = features or COLD_FEATURES
        self.model = None
        self.classes_: List[str] = []
        self.scaler_mean_ = None
        self.scaler_std_ = None
        self.calib_ = None          # Platt scaler for P(60+ mins)

    def _scale(self, X: pd.DataFrame) -> np.ndarray:
        A = X[self.features].to_numpy(dtype=float)
        return (A - self.scaler_mean_) / self.scaler_std_

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "MinutesModel":
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import StratifiedKFold

        A = X[self.features].to_numpy(dtype=float)
        self.scaler_mean_ = A.mean(axis=0)
        self.scaler_std_ = A.std(axis=0)
        self.scaler_std_[self.scaler_std_ == 0] = 1.0
        A = (A - self.scaler_mean_) / self.scaler_std_

        self.model = LogisticRegression(max_iter=2000, C=1.0)
        self.model.fit(A, y)
        self.classes_ = list(self.model.classes_)

        # ---- calibration -------------------------------------------------
        # The raw model is systematically OVERCONFIDENT at the top end
        # (measured: -0.10 to -0.14 error where p > 0.65). Those are exactly
        # the players you captain or build a squad around, so the error lands
        # where it hurts most. Fix with Platt scaling fit on OUT-OF-FOLD
        # predictions - fitting on in-sample predictions would just relearn
        # the same overconfidence.
        y_bin = y.isin(["partial", "full"]).astype(int).to_numpy()
        oof = np.zeros(len(y_bin))
        try:
            skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
            for tr, te in skf.split(A, y_bin):
                m = LogisticRegression(max_iter=2000, C=1.0)
                m.fit(A[tr], y.iloc[tr])
                cls = list(m.classes_)
                p = m.predict_proba(A[te])
                idx = [cls.index(c) for c in ("partial", "full") if c in cls]
                oof[te] = p[:, idx].sum(axis=1) if idx else 0.0

            self.calib_ = LogisticRegression(max_iter=1000)
            self.calib_.fit(_logit(oof).reshape(-1, 1), y_bin)
        except Exception as e:  # small/degenerate folds - run uncalibrated
            log.warning("calibration skipped (%s)", e)
            self.calib_ = None

        return self

    def predict_proba(self, X: pd.DataFrame) -> pd.DataFrame:
        P = self.model.predict_proba(self._scale(X))
        out = pd.DataFrame(P, columns=self.classes_, index=X.index)
        for b in BUCKETS:                      # guarantee all four columns
            if b not in out.columns:
                out[b] = 0.0
        out = out[BUCKETS]

        if self.calib_ is not None:
            raw = (out["partial"] + out["full"]).to_numpy()
            adj = self.calib_.predict_proba(_logit(raw).reshape(-1, 1))[:, 1]
            # Rescale the 60+ mass to the calibrated total, preserving the
            # partial/full split and the sub/none split.
            with np.errstate(divide="ignore", invalid="ignore"):
                up = np.where(raw > 1e-9, adj / raw, 1.0)
                dn = np.where(raw < 1 - 1e-9, (1 - adj) / (1 - raw), 1.0)
            out["partial"] *= up
            out["full"] *= up
            out["sub"] *= dn
            out["none"] *= dn
            out = out.div(out.sum(axis=1), axis=0)

        return out

    def expected_minutes(self, X: pd.DataFrame) -> pd.Series:
        P = self.predict_proba(X)
        return sum(P[b] * BUCKET_MINUTES[b] for b in BUCKETS)

    def p_start(self, X: pd.DataFrame) -> pd.Series:
        """P(60+ minutes) - the quantity clean sheets and appearance pts hinge on."""
        P = self.predict_proba(X)
        return P["partial"] + P["full"]

    def p_appear(self, X: pd.DataFrame) -> pd.Series:
        return 1.0 - self.predict_proba(X)["none"]


# ---------------------------------------------------------------------------
# Baselines - we must beat these or the model is not earning its place
# ---------------------------------------------------------------------------

def baseline_base_rate(train_y: pd.Series, n: int) -> np.ndarray:
    """Predict the training base rate for everyone. The floor."""
    rate = (train_y.isin(["partial", "full"])).mean()
    return np.full(n, rate)


def baseline_price_tier(X: pd.DataFrame) -> np.ndarray:
    """
    The v0.1 heuristic: price tier as a proxy for status.
    This is what we are trying to beat.
    """
    def tier(row):
        m = row["price"]
        if row.get("pos_GKP", 0) == 1:
            return 0.92 if m >= 5.0 else 0.45
        if m >= 10.0: return 0.88
        if m >= 8.0:  return 0.82
        if m >= 6.5:  return 0.74
        if m >= 5.5:  return 0.62
        if m >= 4.5:  return 0.45
        return 0.28
    return X.apply(tier, axis=1).to_numpy()


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss_safe(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))
