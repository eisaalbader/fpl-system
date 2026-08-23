"""
Exact purchase prices from the collector's own snapshots.

Fixes AGENT_CONTEXT limitation 6.9 (selling prices approximated).

FPL refunds only 50% of profit, rounded down to 0.1m. Without the true purchase
price, sell value is guessed, and every report has to carry the caveat
"confirm in the app before making a transfer that depends on exact funds".

The fix costs nothing because the data already exists: collect.py has been
logging hourly point-in-time snapshots since before GW1. Prices are frozen in
pre-season, so the price in the GW1-deadline snapshot IS the purchase price for
every player in the initial squad. For players bought later, the snapshot
nearest that transfer's timestamp gives the price paid.
"""
from __future__ import annotations
import json, logging
from pathlib import Path
from typing import Dict, Optional
import pandas as pd

log = logging.getLogger("purchase_price")
ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "data" / "snapshots"


def _load_snapshots() -> pd.DataFrame:
    """All hourly snapshots as one frame: element, price, captured_at."""
    rows = []
    for f in sorted(SNAP.glob("**/*.json")):
        try:
            blob = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            log.warning("unreadable snapshot %s", f)
            continue
        ts = blob.get("captured_at") or blob.get("timestamp")
        for e in blob.get("elements", blob.get("players", [])):
            if "id" in e and "now_cost" in e:
                rows.append({"element": int(e["id"]),
                             "price": float(e["now_cost"]) / 10.0,
                             "captured_at": ts})
    if not rows:
        return pd.DataFrame(columns=["element", "price", "captured_at"])
    df = pd.DataFrame(rows)
    df["captured_at"] = pd.to_datetime(df["captured_at"], utc=True, errors="coerce")
    return df.dropna(subset=["captured_at"]).sort_values("captured_at")


def price_at(element: int, when: pd.Timestamp,
             snaps: Optional[pd.DataFrame] = None) -> Optional[float]:
    """Price of `element` at the last snapshot at or before `when`."""
    s = snaps if snaps is not None else _load_snapshots()
    sub = s[(s["element"] == element) & (s["captured_at"] <= when)]
    return float(sub.iloc[-1]["price"]) if len(sub) else None


def purchase_prices(transfers: list[dict], initial_squad: list[int],
                    gw1_deadline: pd.Timestamp) -> Dict[int, float]:
    """
    Purchase price per owned element.

    transfers: the public /entry/{id}/transfers/ payload.
    initial_squad: element ids owned at GW1.
    """
    snaps = _load_snapshots()
    if snaps.empty:
        log.warning("no snapshots found - falling back to approximation")
        return {}

    out: Dict[int, float] = {}
    for el in initial_squad:
        p = price_at(el, gw1_deadline, snaps)
        if p is not None:
            out[el] = p

    for t in sorted(transfers, key=lambda x: x.get("time", "")):
        el = t.get("element_in")
        ts = pd.to_datetime(t.get("time"), utc=True, errors="coerce")
        if el is None or pd.isna(ts):
            continue
        cost = t.get("element_in_cost")
        out[int(el)] = float(cost) / 10.0 if cost else (price_at(int(el), ts, snaps) or out.get(int(el), 0.0))
        out.pop(t.get("element_out"), None)
    return out


def selling_price(purchase: float, current: float) -> float:
    """FPL sell value: cost + 50% of profit, rounded DOWN to 0.1m."""
    if current <= purchase:
        return current
    import math
    return purchase + math.floor((current - purchase) * 10 / 2) / 10
