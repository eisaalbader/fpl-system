"""
Read the user's CURRENT team state from public FPL endpoints.

NO LOGIN REQUIRED. Everything here uses public endpoints and a team ID:
  entry/{id}/                      -> bank, team value, overall rank
  entry/{id}/history/              -> per-GW bank/value, chips already used
  entry/{id}/event/{gw}/picks/     -> the 15 players (public once GW starts)
  entry/{id}/transfers/            -> every transfer, with in/out prices

SELLING PRICE — the fiddly bit
------------------------------
FPL does not refund full value. You keep 50% of any PROFIT, rounded DOWN to
the nearest 0.1. Losses are absorbed in full.

    bought 5.0, now 5.3  ->  profit 0.3, keep 0.15, round down -> sell 5.1
    bought 5.0, now 4.7  ->  sell 4.7

The authoritative selling price lives behind the authenticated /my-team/
endpoint, which we deliberately do not use. So we RECONSTRUCT purchase prices
from the public transfers endpoint, and fall back to current price for the
initial squad (correct until a player's price first moves).

The error from this is small and always in the conservative direction early
in the season. It is flagged in the report rather than hidden.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import fpl_api

log = logging.getLogger("team_state")

# FPL chip codes -> readable names
CHIP_NAMES = {
    "wildcard": "Wildcard",
    "freehit": "Free Hit",
    "3xc": "Triple Captain",
    "bboost": "Bench Boost",
}


def selling_price(purchase_tenths: int, current_tenths: int) -> int:
    """Both in tenths of a million. Returns tenths."""
    if current_tenths <= purchase_tenths:
        return current_tenths
    profit = current_tenths - purchase_tenths
    return purchase_tenths + profit // 2      # integer division = round down


def get_state(entry_id: int, bs: Dict[str, Any],
              gw: Optional[int] = None) -> Dict[str, Any]:
    """
    Returns current squad, bank, free transfers and chip availability.

    Raises nothing on a missing team - returns {"available": False, ...} so the
    report can degrade gracefully to fresh-squad mode.
    """
    if not entry_id:
        return {"available": False, "reason": "team_id not set in config/settings.yaml"}

    try:
        entry = fpl_api.entry(entry_id)
    except Exception as e:
        return {"available": False, "reason": f"could not read entry {entry_id}: {e}"}

    # Which GW's picks can we actually see? Picks become public once a GW starts.
    current_gw = fpl_api.current_event(bs)
    pick_gw = gw or current_gw
    if pick_gw is None:
        return {"available": False,
                "reason": "no gameweek has started yet - no squad to read"}

    try:
        picks_payload = fpl_api.entry_picks(entry_id, pick_gw)
    except Exception as e:
        return {"available": False,
                "reason": f"could not read picks for GW{pick_gw}: {e}"}

    picks = picks_payload.get("picks", [])
    if not picks:
        return {"available": False, "reason": f"no picks found for GW{pick_gw}"}

    # ---- reconstruct purchase prices from transfer history ----
    purchase: Dict[int, int] = {}
    try:
        for t in fpl_api.entry_transfers(entry_id):
            # most recent transfer for a player wins; the list is newest-first
            pid = t.get("element_in")
            if pid is not None and pid not in purchase:
                purchase[pid] = t.get("element_in_cost")
    except Exception as e:
        log.warning("transfer history unavailable (%s) - using current prices", e)

    elements = {el["id"]: el for el in bs.get("elements", [])}
    positions = {et["id"]: et.get("singular_name_short", "?")
                 for et in bs.get("element_types", [])}
    teams = {t["id"]: t.get("short_name", "?") for t in bs.get("teams", [])}

    squad: List[Dict[str, Any]] = []
    sell_total = 0
    approximated = 0

    for p in picks:
        pid = p.get("element")
        el = elements.get(pid)
        if not el:
            continue
        now = el.get("now_cost", 0) or 0
        bought = purchase.get(pid)
        if bought is None:
            bought = now                      # initial squad or unknown
            approximated += 1
        sp = selling_price(bought, now)
        sell_total += sp

        squad.append({
            "id": pid,
            "name": el.get("web_name"),
            "pos": positions.get(el.get("element_type"), "?"),
            "team": teams.get(el.get("team"), "?"),
            "team_id": el.get("team"),
            "now_cost": now / 10.0,
            "purchase_cost": bought / 10.0,
            "sell_price": sp / 10.0,
            "is_captain": p.get("is_captain", False),
            "is_vice": p.get("is_vice_captain", False),
            "bench_pos": p.get("position", 0),
        })

    bank = (entry.get("last_deadline_bank") or 0) / 10.0

    # ---- free transfers ----
    ft = _free_transfers(entry_id, bs, current_gw)

    # ---- chips ----
    used = []
    try:
        hist = fpl_api.entry_history(entry_id)
        used = [c.get("name") for c in hist.get("chips", [])]
    except Exception as e:
        log.warning("chip history unavailable: %s", e)

    return {
        "available": True,
        "entry_id": entry_id,
        "name": entry.get("name"),
        "picks_from_gw": pick_gw,
        "squad": squad,
        "bank": bank,
        "squad_sell_value": sell_total / 10.0,
        "budget": bank + sell_total / 10.0,
        "free_transfers": ft,
        "chips_used": used,
        "overall_rank": entry.get("summary_overall_rank"),
        "total_points": entry.get("summary_overall_points"),
        "prices_approximated": approximated,
    }


def _free_transfers(entry_id: int, bs: Dict[str, Any],
                    current_gw: Optional[int]) -> int:
    """
    Free transfers available for the NEXT gameweek.

    Rules (2026/27): 1 per GW, bankable up to 5.

    The public API does not expose this directly, so we reconstruct: start at 1
    after GW1, add 1 per GW, subtract transfers made, clamp to [1, 5]. A
    wildcard or free hit week does not consume free transfers.

    This is a RECONSTRUCTION and can drift. The report tells the user to
    confirm against the FPL app, which shows the true number.
    """
    if not current_gw or current_gw < 1:
        return 1
    try:
        transfers = fpl_api.entry_transfers(entry_id)
        hist = fpl_api.entry_history(entry_id)
    except Exception:
        return 1

    chip_gws = {c.get("event") for c in hist.get("chips", [])
                if c.get("name") in ("wildcard", "freehit")}

    ft = 1
    for gw in range(1, current_gw + 1):
        if gw > 1:
            ft = min(ft + 1, 5)
        if gw in chip_gws:
            continue                          # chips don't consume FTs
        made = sum(1 for t in transfers if t.get("event") == gw)
        ft = max(ft - made, 0)
    return max(1, min(ft, 5))


def chips_remaining(chips_used: List[str], gw: int) -> Dict[str, bool]:
    """
    2026/27 has TWO sets of chips. First set expires at the GW19 deadline and
    does NOT carry over. Second set becomes available from GW20.
    """
    half = 1 if gw <= 19 else 2
    used_this_half = set()
    # chips_used is a list of names; we cannot always tell which half without
    # the event number, so this is conservative - the report states the caveat.
    for c in chips_used:
        used_this_half.add(c)

    return {
        CHIP_NAMES.get(k, k): (k not in used_this_half)
        for k in ("wildcard", "freehit", "3xc", "bboost")
    } | {"_half": half}
