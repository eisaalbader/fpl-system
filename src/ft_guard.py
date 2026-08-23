"""
Free-transfer reconciliation guard.

Fixes AGENT_CONTEXT limitation 6.8 (free transfers are reconstructed and can
drift). The public API does not expose the free-transfer count, so
team_state._free_transfers replays transfer history. That replay is now
load-bearing: from GW2 onward the transfer optimiser's roll/hit decision
depends on it, and a silent off-by-one changes the recommendation.

This does not fix the reconstruction. It detects when it is wrong, by an
independent route: diffing consecutive picks/ payloads counts how many players
actually changed, which must agree with the replayed transfer log.

Disagreement is not fatal - it raises a flag the report prints loudly, so the
user checks the app rather than trusting a wrong number.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

log = logging.getLogger("ft_guard")

MAX_BANKED = 5  # 2026/27 rule; verified in config/rules_2026_27.yaml


@dataclass
class FTCheck:
    replayed: int
    implied: Optional[int]
    agrees: bool
    detail: str

    def banner(self) -> str:
        if self.agrees:
            return f"Free transfers: **{self.replayed}** (reconciled ✅)"
        return (f"⚠️ **FREE TRANSFER COUNT UNVERIFIED** — replay says "
                f"{self.replayed}, picks-diff implies {self.implied}. "
                f"{self.detail} **Check the FPL app before transferring.**")


def transfers_between(picks_prev: List[dict], picks_now: List[dict]) -> int:
    """How many squad slots changed between two gameweeks."""
    a = {p["element"] for p in picks_prev}
    b = {p["element"] for p in picks_now}
    return len(b - a)


def reconcile(replayed_ft: int, picks_by_gw: Dict[int, List[dict]],
              transfer_log: List[dict], current_gw: int,
              chips_used: Optional[Dict[int, str]] = None) -> FTCheck:
    """
    Cross-check the replayed free-transfer count against observed squad changes.

    Wildcard and Free Hit gameweeks are excluded: unlimited transfers there make
    the diff meaningless, and Free Hit reverts the squad afterwards.
    """
    chips_used = chips_used or {}
    gws = sorted(g for g in picks_by_gw if g <= current_gw)
    if len(gws) < 2:
        return FTCheck(replayed_ft, None, True, "Not enough history to cross-check.")

    made = 0
    for prev, now in zip(gws, gws[1:]):
        if chips_used.get(now) in {"wildcard", "freehit"}:
            continue
        made += transfers_between(picks_by_gw[prev], picks_by_gw[now])

    logged = len([t for t in transfer_log
                  if t.get("event") and t["event"] <= current_gw])

    if made != logged:
        return FTCheck(replayed_ft, None, False,
                       f"picks-diff counts {made} transfers, log has {logged}.")

    earned = min(MAX_BANKED, 1 + (current_gw - 1))
    implied = max(0, min(MAX_BANKED, earned - made))
    agrees = implied == replayed_ft
    return FTCheck(replayed_ft, implied, agrees,
                   "Independent count agrees." if agrees
                   else "Replay and picks-diff disagree.")
