"""
Point-in-time snapshot collector.

WHY THIS EXISTS
---------------
The FPL API only ever returns *current* state. There is no endpoint that
answers "what was this player's price / ownership / injury flag at 18:29 on
the GW7 deadline?". Public historical datasets store END-OF-GAMEWEEK
snapshots, which are contaminated for backtesting: by the end of GW7 the
injury news that broke during GW7 is already baked in.

So we log it ourselves, hourly, forever. Every hour not logged is ground
truth permanently lost.

STORAGE STRATEGY
----------------
Git stores every version of every file forever, so naively committing a 3MB
JSON hourly would add ~17GB/year of git objects. Instead:

  * Each run writes ONE SMALL FILE that is never modified again.
    data/snapshots/YYYY-MM-DD/HHMM_delta.csv   - only fields that CHANGED
    data/snapshots/YYYY-MM-DD/HHMM_full.csv    - full ownership sweep (6-hourly)

  * Delta files are usually 0-30 rows (~1-3KB). If nothing changed we write
    nothing at all.

  * Expected footprint: roughly 40MB for a full season.

The current state lives in data/state/last_players.json so the next run can
diff against it. That file IS overwritten each run, but it's small.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpl_api  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collect")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAP = DATA / "snapshots"
STATE = DATA / "state"

# Fields checked every hour. These are the ones that move on news and can
# flip a decision. Cheap to diff, high information value.
VOLATILE_FIELDS = [
    "now_cost",
    "status",
    "news",
    "news_added",
    "chance_of_playing_this_round",
    "chance_of_playing_next_round",
    "ep_next",
    "ep_this",
]

# Fields swept periodically for every player. Ownership drifts constantly so
# diffing it hourly would defeat the point of delta storage.
FULL_FIELDS = [
    "now_cost",
    "selected_by_percent",
    "transfers_in_event",
    "transfers_out_event",
    "form",
    "total_points",
    "minutes",
    "status",
    "chance_of_playing_next_round",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _extract(bs: Dict[str, Any], fields) -> Dict[str, Dict[str, Any]]:
    """player_id -> {field: value} for the requested fields."""
    out: Dict[str, Dict[str, Any]] = {}
    for el in bs.get("elements", []):
        pid = str(el.get("id"))
        out[pid] = {f: el.get(f) for f in fields}
    return out


def _load_state() -> Dict[str, Dict[str, Any]]:
    p = STATE / "last_players.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        log.warning("state file corrupt, treating as empty")
        return {}


def _save_state(state: Dict[str, Dict[str, Any]]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "last_players.json").write_text(json.dumps(state, sort_keys=True))


def _write_csv(path: Path, rows, header) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def _write_heartbeat(ts: datetime, n_changes: int, gw, deadline) -> None:
    """
    The report reads this. If data is stale the report must SAY SO LOUDLY
    rather than quietly advising from Tuesday's information. GitHub Actions
    does not notify you when a scheduled job fails, so this is the alarm.
    """
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "heartbeat.json").write_text(json.dumps({
        "last_run_utc": ts.isoformat(),
        "changes_detected": n_changes,
        "next_gw": gw,
        "next_deadline": deadline,
    }, indent=2))


def main() -> int:
    ts = _now()
    stamp = ts.strftime("%H%M%S")
    day = ts.strftime("%Y-%m-%d")

    log.info("fetching bootstrap-static")
    bs = fpl_api.bootstrap()

    n_players = len(bs.get("elements", []))
    if n_players == 0:
        log.error("bootstrap returned zero players - refusing to overwrite state")
        return 1
    log.info("got %d players, %d teams", n_players, len(bs.get("teams", [])))

    gw = fpl_api.next_event(bs)
    deadline = fpl_api.next_deadline(bs)

    # ---------------- hourly delta ----------------
    current = _extract(bs, VOLATILE_FIELDS)
    previous = _load_state()

    rows = []
    for pid, fields in current.items():
        prev = previous.get(pid, {})
        for field, value in fields.items():
            if prev.get(field) != value:
                rows.append([
                    ts.isoformat(), pid, field,
                    prev.get(field) if pid in previous else "",
                    value,
                ])

    if rows:
        out = SNAP / day / f"{stamp}_delta.csv"
        _write_csv(out, rows, ["as_of_utc", "player_id", "field", "old", "new"])
        log.info("wrote %d changed values to %s", len(rows), out.relative_to(ROOT))
    else:
        log.info("no changes since last run - nothing written")

    _save_state(current)

    # ---------------- periodic full sweep ----------------
    # Every 6 hours. Ownership and transfer counts for everyone.
    if ts.hour % 6 == 0:
        full = _extract(bs, FULL_FIELDS)
        frows = [[ts.isoformat(), pid] + [f.get(k) for k in FULL_FIELDS]
                 for pid, f in sorted(full.items(), key=lambda kv: int(kv[0]))]
        out = SNAP / day / f"{stamp}_full.csv"
        _write_csv(out, frows, ["as_of_utc", "player_id"] + FULL_FIELDS)
        log.info("wrote full sweep (%d players) to %s", len(frows), out.relative_to(ROOT))

    # ---------------- fixtures ----------------
    # Small, and postponements matter. Overwrite daily rather than hourly.
    fx_path = DATA / "fixtures" / f"{day}.json"
    if not fx_path.exists():
        try:
            fx = fpl_api.fixtures()
            fx_path.parent.mkdir(parents=True, exist_ok=True)
            fx_path.write_text(json.dumps(fx))
            log.info("wrote %d fixtures", len(fx))
        except Exception as e:  # non-fatal
            log.warning("fixtures fetch failed: %s", e)

    _write_heartbeat(ts, len(rows), gw, deadline)
    log.info("done. next GW=%s deadline=%s", gw, deadline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
