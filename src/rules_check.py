"""
Rules drift detector.

FPL changes rules between seasons and occasionally mid-season. Every number
in config/rules_2026_27.yaml was verified by hand on 17 Aug 2026, but hand
verification decays. This script re-checks the config against the live API
and shouts if they disagree.

It is deliberately non-fatal in CI: a false alarm should not stop you getting
a report an hour before the deadline. It prints loudly instead.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpl_api  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("rules_check")

ROOT = Path(__file__).resolve().parent.parent


def check() -> List[str]:
    problems: List[str] = []
    cfg = yaml.safe_load((ROOT / "config" / "rules_2026_27.yaml").read_text())

    try:
        bs = fpl_api.bootstrap()
    except Exception as e:
        return [f"could not reach FPL API: {e}"]

    gs = bs.get("game_settings", {}) or {}
    try:
        gs_live = fpl_api.game_settings()
        if isinstance(gs_live, dict):
            gs = {**gs, **gs_live}
    except Exception as e:
        log.warning("game-settings endpoint unavailable (%s), using bootstrap copy", e)

    # --- squad rules ---
    checks = [
        ("squad_squadsize", cfg["squad"]["size"], "squad size"),
        ("squad_team_limit", cfg["squad"]["max_per_club"], "max per club"),
        ("squad_total_spend", int(cfg["squad"]["budget"] * 10), "budget (tenths)"),
    ]
    for key, expected, label in checks:
        actual = gs.get(key)
        if actual is not None and actual != expected:
            problems.append(f"{label}: config says {expected}, FPL says {actual}")

    # --- transfers ---
    hit = gs.get("transfers_cost")
    if hit is not None and hit != abs(cfg["transfers"]["hit_cost"]):
        problems.append(
            f"transfer hit: config {cfg['transfers']['hit_cost']}, FPL {-hit}")

    limit = gs.get("transfers_limit") or gs.get("max_free_transfers")
    if limit is not None and limit != cfg["transfers"]["max_banked"]:
        problems.append(
            f"max banked transfers: config {cfg['transfers']['max_banked']}, "
            f"FPL {limit}")

    # --- element types (position composition) ---
    for et in bs.get("element_types", []):
        short = et.get("singular_name_short")
        expected = cfg["squad"]["composition"].get(short)
        actual = et.get("squad_select")
        if expected is not None and actual is not None and expected != actual:
            problems.append(
                f"{short} squad slots: config {expected}, FPL {actual}")
        exp_min = cfg["squad"]["formation_min"].get(short)
        act_min = et.get("squad_min_play")
        if exp_min is not None and act_min is not None and exp_min != act_min:
            problems.append(
                f"{short} minimum in XI: config {exp_min}, FPL {act_min}")

    # --- chips present in the game ---
    chip_names = {c.get("name") for c in bs.get("chips", []) if isinstance(c, dict)}
    if chip_names:
        expected_chips = {"wildcard", "freehit", "3xc", "bboost"}
        unknown = chip_names - expected_chips
        if unknown:
            problems.append(f"UNRECOGNISED CHIP(S) in FPL data: {sorted(unknown)}")

    return problems


def main() -> int:
    problems = check()
    if not problems:
        log.info("rules config matches live FPL settings")
        return 0

    print("\n" + "=" * 66)
    print("  RULES DRIFT DETECTED - config/rules_2026_27.yaml is out of date")
    print("=" * 66)
    for p in problems:
        print(f"  * {p}")
    print("=" * 66)
    print("  Update the config before trusting the optimiser.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
