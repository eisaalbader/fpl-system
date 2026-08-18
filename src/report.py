"""
Weekly decision report.

Writes reports/GW{n}.md and reports/latest.md. That file is what you read on
your phone, and what Claude reads when you ask for a weekly briefing.

Design rule: the report must state its own weakness. A report that hides the
fact it is running on priors, or on stale data, is worse than no report -
it launders a guess into something that looks authoritative.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpl_api      # noqa: E402
import project      # noqa: E402
import pandas as pd  # noqa: E402
import squad as squad_mod  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("report")

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def _load_yaml(p: Path) -> Dict[str, Any]:
    return yaml.safe_load(p.read_text()) or {}


def _staleness() -> str:
    """GitHub Actions does not alert on failed cron jobs. This is the alarm."""
    hb = ROOT / "data" / "state" / "heartbeat.json"
    if not hb.exists():
        return "🔴 **NO COLLECTOR DATA.** The hourly job has never run successfully."
    try:
        data = json.loads(hb.read_text())
        last = datetime.fromisoformat(data["last_run_utc"])
        age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
    except (json.JSONDecodeError, KeyError, ValueError):
        return "🔴 **HEARTBEAT UNREADABLE.** Treat everything below with suspicion."

    if age_h > 12:
        return (f"🔴 **DATA IS {age_h:.0f} HOURS OLD.** The collector has stopped. "
                f"Do not act on this report until it is fixed.")
    if age_h > 6:
        return f"🟠 **Data is {age_h:.1f}h old.** Late team news may be missing."
    return f"🟢 Data is {age_h:.1f}h old."


def _fmt_players(rows: List[Dict[str, Any]], n: int) -> str:
    out = ["| Player | Team | £ | xP | P(60+) | Mins | DefCon | Own% | Conf | Note |",
           "|---|---|--:|--:|--:|--:|--:|--:|---|---|"]
    for p in rows[:n]:
        note = p["news"][:36] if p["news"] else ("no prior" if not p["has_prior"] else "")
        dc = f"{p.get('p_defcon', 0):.2f}" if p.get("p_defcon", 0) > 0.01 else "-"
        out.append(
            f"| {p['name']} | {p['team']} | {p['cost']:.1f} | {p['xp']:.2f} | "
            f"{p.get('p_start', 0):.2f} | {p['exp_minutes']:.0f} | {dc} | "
            f"{p['own']:.1f} | {p['confidence']} | {note} |"
        )
    return "\n".join(out)


def build(gw: int = None) -> Path:
    settings = _load_yaml(ROOT / "config" / "settings.yaml")
    rules = _load_yaml(ROOT / "config" / "rules_2026_27.yaml")

    log.info("fetching live data")
    bs = fpl_api.bootstrap()
    fixtures = fpl_api.fixtures()
    gw = gw or fpl_api.next_event(bs)
    deadline = fpl_api.next_deadline(bs)

    log.info("projecting for GW%s", gw)
    hist_path = ROOT / "data" / "history.parquet"
    if not hist_path.exists():
        raise SystemExit("data/history.parquet missing - run: python src/backfill.py")
    hist = pd.read_parquet(hist_path)
    players = project.build_projections(bs, fixtures, gw, hist)

    opt_cfg = settings.get("optimiser", {}) or {}
    result = squad_mod.optimise(
        players,
        budget=float(opt_cfg.get("budget", 100.0)),
        squad_size=rules["squad"]["composition"],
        max_per_club=rules["squad"]["max_per_club"],
        formation_min=rules["squad"]["formation_min"],
        locked=opt_cfg.get("locked_players") or [],
        banned=opt_cfg.get("banned_players") or [],
    )

    now = datetime.now(timezone.utc)
    top_n = int((settings.get("report") or {}).get("top_n_by_position", 12))
    is_gw1 = (gw == 1)

    flagged = [p for p in players if p["news"]][:15]
    no_prior = [p for p in players[:120] if not p["has_prior"]][:12]

    L: List[str] = []
    A = L.append

    A(f"# GW{gw} Decision Report")
    A("")
    A(f"Generated **{now.strftime('%Y-%m-%d %H:%M UTC')}** · "
      f"Deadline **{deadline}**")
    A("")
    A(_staleness())
    A("")

    if is_gw1:
        A("> ### ⚠️ What is and is not modelled here")
        A("> There is **zero current-season Premier League data**. Everything "
          "below is built from 7 seasons of history (185,964 player-gameweek "
          "rows), not from current form.")
        A("> ")
        A("> **Modelled:** minutes distribution over {0, 1-59, 60-89, 90} "
          "(validated out-of-sample: Brier 0.173 vs 0.232 for a price "
          "heuristic — 25.7% better across 4 held-out seasons); goal and "
          "assist rates with empirical-Bayes shrinkage; clean-sheet "
          "probability; goalkeeper saves; defensive contributions as a "
          "threshold model.")
        A("> ")
        A("> **Not modelled:** joint Monte Carlo (so ceiling/floor are "
          "parametric, not sampled — they ignore that a team's defenders "
          "share clean-sheet outcomes); bonus rebuilt from the new 2026/27 "
          "BPS components; multi-gameweek planning; chip timing.")
        A("> ")
        A("> **Bonus is damped by 40%** because the 2026/27 BPS changed "
          "(CBI now 1 point per 3 actions rather than per 2, tackled penalty "
          "removed, keeper saves restructured). Historical bonus rates are "
          "miscalibrated by construction.")
        A("> ")
        A("> **Overall confidence: MODERATE.** The minutes and rate models are "
          "real and measured. Everything downstream of them is v1.")
        A("")
    A("## 1. Recommended XI")
    A("")
    A(f"Formation **{result['formation']}** · Squad cost **£{result['total_cost']}m** · "
      f"XI expected points (captain doubled) **{result['xi_xp']}**")
    A("")
    A(_fmt_players(result["xi"], 11))
    A("")

    A("## 2. Bench (in auto-sub order)")
    A("")
    A("| Order | Player | Team | £ | xP | Why here |")
    A("|---|---|---|--:|--:|---|")
    gk = result["bench_gk"][0] if result["bench_gk"] else None
    if gk:
        A(f"| GK | {gk['name']} | {gk['team']} | {gk['cost']:.1f} | {gk['xp']:.2f} | "
          f"Backup keeper — only plays if your starter is dropped |")
    for i, p in enumerate(result["bench_outfield"], 1):
        A(f"| {i} | {p['name']} | {p['team']} | {p['cost']:.1f} | {p['xp']:.2f} | "
          f"Ordered by expected points |")
    A("")

    A("## 3. Captain")
    A("")
    c, v = result["captain"], result["vice"]
    A(f"**Captain: {c['name']}** ({c['team']}, £{c['cost']:.1f}m)")
    A("")
    A(f"| | xP | Floor (p10) | Ceiling (p90) | Exp mins | Own% |")
    A("|---|--:|--:|--:|--:|--:|")
    A(f"| {c['name']} | {c['xp']:.2f} | {c['p10']:.1f} | {c['p90']:.1f} | "
      f"{c['exp_minutes']:.0f} | {c['own']:.1f} |")
    A(f"| {v['name']} (vice) | {v['xp']:.2f} | {v['p10']:.1f} | {v['p90']:.1f} | "
      f"{v['exp_minutes']:.0f} | {v['own']:.1f} |")
    A("")
    A("")
    A("**Where the captain's points come from:**")
    A("")
    A("| Appearance | Goals | Assists | Clean sheet | Saves | DefCon | Bonus |")
    A("|--:|--:|--:|--:|--:|--:|--:|")
    A(f"| {c.get('c_app',0):.2f} | {c.get('c_goals',0):.2f} | "
      f"{c.get('c_assists',0):.2f} | {c.get('c_cs',0):.2f} | "
      f"{c.get('c_saves',0):.2f} | {c.get('c_defcon',0):.2f} | "
      f"{c.get('c_bonus',0):.2f} |")
    A("")
    A("*Selected on expected points only. Ceiling/floor are parametric, not "
      "sampled. Ownership-adjusted and rank-relative captaincy needs the joint "
      "simulation (not yet built).*")
    A("")

    A("## 4. Players flagged in FPL's own news field")
    A("")
    if flagged:
        A("| Player | Team | Status | Chance | News |")
        A("|---|---|---|--:|---|")
        for p in flagged:
            ch = f"{p['chance']}%" if p["chance"] is not None else "—"
            A(f"| {p['name']} | {p['team']} | {p['status']} | {ch} | {p['news'][:70]} |")
    else:
        A("None currently flagged.")
    A("")

    A("## 5. Biggest risks in this recommendation")
    A("")
    A("1. **Minutes at the top end.** The model is measured 25.7% better than "
      "a price heuristic, but GW1 top-end calibration swings a lot "
      "season to season (+0.047, +0.065, +0.037, -0.103 across four held-out "
      "GW1s). For players shown above P(60+) = 0.6, treat the number as "
      "roughly +/- 0.07. Managers experiment in GW1.")
    if no_prior:
        names = ", ".join(f"{p['name']} ({p['team']})" for p in no_prior[:8])
        A(f"2. **Players with no usable history** — new signings, promoted-club "
          f"players, youth. These are effectively unknown: {names}")
    else:
        A("2. **New signings and promoted-club players** have no usable prior.")
    A("3. **DefCon rests on ONE season.** Defensive contributions only exist "
      "from 2025/26, so there is no cross-season validation. Rates are "
      "shrunk hard, but treat DefCon columns as the least reliable numbers "
      "in this report.")
    A("4. **Clean sheets use FPL's own strength ratings**, which at GW1 are "
      "themselves last season's guesses. Bookmaker odds would be sharper.")
    A("5. **Correlation is ignored.** Owning three defenders from one club is "
      "riskier than the individual numbers suggest — they all live or die on "
      "the same clean sheet. The joint simulation will fix this.")
    A("")

    A("## 6. News watchlist before the deadline")
    A("")
    A("Check these before locking in:")
    A("")
    A(f"- Press conferences for the clubs of your captain ({c['team']}) and "
      f"vice ({v['team']})")
    A("- Any player above with a `chance` below 100%")
    A("- Confirmed XIs are not available pre-deadline, but Friday-afternoon "
      "press conferences usually resolve the biggest doubts")
    if is_gw1:
        A("- **World Cup 2026 minutes.** Players who went deep in July have had "
          "a very short pre-season. Managers have said publicly they will manage "
          "these loads. This is not in the model.")
    A("")

    A("## 7. What this system cannot do yet")
    A("")
    A("| Capability | Status | Available from |")
    A("|---|---|---|")
    A("| Point-in-time data logging | ✅ live | now |")
    A("| Rules engine + drift alerts | ✅ live | now |")
    A("| Squad optimisation (IP) | ✅ live | now |")
    A("| Minutes model (7 seasons, validated) | ✅ live | now |")
    A("| Shrunk goal / assist / save rates | ✅ live | now |")
    A("| Clean sheet probability | ✅ v1 (strength-based) | now |")
    A("| Defensive contribution model | ✅ live (1 season of data) | now |")
    A("| Clean sheet from bookmaker odds | ❌ | GW3 |")
    A("| BPS rebuilt from 2026/27 components | ❌ | GW4 |")
    A("| Monte Carlo joint distribution | ❌ | GW5 |")
    A("| Multi-GW transfer planning | ❌ | GW6 |")
    A("| Chip option-value model | ❌ | GW8 |")
    A("| Backtest vs baselines | ❌ | GW10 |")
    A("")

    A("---")
    A("")
    A(f"*Rules spec verified {rules.get('verified_utc')}. "
      f"Chips: {rules['chips']['sets']} sets, first set expires GW"
      f"{rules['chips']['first_set_expiry_gw']}. "
      f"Max banked transfers: {rules['transfers']['max_banked']}.*")
    A("")
    A("## Appendix: top players by position")
    A("")
    for pos in ("GKP", "DEF", "MID", "FWD"):
        A(f"### {pos}")
        A("")
        A(_fmt_players([p for p in players if p["pos"] == pos], top_n))
        A("")

    text = "\n".join(L)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"GW{gw}.md"
    out.write_text(text, encoding="utf-8")
    (REPORTS / "latest.md").write_text(text, encoding="utf-8")
    log.info("wrote %s (%d chars)", out, len(text))
    return out


if __name__ == "__main__":
    build()
