"""
Transfer optimiser.

THE QUESTION THIS ANSWERS
-------------------------
Not "what is the best possible squad?" - you cannot get there from where you
are. The real question is:

    Given the 15 players I already own, my bank, and my free transfers,
    what change (if any) maximises expected points net of hit costs?

That includes the option of doing NOTHING. Rolling a free transfer is often
correct and the optimiser must be able to say so.

HOW IT WORKS
------------
An integer programme over "which players do I own after the deadline", with:
  * budget = bank + selling value of anyone I sell
  * transfers counted as players entering the squad
  * hits charged at -4 for each transfer beyond the free allowance
  * all the usual FPL constraints (15 players, 2/5/5/3, max 3 per club)

It is solved once per transfer count (0, 1, 2, 3) so the user can see the
trade-off explicitly rather than being handed a single number.

HONEST LIMITATION
-----------------
This optimises the NEXT gameweek only. A transfer that looks -0.4 this week
may be clearly right over five weeks. Multi-gameweek planning is on the
roadmap and is a genuinely bigger piece of work. Until then, the report
applies a simple decision rule stated in plain English rather than pretending
to a horizon it does not model.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pulp

log = logging.getLogger("transfers")

HIT_COST = 4.0
BENCH_WEIGHTS = [0.16, 0.10, 0.06]


def optimise_transfers(
    current_squad: List[Dict[str, Any]],
    projections: List[Dict[str, Any]],
    bank: float,
    free_transfers: int,
    max_transfers: int = 3,
    squad_size: Dict[str, int] = None,
    max_per_club: int = 3,
    formation_min: Dict[str, int] = None,
    locked: List[int] = None,
    banned: List[int] = None,
) -> List[Dict[str, Any]]:
    """
    Returns one solution per transfer count (0..max_transfers), each with net
    expected points after hits. Caller picks the best and shows the rest.
    """
    squad_size = squad_size or {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
    formation_min = formation_min or {"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1}
    locked = set(locked or [])
    banned = set(banned or [])

    if len(current_squad) != 15:
        raise ValueError(
            f"current squad has {len(current_squad)} players, expected 15. "
            "The squad read from the FPL API is incomplete - do not trust any "
            "transfer advice built on it.")

    owned = {p["id"]: p for p in current_squad}
    sell = {p["id"]: p["sell_price"] for p in current_squad}

    proj = {p["id"]: p for p in projections}

    # Candidate pool: everyone owned (so we can keep them) plus anyone
    # projected to score. Keeps the IP small.
    pool_ids = set(owned) | {p["id"] for p in projections if p["xp"] > 0}
    pool_ids -= (banned - set(owned))
    pool = [proj[i] for i in pool_ids if i in proj]

    if len(pool) < 15:
        raise ValueError(f"only {len(pool)} candidates - cannot form a squad")

    results = []
    for n_transfers in range(0, max_transfers + 1):
        try:
            r = _solve(pool, owned, sell, bank, n_transfers, free_transfers,
                       squad_size, max_per_club, formation_min, locked)
            results.append(r)
        except Exception as e:
            log.warning("no solution for %d transfers: %s", n_transfers, e)

    results.sort(key=lambda r: r["net_xp"], reverse=True)
    return results


def _solve(pool, owned, sell, bank, n_transfers, free_transfers,
           squad_size, max_per_club, formation_min, locked):
    by_id = {p["id"]: p for p in pool}
    ids = list(by_id)

    prob = pulp.LpProblem(f"fpl_transfers_{n_transfers}", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in ids}   # own after
    y = {i: pulp.LpVariable(f"y_{i}", cat="Binary") for i in ids}   # in XI
    c = {i: pulp.LpVariable(f"c_{i}", cat="Binary") for i in ids}   # captain

    hits = max(0, n_transfers - free_transfers)
    avg_bench = sum(BENCH_WEIGHTS) / len(BENCH_WEIGHTS)

    prob += (
        pulp.lpSum(by_id[i]["xp"] * y[i]
                   + by_id[i]["xp"] * c[i]
                   + by_id[i]["xp"] * avg_bench * (x[i] - y[i]) for i in ids)
        - HIT_COST * hits
    )

    # --- exactly n_transfers players entering the squad ---
    # A player "enters" if x=1 and they were not owned.
    incoming = [x[i] for i in ids if i not in owned]
    prob += pulp.lpSum(incoming) == n_transfers

    # --- budget ---
    # money available = bank + selling price of owned players we drop
    # spend = price of players we buy
    spend = pulp.lpSum(by_id[i]["cost"] * x[i] for i in ids if i not in owned)
    raised = pulp.lpSum(sell[i] * (1 - x[i]) for i in ids if i in owned)
    prob += spend <= bank + raised

    # --- squad composition ---
    prob += pulp.lpSum(x[i] for i in ids) == 15
    for pos, n in squad_size.items():
        prob += pulp.lpSum(x[i] for i in ids if by_id[i]["pos"] == pos) == n

    for team_id in {by_id[i]["team_id"] for i in ids}:
        prob += pulp.lpSum(x[i] for i in ids
                           if by_id[i]["team_id"] == team_id) <= max_per_club

    # --- starting XI ---
    prob += pulp.lpSum(y[i] for i in ids) == 11
    prob += pulp.lpSum(y[i] for i in ids if by_id[i]["pos"] == "GKP") == 1
    for pos, n in formation_min.items():
        if pos != "GKP":
            prob += pulp.lpSum(y[i] for i in ids if by_id[i]["pos"] == pos) >= n

    for i in ids:
        prob += y[i] <= x[i]
        prob += c[i] <= y[i]
    prob += pulp.lpSum(c[i] for i in ids) == 1

    for pid in locked:
        if pid in x:
            prob += x[pid] == 1

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(pulp.LpStatus[status])

    new_squad = [by_id[i] for i in ids if x[i].value() > 0.5]
    xi = [by_id[i] for i in ids if y[i].value() > 0.5]
    captain = next(by_id[i] for i in ids if c[i].value() > 0.5)

    out_players = [owned[i] for i in owned if i not in {p["id"] for p in new_squad}]
    in_players = [by_id[i] for i in ids
                  if x[i].value() > 0.5 and i not in owned]

    gross = sum(p["xp"] for p in xi) + captain["xp"]
    bench = [p for p in new_squad if p not in xi]
    bench_gk = [p for p in bench if p["pos"] == "GKP"]
    bench_out = sorted([p for p in bench if p["pos"] != "GKP"],
                       key=lambda p: p["xp"], reverse=True)

    xi.sort(key=lambda p: ({"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}[p["pos"]], -p["xp"]))
    vice = max((p for p in xi if p["id"] != captain["id"]), key=lambda p: p["xp"])

    return {
        "n_transfers": n_transfers,
        "hits": hits,
        "hit_cost": HIT_COST * hits,
        "gross_xp": round(gross, 2),
        "net_xp": round(gross - HIT_COST * hits, 2),
        "out": out_players,
        "in": in_players,
        "squad": new_squad,
        "xi": xi,
        "bench_gk": bench_gk,
        "bench_outfield": bench_out,
        "captain": captain,
        "vice": vice,
        "formation": _formation(xi),
        "spend": round(sum(p["cost"] for p in in_players), 1),
        "raised": round(sum(p["sell_price"] for p in out_players), 1),
    }


def _formation(xi):
    d = sum(1 for p in xi if p["pos"] == "DEF")
    m = sum(1 for p in xi if p["pos"] == "MID")
    f = sum(1 for p in xi if p["pos"] == "FWD")
    return f"{d}-{m}-{f}"


def decision_rule(results: List[Dict[str, Any]],
                  free_transfers: int) -> Dict[str, Any]:
    """
    Turn the solved options into a recommendation with a stated rationale.

    The thresholds below are deliberately conservative and stated openly,
    because this model only sees ONE gameweek ahead. A -4 that looks marginally
    positive over one week is usually wrong; over five weeks it is often right.
    Until multi-gameweek planning exists, we require a clear margin.
    """
    if not results:
        # Always return a usable shape - callers should never KeyError on this.
        return {"action": "error", "choice": None,
                "reason": "No feasible squad found. Usual causes: the current "
                          "squad is not 15 valid players, the bank figure is "
                          "wrong, or locked/banned lists conflict."}

    best = results[0]
    roll = next((r for r in results if r["n_transfers"] == 0), None)
    one = next((r for r in results if r["n_transfers"] == 1), None)

    # Rolling to bank a transfer has real option value, not captured by a
    # one-week model. Require a margin before spending a free transfer.
    ROLL_MARGIN = 0.4      # xP the transfer must beat rolling by
    HIT_MARGIN = 2.0       # a -4 must clear this much AFTER the hit

    if roll and best["n_transfers"] == 0:
        return {"action": "roll", "choice": roll,
                "reason": f"No transfer beats holding. Bank the free transfer "
                          f"(you'd have {min(free_transfers + 1, 5)} next week)."}

    if best["hits"] > 0:
        if roll is None:
            # No zero-transfer solution exists, so there is no baseline to
            # measure a hit against. Report it rather than inventing a margin.
            return {"action": "forced", "choice": best,
                    "reason": "Holding is not a legal option (squad is invalid "
                              "or unaffordable). These transfers are required, "
                              "not optional - verify your squad in the app."}
        margin = best["net_xp"] - roll["net_xp"]
        if margin < HIT_MARGIN:
            fallback = one if one else roll
            return {"action": "no_hit", "choice": fallback,
                    "reason": f"Taking a hit gains only {margin:+.2f} xP this "
                              f"week - not enough to justify -4 on a one-week "
                              f"model. Do the free transfer instead."}
        return {"action": "hit", "choice": best,
                "reason": f"The hit clears its cost by {margin:+.2f} xP even "
                          f"after -4. Unusual - double-check the news."}

    if roll and one:
        margin = one["net_xp"] - roll["net_xp"]
        if margin < ROLL_MARGIN:
            return {"action": "roll", "choice": roll,
                    "reason": f"The best transfer gains only {margin:+.2f} xP. "
                              f"Below the {ROLL_MARGIN} threshold - roll it and "
                              f"keep flexibility."}
        return {"action": "transfer", "choice": one,
                "reason": f"Gains {margin:+.2f} xP over holding, using a free "
                          f"transfer. No hit taken."}

    return {"action": "transfer", "choice": best, "reason": "best available option"}
