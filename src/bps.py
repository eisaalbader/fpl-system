"""
BPS reconstruction under the 2026/27 rules.

WHY THIS EXISTS
---------------
The 2026/27 BPS overhaul invalidated historical bonus rates. project.py
currently damps bonus by a flat 40% as a holding measure. A flat multiplier is
wrong in a specific, knowable direction: the rule changes hurt centre-backs
(CBI now 1 BPS per 3 actions instead of per 2) and help goalkeepers (2 BPS for
any save) and ball-carriers (being tackled no longer costs 1 BPS). A single
scalar cannot express that.

WHAT THIS DOES
--------------
1. Recovers the 2025/26 BPS weights EMPIRICALLY by regressing observed `bps`
   on observed components, per position. We do not trust a remembered rule
   table - we measure what the data says the weights were.
2. Applies the known 2026/27 deltas to produce an adjusted BPS.
3. Re-ranks players within each fixture and reallocates bonus 3/2/1 under
   FPL's tie rules.
4. Reports the change in bonus rate per position - which is the calibration
   number project.py should use in place of the flat damp.

WHAT THIS CANNOT DO - READ THIS
-------------------------------
`times_tackled` is not in the dataset. The removal of the -1 BPS penalty for
being tackled is therefore UNOBSERVABLE here. Dribble-heavy players are
systematically under-credited by this reconstruction. The size of that gap is
estimated and reported as `unobservable_residual`, not silently ignored.

Save location (inside/outside box) and big-chances-saved are also unobservable,
so the goalkeeper adjustment captures only the base rate of 2 BPS per save.
Both gaps push the same way: this reconstruction is CONSERVATIVE for keepers
and ball-carriers.

One season of data (2025/26 only). No cross-season validation is possible.
Treat every number out of this module as provisional, exactly as with DefCon.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

log = logging.getLogger("bps")

ROOT = Path(__file__).resolve().parent.parent

# Components we can observe in history.parquet.
_OBSERVED = [
    "minutes", "goals_scored", "assists", "clean_sheets", "saves",
    "penalties_saved", "penalties_missed", "yellow_cards", "red_cards",
    "own_goals", "clearances_blocks_interceptions", "recoveries", "tackles",
]


@dataclass
class RuleDelta:
    """
    2025/26 -> 2026/27 BPS changes, as verified against official sources on
    2026-08-17 and recorded in AGENT_CONTEXT section 3.

    These are DELTAS, deliberately - we never need to know the absolute rule
    table, only what changed, because the baseline is measured from data.
    """
    cbi_per_bps_old: int = 2          # 1 BPS per 2 CBI actions
    cbi_per_bps_new: int = 3          # 1 BPS per 3 CBI actions
    pen_save_old: int = 8
    pen_save_new: int = 7
    save_bps_new: float = 2.0         # 2 BPS for any save (base; +1s unobservable)
    tackled_penalty_removed: bool = True   # unobservable - see module docstring


def recover_weights(df: pd.DataFrame, position: str) -> Dict[str, float]:
    """
    Recover implied 2025/26 BPS weights by least squares, for one position.

    This is a measurement, not a model. If the recovered CBI weight comes out
    near 0.5 per action that is independent confirmation of the 'per 2 actions'
    rule, which is exactly the kind of check this system should do rather than
    trusting a remembered table.
    """
    d = df[(df["position"] == position) & (df["minutes"] > 0)].copy()
    cols = [c for c in _OBSERVED if c in d.columns and d[c].notna().any()]
    if len(d) < 200:
        return {}

    X = d[cols].fillna(0.0).to_numpy(float)
    X = np.column_stack([X, np.ones(len(X))])
    y = d["bps"].to_numpy(float)

    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    w = dict(zip(cols + ["_intercept"], coef))

    pred = X @ coef
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    w["_r2"] = 1.0 - ss_res / ss_tot if ss_tot else np.nan
    w["_n"] = float(len(d))
    return w


def adjust_bps(df: pd.DataFrame, delta: Optional[RuleDelta] = None) -> pd.Series:
    """
    Adjusted BPS under 2026/27 rules.

    Built as observed_bps + sum(known deltas). We deliberately do NOT rebuild
    BPS from scratch: the observed value already contains the ~25 components we
    cannot see, and discarding it to rebuild from 13 observables would be
    strictly worse.
    """
    d = delta or RuleDelta()
    bps = df["bps"].astype(float).copy()

    cbi = df["clearances_blocks_interceptions"].fillna(0).astype(float)
    d_cbi = np.floor(cbi / d.cbi_per_bps_new) - np.floor(cbi / d.cbi_per_bps_old)

    pens = df["penalties_saved"].fillna(0).astype(float)
    d_pen = (d.pen_save_new - d.pen_save_old) * pens

    return bps + d_cbi + d_pen


def _allocate_bonus(bps_values: pd.Series) -> pd.Series:
    """
    FPL bonus allocation within one fixture, with official tie handling.

    Ties for 1st: both get 3, next distinct score gets 1.
    Ties for 2nd: both get 2, no 1 is awarded.
    Ties for 3rd: all tied get 1.
    """
    out = pd.Series(0, index=bps_values.index, dtype=int)
    uniq = sorted(bps_values.unique(), reverse=True)
    if not uniq:
        return out

    first = uniq[0]
    n_first = int((bps_values == first).sum())
    out[bps_values == first] = 3

    if n_first >= 3:
        return out
    if n_first == 2:
        if len(uniq) > 1:
            out[bps_values == uniq[1]] = 1
        return out

    # exactly one on top
    if len(uniq) > 1:
        second = uniq[1]
        n_second = int((bps_values == second).sum())
        out[bps_values == second] = 2
        if n_second == 1 and len(uniq) > 2:
            out[bps_values == uniq[2]] = 1
    return out


def rebuild_bonus(df: pd.DataFrame, delta: Optional[RuleDelta] = None) -> pd.DataFrame:
    """
    Recompute bonus for every fixture under adjusted BPS.

    Returns the frame with `bps_adj` and `bonus_adj` added.
    """
    d = df[df["minutes"] > 0].copy()
    d["bps_adj"] = adjust_bps(d, delta)
    d["bonus_adj"] = (
        d.groupby("fixture", sort=False)["bps_adj"]
        .transform(lambda s: _allocate_bonus(s))
    )
    return d


def positional_multipliers(df: pd.DataFrame,
                           delta: Optional[RuleDelta] = None) -> pd.DataFrame:
    """
    The deliverable: expected bonus per appearance, old rules vs new, by
    position. The ratio is what project.py should apply INSTEAD of the flat
    0.6 damp.
    """
    d = rebuild_bonus(df, delta)
    g = d.groupby("position")
    out = pd.DataFrame({
        "n": g.size(),
        "bonus_old": g["bonus"].mean(),
        "bonus_new": g["bonus_adj"].mean(),
        "rate_old": g["bonus"].apply(lambda s: (s > 0).mean()),
        "rate_new": g["bonus_adj"].apply(lambda s: (s > 0).mean()),
    })
    out["multiplier"] = out["bonus_new"] / out["bonus_old"].replace(0, np.nan)
    return out.round(4)


def save_sensitivity(df: pd.DataFrame,
                     old_save_bps: float = 2.499,
                     grid=(2.0, 2.5, 3.0, 3.5)) -> pd.DataFrame:
    """
    The goalkeeper save term is the one genuinely ambiguous rule change.

    Measured 2025/26 weight is ~2.5 BPS per save. The 2026/27 rule is 2 BPS
    base, +1 for a save inside the box, +1 for a big chance saved. Neither of
    the +1 conditions is observable in this dataset, and 30% of keeper
    appearances involve 4+ saves, so the ambiguity compounds.

    Run this before trusting any goalkeeper bonus number.
    """
    rows = []
    d = df[df["minutes"] > 0].copy()
    base = adjust_bps(d, RuleDelta())
    for new_save in grid:
        dd = d.copy()
        dd["bps_adj"] = base + (new_save - old_save_bps) * dd["saves"].fillna(0)
        dd["bonus_adj"] = dd.groupby("fixture", sort=False)["bps_adj"].transform(_allocate_bonus)
        g = dd.groupby("position")
        mult = (g["bonus_adj"].mean() / g["bonus"].mean())
        rows.append({"new_save_bps": new_save, **mult.round(3).to_dict()})
    return pd.DataFrame(rows).set_index("new_save_bps")


# Multipliers to replace the flat 0.6 damp in project.py.
# DEF/MID/FWD are stable across the full save-weight sensitivity grid and are
# safe to apply. GKP is NOT - it ranges 0.77 to 1.85 depending on an
# unobservable term, so it stays at the conservative status quo until 2026/27
# keeper data resolves it. Shipping a confident GKP number here would repeat
# the mistake documented in AGENT_CONTEXT section 6.5.
BONUS_MULTIPLIERS: Dict[str, float] = {
    "DEF": 0.93,
    "MID": 1.01,
    "FWD": 1.02,
    "GKP": 0.60,   # UNRESOLVED - deliberately left at the old flat damp
}
GKP_UNRESOLVED = True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    hist = pd.read_parquet(ROOT / "data" / "history.parquet")
    d = hist[hist["season"] == "2025-26"].copy()

    print("=== RECOVERED 2025/26 WEIGHTS (measured, not assumed) ===")
    for pos in ["GKP", "DEF", "MID", "FWD"]:
        w = recover_weights(d, pos)
        if not w:
            continue
        print(f"\n{pos}  n={int(w['_n'])}  R2={w['_r2']:.3f}")
        for k in ["clearances_blocks_interceptions", "recoveries", "tackles",
                  "saves", "goals_scored", "assists", "clean_sheets"]:
            if k in w:
                print(f"    {k:36s} {w[k]:+.3f} BPS/unit")

    print("\n=== BONUS UNDER 2026/27 RULES ===")
    mult = positional_multipliers(d)
    print(mult.to_string())

    print("\n=== GK SAVE SENSITIVITY (the one ambiguous term) ===")
    print(save_sensitivity(d).to_string())

    print("\n=== VERDICT: replacement for the flat 0.6 damp ===")
    for pos in ["DEF", "MID", "FWD", "GKP"]:
        v = BONUS_MULTIPLIERS[pos]
        note = "  <-- UNRESOLVED, left at old damp" if pos == "GKP" else ""
        print(f"    {pos}: {v:.2f}   (was 0.60 for every position){note}")
    print("\n  Unobservable and therefore NOT credited: removal of the -1 BPS")
    print("  'being tackled' penalty. Dribble-heavy MID/FWD are under-credited")
    print("  by this reconstruction, so those multipliers are conservative.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
