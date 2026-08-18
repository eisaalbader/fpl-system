"""
Per-90 scoring rates and the Defensive Contribution model.

EMPIRICAL-BAYES SHRINKAGE - WHY IT MATTERS MORE THAN THE MODEL CHOICE
---------------------------------------------------------------------
The single biggest source of overfitting in FPL modelling is trusting a
per-90 rate computed from a small number of minutes. A striker with 2 goals
in 180 minutes has a raw rate of 1.0 goals/90 - roughly Haaland. He is
almost certainly not roughly Haaland.

The fix is to shrink every player's raw rate toward the mean rate for their
position, with the shrinkage weight determined by how many minutes they have
actually played:

    shrunk = (player_events + k * prior_rate) / (player_90s + k)

where k is the "prior strength" in units of 90-minute matches. A player with
k 90s of data gets a 50/50 blend. k is estimated from the data by matching
the observed between-player variance, not hand-picked.

Early season this means almost everything is prior-dominated. That is CORRECT
and it should be visible in the output rather than hidden.

DEFENSIVE CONTRIBUTION - A THRESHOLD, NOT A RATE
------------------------------------------------
DefCon is +2 points for >=10 CBIT (defenders) or >=12 CBIRT (mid/fwd), capped
at 2 per match. 20 qualifying actions still scores 2, not 4.

So the quantity we need is P(count >= threshold | minutes played), NOT
expected count * some multiplier. Modelling it as a rate is the most common
error in public DefCon work and it badly misprices high-volume defenders.

We model the per-90 action count as negative binomial (counts are
overdispersed relative to Poisson - measured below) and integrate over the
minutes distribution from the minutes model.

DATA LIMITATION, STATED PLAINLY: DefCon exists in exactly ONE season
(2025-26). There is no cross-season validation available. Treat these
estimates as high-variance and shrink them hard.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

log = logging.getLogger("rates")

# Events we build per-90 rates for.
RATE_EVENTS = ["goals_scored", "assists", "bps", "saves"]

DEFCON_THRESHOLD = {"DEF": 10, "MID": 12, "FWD": 12, "GKP": 999}
DEFCON_ACTIONS_DEF = ["clearances_blocks_interceptions", "tackles"]
DEFCON_ACTIONS_MID = ["clearances_blocks_interceptions", "tackles", "recoveries"]


# ---------------------------------------------------------------------------
# Empirical Bayes
# ---------------------------------------------------------------------------

def estimate_prior_strength(events: np.ndarray, exposure: np.ndarray,
                            min_exposure: float = 5.0) -> float:
    """
    Estimate k (prior strength, in 90s) by method of moments.

    Intuition: if between-player variance in observed rates is barely more
    than what sampling noise alone would produce, then true talent varies
    little and we should shrink hard (large k). If observed variance is much
    larger than sampling noise, talent genuinely varies and we shrink less.
    """
    mask = exposure >= min_exposure
    if mask.sum() < 20:
        return 10.0                      # not enough data - shrink hard

    e, x = events[mask], exposure[mask]
    rates = e / x
    mu = e.sum() / x.sum()
    if mu <= 0:
        return 10.0

    # observed variance vs expected sampling variance (Poisson)
    obs_var = np.var(rates)
    samp_var = np.mean(mu / x)
    excess = obs_var - samp_var

    if excess <= 1e-9:
        return 50.0                      # no real talent spread detected
    k = mu / excess
    return float(np.clip(k, 1.0, 60.0))


def shrunk_rates(hist: pd.DataFrame, season: str,
                 events: list = None) -> pd.DataFrame:
    """
    Per-90 rates from `season`, shrunk toward the positional mean.

    Returns one row per (pkey, position) with `<event>_p90` columns.
    """
    events = events or RATE_EVENTS
    d = hist[hist["season"] == season].copy()
    if d.empty:
        return pd.DataFrame(columns=["pkey"])

    agg = {"minutes": ("minutes", "sum"), "position": ("position", "first")}
    for e in events:
        if e in d.columns:
            agg[e] = (e, "sum")
    g = d.groupby("pkey").agg(**agg).reset_index()
    g["n90"] = g["minutes"] / 90.0

    for e in events:
        if e not in g.columns:
            continue
        out_col = f"{e}_p90"
        g[out_col] = np.nan

        for pos in g["position"].dropna().unique():
            m = g["position"] == pos
            ev = g.loc[m, e].to_numpy(dtype=float)
            ex = g.loc[m, "n90"].to_numpy(dtype=float)

            total_ex = ex.sum()
            prior = ev.sum() / total_ex if total_ex > 0 else 0.0
            k = estimate_prior_strength(ev, ex)

            g.loc[m, out_col] = (ev + k * prior) / (ex + k)
            g.loc[m, f"{e}_prior"] = prior
            g.loc[m, f"{e}_k"] = k

    return g


# ---------------------------------------------------------------------------
# Defensive contribution
# ---------------------------------------------------------------------------

def defcon_action_rates(hist: pd.DataFrame, season: str = "2025-26") -> pd.DataFrame:
    """
    Per-90 qualifying-action counts, shrunk. Only 2025-26 has these columns.
    """
    d = hist[hist["season"] == season].copy()
    needed = set(DEFCON_ACTIONS_MID)
    if not needed.issubset(d.columns) or d[list(needed)].isna().all().all():
        log.warning("no DefCon action data for %s", season)
        return pd.DataFrame(columns=["pkey"])

    d = d[d["minutes"] > 0].copy()
    d["cbit"] = d[DEFCON_ACTIONS_DEF].fillna(0).sum(axis=1)
    d["cbirt"] = d[DEFCON_ACTIONS_MID].fillna(0).sum(axis=1)

    g = d.groupby("pkey").agg(
        position=("position", "first"),
        minutes=("minutes", "sum"),
        cbit=("cbit", "sum"),
        cbirt=("cbirt", "sum"),
        matches=("GW", "count"),
    ).reset_index()
    g["n90"] = g["minutes"] / 90.0

    for col in ("cbit", "cbirt"):
        g[f"{col}_p90"] = np.nan
        for pos in g["position"].dropna().unique():
            m = g["position"] == pos
            ev = g.loc[m, col].to_numpy(dtype=float)
            ex = g.loc[m, "n90"].to_numpy(dtype=float)
            total_ex = ex.sum()
            prior = ev.sum() / total_ex if total_ex > 0 else 0.0
            k = estimate_prior_strength(ev, ex)
            g.loc[m, f"{col}_p90"] = (ev + k * prior) / (ex + k)

    return g


def measure_dispersion(hist: pd.DataFrame, season: str = "2025-26") -> Dict[str, float]:
    """
    Are DefCon action counts overdispersed relative to Poisson?

    If variance/mean > 1 we need negative binomial, not Poisson. Measured
    rather than assumed.
    """
    d = hist[(hist["season"] == season) & (hist["minutes"] >= 60)].copy()
    if d.empty or "tackles" not in d.columns:
        return {}
    d["cbit"] = d[DEFCON_ACTIONS_DEF].fillna(0).sum(axis=1)
    d["cbirt"] = d[DEFCON_ACTIONS_MID].fillna(0).sum(axis=1)

    out = {}
    for pos, col in [("DEF", "cbit"), ("MID", "cbirt"), ("FWD", "cbirt")]:
        s = d[d["position"] == pos][col]
        if len(s) > 30 and s.mean() > 0:
            out[f"{pos}_{col}_mean"] = float(s.mean())
            out[f"{pos}_{col}_var_mean_ratio"] = float(s.var() / s.mean())
    return out


def p_defcon(action_rate_p90: float, position: str,
             minutes_dist: Dict[str, float],
             dispersion: float = 1.6) -> float:
    """
    P(hitting the DefCon threshold) integrated over the minutes distribution.

    Negative binomial with the given variance/mean ratio. Threshold is read
    from DEFCON_THRESHOLD - never hardcoded at the call site.
    """
    from scipy.stats import nbinom

    threshold = DEFCON_THRESHOLD.get(position, 999)
    if threshold > 100 or action_rate_p90 <= 0:
        return 0.0

    bucket_minutes = {"none": 0.0, "sub": 28.0, "partial": 74.0, "full": 90.0}
    total = 0.0

    for bucket, p_bucket in minutes_dist.items():
        if p_bucket <= 0:
            continue
        mins = bucket_minutes.get(bucket, 0.0)
        if mins <= 0:
            continue
        mu = action_rate_p90 * mins / 90.0
        if mu <= 0:
            continue

        # negative binomial parameterised by mean and var/mean ratio
        if dispersion <= 1.0:
            from scipy.stats import poisson
            p_hit = 1.0 - poisson.cdf(threshold - 1, mu)
        else:
            r = mu / (dispersion - 1.0)
            p = r / (r + mu)
            p_hit = 1.0 - nbinom.cdf(threshold - 1, r, p)

        total += p_bucket * p_hit

    return float(np.clip(total, 0.0, 1.0))
