"""
Thin, defensive client for the unofficial Fantasy Premier League API.

Design notes:
  * The FPL API is undocumented and field names change between seasons.
    Every field access goes through .get() with a default. Nothing here
    should raise because FPL renamed a key.
  * We set a real User-Agent. Anonymous scrapers get throttled harder.
  * Retries use exponential backoff. 503s are common around deadlines.
"""

from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

BASE = "https://fantasy.premierleague.com/api"

HEADERS = {
    "User-Agent": (
        "fpl-research-system/0.1 (personal research project; "
        "contact via GitHub issues)"
    ),
    "Accept": "application/json",
}

# Endpoints we use. Kept in one place so a rename is a one-line fix.
EP = {
    "bootstrap": "/bootstrap-static/",
    "fixtures": "/fixtures/",
    "game_settings": "/game-settings/",
    "element_summary": "/element-summary/{pid}/",
    "live": "/event/{gw}/live/",
    "entry": "/entry/{entry_id}/",
    "entry_history": "/entry/{entry_id}/history/",
    "entry_picks": "/entry/{entry_id}/event/{gw}/picks/",
    "entry_transfers": "/entry/{entry_id}/transfers/",
}


class FPLError(RuntimeError):
    pass


def _get(path: str, retries: int = 4, timeout: int = 30) -> Any:
    """GET with exponential backoff. Raises FPLError if all attempts fail."""
    url = BASE + path
    last_err: Optional[Exception] = None

    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            # 429/503 are transient; 404 is not worth retrying.
            if r.status_code == 404:
                raise FPLError(f"404 Not Found: {url}")
            last_err = FPLError(f"HTTP {r.status_code} from {url}")
        except requests.RequestException as e:  # network-level
            last_err = e

        sleep = 2 ** attempt
        log.warning("attempt %d/%d failed for %s (%s), sleeping %ds",
                    attempt + 1, retries, path, last_err, sleep)
        time.sleep(sleep)

    raise FPLError(f"all {retries} attempts failed for {url}: {last_err}")


def bootstrap() -> Dict[str, Any]:
    """Players, teams, events, element_types, game settings. The main payload."""
    return _get(EP["bootstrap"])


def fixtures(event: Optional[int] = None) -> List[Dict[str, Any]]:
    path = EP["fixtures"]
    if event is not None:
        path += f"?event={event}"
    return _get(path)


def game_settings() -> Dict[str, Any]:
    return _get(EP["game_settings"])


def entry_picks(entry_id: int, gw: int) -> Dict[str, Any]:
    """Public once the gameweek has started. No login required."""
    return _get(EP["entry_picks"].format(entry_id=entry_id, gw=gw))


def entry_transfers(entry_id: int) -> List[Dict[str, Any]]:
    return _get(EP["entry_transfers"].format(entry_id=entry_id))


def entry(entry_id: int) -> Dict[str, Any]:
    return _get(EP["entry"].format(entry_id=entry_id))


def live(gw: int) -> Dict[str, Any]:
    return _get(EP["live"].format(gw=gw))


# ---------------------------------------------------------------------------
# Helpers over the bootstrap payload
# ---------------------------------------------------------------------------

def current_event(bs: Dict[str, Any]) -> Optional[int]:
    """
    The GW currently in progress. FPL has moved this around between seasons,
    so we read the per-event booleans rather than a top-level field.
    """
    for ev in bs.get("events", []):
        if ev.get("is_current"):
            return ev.get("id")
    return None


def next_event(bs: Dict[str, Any]) -> Optional[int]:
    for ev in bs.get("events", []):
        if ev.get("is_next"):
            return ev.get("id")
    # Pre-season: nothing is current or next yet, so fall back to the first
    # event that has not finished.
    for ev in bs.get("events", []):
        if not ev.get("finished"):
            return ev.get("id")
    return None


def next_deadline(bs: Dict[str, Any]) -> Optional[str]:
    gw = next_event(bs)
    for ev in bs.get("events", []):
        if ev.get("id") == gw:
            return ev.get("deadline_time")
    return None


def team_map(bs: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    return {t["id"]: t for t in bs.get("teams", [])}


def position_map(bs: Dict[str, Any]) -> Dict[int, str]:
    return {
        et["id"]: et.get("singular_name_short", str(et["id"]))
        for et in bs.get("element_types", [])
    }


def entry_history(entry_id: int) -> Dict[str, Any]:
    """Per-GW history plus the chips already used."""
    return _get(EP["entry_history"].format(entry_id=entry_id))
