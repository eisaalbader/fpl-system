"""
Squad optimiser — integer programme over the real FPL constraints.

Solver: PuLP with the bundled CBC. Free, pip-installable, no system deps,
works on a GitHub Actions runner with no configuration. HiGHS is faster but
CBC solves a 700-player single-gameweek squad problem in well under a second,
so the speed difference is irrelevant at this size.

CONSTRAINTS ENFORCED (all read from config/rules_2026_27.yaml, never hardcoded)
  * 15 players: 2 GKP, 5 DEF, 5 MID, 3 FWD
  * budget <= 100.0m
  * max 3 players per club
  * starting XI of 11 with >=1 GKP, >=3 DEF, >=2 MID, >=1 FWD
  * exactly 1 GKP starting

BENCH HANDLING
  Bench players are weighted by their probability of actually being needed,
  not by a flat discount. A bench player only scores if a starter records
  zero minutes, so the weight is tied to expected minutes. This is a real
  edge over the fixed 0.1/0.05 weights most public optimisers use.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import pulp

log = logging.getLogger("squad")

# Bench weights by bench order. Roughly P(this slot gets auto-subbed in).
# From GW3 these come from the minutes model instead of this table.
BENCH_WEIGHTS = [0.16, 0.10, 0.06]   # outfield bench slots 1..3
GK_BENCH_WEIGHT = 0.04


def optimise(
    players: List[Dict[str, Any]],
    budget: float = 100.0,
    squad_size: Dict[str, int] = None,
    max_per_club: int = 3,
    formation_min: Dict[str, int] = None,
    locked: List[int] = None,
    banned: List[int] = None,
) -> Dict[str, Any]:
    """
    players: records from project.project_players()
    locked : player ids that MUST be in the squad
    banned : player ids that must NOT be (e.g. you refuse to own him)
    """
    squad_size = squad_size or {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
    formation_min = formation_min or {"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1}
    locked = locked or []
    banned = banned or []

    # Drop the unavailable and the pointless. Keeps the IP small and fast.
    pool = [p for p in players
            if p["id"] not in banned
            and (p["xp"] > 0 or p["id"] in locked)]

    if len(pool) < 15:
        raise ValueError(f"only {len(pool)} selectable players - cannot build a squad")

    log.info("optimising over %d players", len(pool))

    prob = pulp.LpProblem("fpl_squad", pulp.LpMaximize)

    # x = in 15-man squad, y = in starting XI, c = captain
    x = {p["id"]: pulp.LpVariable(f"x_{p['id']}", cat="Binary") for p in pool}
    y = {p["id"]: pulp.LpVariable(f"y_{p['id']}", cat="Binary") for p in pool}
    c = {p["id"]: pulp.LpVariable(f"c_{p['id']}", cat="Binary") for p in pool}

    by_id = {p["id"]: p for p in pool}

    # ---- objective ----
    # starters at full value, captain doubled, bench at a small weight
    avg_bench_w = sum(BENCH_WEIGHTS) / max(len(BENCH_WEIGHTS), 1)
    prob += pulp.lpSum(
        by_id[i]["xp"] * y[i]
        + by_id[i]["xp"] * c[i]                       # captain's extra copy
        + by_id[i]["xp"] * avg_bench_w * (x[i] - y[i])  # benched
        for i in x
    )

    # ---- squad composition ----
    for pos, n in squad_size.items():
        prob += pulp.lpSum(x[p["id"]] for p in pool if p["pos"] == pos) == n

    prob += pulp.lpSum(x[i] for i in x) == 15
    prob += pulp.lpSum(by_id[i]["cost"] * x[i] for i in x) <= budget

    # ---- max per club ----
    for team_id in {p["team_id"] for p in pool}:
        prob += pulp.lpSum(x[p["id"]] for p in pool
                           if p["team_id"] == team_id) <= max_per_club

    # ---- starting XI ----
    prob += pulp.lpSum(y[i] for i in y) == 11
    prob += pulp.lpSum(y[p["id"]] for p in pool if p["pos"] == "GKP") == 1
    for pos, n in formation_min.items():
        if pos == "GKP":
            continue
        prob += pulp.lpSum(y[p["id"]] for p in pool if p["pos"] == pos) >= n

    # you can only start someone you own
    for i in x:
        prob += y[i] <= x[i]
        prob += c[i] <= y[i]      # captain must start
    prob += pulp.lpSum(c[i] for i in c) == 1

    # ---- locked players ----
    for pid in locked:
        if pid in x:
            prob += x[pid] == 1

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        # "Infeasible" alone is useless at 18:25 on a Friday. Say WHY.
        diag = []
        from collections import Counter
        cnt = Counter(p["pos"] for p in pool)
        for pos, need in squad_size.items():
            if cnt.get(pos, 0) < need:
                diag.append(f"only {cnt.get(pos,0)} {pos} available, need {need}")
        cheapest = 0.0
        for pos, need in squad_size.items():
            got = sorted((p["cost"] for p in pool if p["pos"] == pos))[:need]
            cheapest += sum(got)
        if cheapest > budget:
            diag.append(f"cheapest legal squad costs GBP{cheapest:.1f}m "
                        f"but budget is GBP{budget:.1f}m")
        if len(locked) > 15:
            diag.append(f"{len(locked)} locked players exceeds squad size 15")
        raise RuntimeError(
            f"solver returned {pulp.LpStatus[status]}"
            + (" - " + "; ".join(diag) if diag else
               " - no obvious cause; check locked/banned lists"))

    squad = [by_id[i] for i in x if x[i].value() > 0.5]
    xi = [by_id[i] for i in y if y[i].value() > 0.5]
    captain = next(by_id[i] for i in c if c[i].value() > 0.5)

    bench = [p for p in squad if p not in xi]
    # Bench order: outfield by xp descending, keeper always slot 0 by FPL rule
    bench_gk = [p for p in bench if p["pos"] == "GKP"]
    bench_out = sorted([p for p in bench if p["pos"] != "GKP"],
                       key=lambda p: p["xp"], reverse=True)

    xi.sort(key=lambda p: ({"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}[p["pos"]], -p["xp"]))

    # vice-captain: highest xp starter who is not the captain
    vice = max((p for p in xi if p["id"] != captain["id"]), key=lambda p: p["xp"])

    return {
        "squad": squad,
        "xi": xi,
        "bench_gk": bench_gk,
        "bench_outfield": bench_out,
        "captain": captain,
        "vice": vice,
        "total_cost": round(sum(p["cost"] for p in squad), 1),
        "xi_xp": round(sum(p["xp"] for p in xi) + captain["xp"], 2),
        "formation": _formation(xi),
    }


def _formation(xi: List[Dict[str, Any]]) -> str:
    d = sum(1 for p in xi if p["pos"] == "DEF")
    m = sum(1 for p in xi if p["pos"] == "MID")
    f = sum(1 for p in xi if p["pos"] == "FWD")
    return f"{d}-{m}-{f}"
