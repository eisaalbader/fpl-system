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
    out = ["| Player | Team | £ | xP | Mins | Own% | Conf | Note |",
           "|---|---|--:|--:|--:|--:|---|---|"]
    for p in rows[:n]:
        note = p["news"][:44] if p["news"] else ("no prior" if not p["has_prior"] else "")
        out.append(
            f"| {p['name']} | {p['team']} | {p['cost']:.1f} | {p['xp']:.2f} | "
            f"{p['exp_minutes']:.0f} | {p['own']:.1f} | {p['confidence']} | {note} |"
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
        A("> ### ⚠️ Read this before using any number below")
        A("> There is **zero current-season data**. Every projection here is a "
          "prior built from last season's per-90 rates plus FPL's own `ep_next`. "
          "The percentile spread is a crude parametric guess, **not** a Monte "
          "Carlo distribution.")
        A("> ")
        A("> Not yet modelled: defensive contributions, bonus points, clean-sheet "
          "probability, minutes distribution. These need match-level data that "
          "does not exist until GW3.")
        A("> ")
        A("> **Confidence in this report as a whole: LOW.** It is a defensible "
          "starting squad, not a forecast.")
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
    A("*Selected on expected points only. Ceiling/floor are parametric estimates. "
      "Ownership-adjusted and rank-relative captaincy arrives once the joint "
      "simulation is built (GW4+).*")
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
    A("1. **Minutes.** The minutes model is a price-tier prior, not a model. "
      "Any player who is rotated or subbed early breaks the projection.")
    if no_prior:
        names = ", ".join(f"{p['name']} ({p['team']})" for p in no_prior[:8])
        A(f"2. **Players with no usable history** — new signings, promoted-club "
          f"players, youth. These are effectively unknown: {names}")
    else:
        A("2. **New signings and promoted-club players** have no usable prior.")
    A("3. **No bonus or DefCon modelling.** For defenders especially, this "
      "understates points for high-CBIT players and overstates ball-playing "
      "centre-backs under the new 2026/27 BPS.")
    A("4. **Fixture multiplier is crude** — derived from FPL's own strength "
      "ratings, which at GW1 are themselves last season's guesses.")
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
    A("| Minutes model | ❌ prior only | GW3 |")
    A("| Clean sheet / goals / assists split | ❌ | GW3 |")
    A("| Defensive contribution model | ❌ | GW4 |")
    A("| BPS rebuilt from components | ❌ | GW4 |")
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
