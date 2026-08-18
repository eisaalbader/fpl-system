"""
Projection engine v0.2 - component assembly.

CHANGE FROM v0.1
----------------
v0.1 blended FPL's ep_next with a last-season points-per-90 figure and a
price-tier minutes guess. v0.2 replaces that with modelled components:

    minutes distribution   (minutes.MinutesModel, validated out-of-sample:
                            23.8% better Brier than the v0.1 price heuristic)
    goal rate              (rates, empirical-Bayes shrunk)
    assist rate            (rates, empirical-Bayes shrunk)
    clean sheet            (team strength -> Poisson goals conceded)
    saves                  (shrunk rate, GK only)
    defensive contribution (threshold model, negative binomial)
    bonus                  (damped - see caveat)

Points are assembled from components rather than regressed directly, because
FPL points are zero-inflated, threshold-laden and position-dependent. A single
regressor must learn all of that at once; components can each be swapped,
inspected and validated separately - and when FPL changes a rule, only the
affected component needs rebuilding.

Every projection carries its component breakdown so any number can be audited
back to source.

BONUS CAVEAT
------------
The 2026/27 BPS changed materially (CBI now 1 BPS per 3 rather than per 2;
being tackled no longer penalised; goalkeeper saves restructured). Historical
bonus rates are therefore MISCALIBRATED - centre-backs will earn less than
history implies, keepers and attackers more. Bonus enters at a damped weight
and is flagged. A rebuild from match components is a later job.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

import minutes as M
import rates as R

log = logging.getLogger("project")

POINTS_PER_GOAL = {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4}
POINTS_PER_CS = {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0}
ASSIST_POINTS = 3
BONUS_DAMPING = 0.6
LEAGUE_AVG_GOALS = 1.42


def _norm(s: str) -> str:
    import unicodedata
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().replace("-", " ").replace("'", "").split())


def availability_multiplier(el: Dict[str, Any]) -> float:
    status = (el.get("status") or "a").lower()
    if status in ("i", "s", "u", "n"):
        return 0.0
    chance = el.get("chance_of_playing_next_round")
    if chance is not None:
        try:
            return float(chance) / 100.0
        except (TypeError, ValueError):
            pass
    return 0.5 if status == "d" else 1.0


def team_cs_probability(bs, fixtures, gw) -> Dict[int, float]:
    """P(clean sheet) per team from FPL strength ratings via Poisson."""
    teams = {t["id"]: t for t in bs.get("teams", [])}
    if not teams:
        return {}
    avg_def = float(np.mean([t.get("strength_defence_home", 1000) or 1000
                             for t in teams.values()]))
    avg_att = float(np.mean([t.get("strength_attack_home", 1000) or 1000
                             for t in teams.values()]))
    out: Dict[int, float] = {}
    for f in fixtures:
        if f.get("event") != gw:
            continue
        h, a = f.get("team_h"), f.get("team_a")
        if h not in teams or a not in teams:
            continue
        a_att = (teams[a].get("strength_attack_away", avg_att) or avg_att) / avg_att
        h_def = (teams[h].get("strength_defence_home", avg_def) or avg_def) / avg_def
        h_att = (teams[h].get("strength_attack_home", avg_att) or avg_att) / avg_att
        a_def = (teams[a].get("strength_defence_away", avg_def) or avg_def) / avg_def
        xgc_h = float(np.clip(LEAGUE_AVG_GOALS * a_att / max(h_def, .5) * .92, .35, 3.2))
        xgc_a = float(np.clip(LEAGUE_AVG_GOALS * h_att / max(a_def, .5) * 1.08, .35, 3.2))
        out[h] = out.get(h, 0.0) + float(np.exp(-xgc_h))
        out[a] = out.get(a, 0.0) + float(np.exp(-xgc_a))
    return out


def build_projections(bs, fixtures, gw, hist, last_season="2025-26"):
    positions = {et["id"]: et.get("singular_name_short", "?")
                 for et in bs.get("element_types", [])}
    teams = {t["id"]: t.get("short_name", "?") for t in bs.get("teams", [])}

    cold = _cold_training_set(hist)
    mm = M.MinutesModel().fit(cold, cold["mins_bucket"])
    prev_agg = _aggregates_for(hist, last_season)

    rate_tbl = R.shrunk_rates(hist, last_season)
    rate_tbl = rate_tbl.set_index("pkey") if not rate_tbl.empty else pd.DataFrame()
    dc_tbl = R.defcon_action_rates(hist, last_season)
    dc_tbl = dc_tbl.set_index("pkey") if not dc_tbl.empty else pd.DataFrame()

    cs_prob = team_cs_probability(bs, fixtures, gw)

    fx_count: Dict[int, int] = {}
    for f in fixtures:
        if f.get("event") == gw:
            for k in ("team_h", "team_a"):
                fx_count[f[k]] = fx_count.get(f[k], 0) + 1

    rows = [{
        "element": el.get("id"),
        "pkey": _norm(f"{el.get('first_name','')} {el.get('second_name','')}"),
        "position": positions.get(el.get("element_type"), "?"),
        "price": (el.get("now_cost", 0) or 0) / 10.0,
    } for el in bs.get("elements", [])]

    feat = M.build_cold_features(pd.DataFrame(rows), prev_agg).reset_index(drop=True)
    dist_df = mm.predict_proba(feat).reset_index(drop=True)

    out: List[Dict[str, Any]] = []
    for i, el in enumerate(bs.get("elements", [])):
        pos = positions.get(el.get("element_type"), "?")
        team_id = el.get("team")
        n_fix = fx_count.get(team_id, 0)
        avail = availability_multiplier(el)

        dist = {b: float(dist_df.iloc[i][b]) for b in M.BUCKETS}
        if avail < 1.0:
            for b in ("sub", "partial", "full"):
                dist[b] *= avail
            dist["none"] = 1.0 - sum(dist[b] for b in ("sub", "partial", "full"))

        p_appear = dist["sub"] + dist["partial"] + dist["full"]
        p_60 = dist["partial"] + dist["full"]
        exp_min = sum(dist[b] * M.BUCKET_MINUTES[b] for b in M.BUCKETS)
        mins_share = exp_min / 90.0

        pk = feat.iloc[i]["pkey"]
        r = rate_tbl.loc[pk] if (not rate_tbl.empty and pk in rate_tbl.index) else None
        if r is not None and isinstance(r, pd.DataFrame):
            r = r.iloc[0]

        def rate(col):
            if r is None:
                return 0.0
            v = r.get(col, np.nan)
            return 0.0 if pd.isna(v) else float(v)

        pts_app = dist["sub"] * 1.0 + p_60 * 2.0
        pts_goals = rate("goals_scored_p90") * mins_share * POINTS_PER_GOAL.get(pos, 4)
        pts_assists = rate("assists_p90") * mins_share * ASSIST_POINTS
        team_cs = cs_prob.get(team_id, 0.25)
        pts_cs = team_cs * p_60 * POINTS_PER_CS.get(pos, 0)
        pts_saves = (rate("saves_p90") * mins_share / 3.0) if pos == "GKP" else 0.0

        p_dc = 0.0
        if pos in ("DEF", "MID", "FWD") and not dc_tbl.empty and pk in dc_tbl.index:
            d = dc_tbl.loc[pk]
            if isinstance(d, pd.DataFrame):
                d = d.iloc[0]
            col = "cbit_p90" if pos == "DEF" else "cbirt_p90"
            v = d.get(col, np.nan)
            if not pd.isna(v):
                p_dc = R.p_defcon(float(v), pos, dist)
        pts_dc = p_dc * 2.0

        pts_bonus = min(rate("bps_p90") * mins_share / 28.0, 1.2) * BONUS_DAMPING

        per_fix = (pts_app + pts_goals + pts_assists + pts_cs
                   + pts_saves + pts_dc + pts_bonus)
        total = per_fix * max(n_fix, 0)
        if avail == 0.0 or n_fix == 0:
            total = 0.0

        base_spread = {"GKP": .45, "DEF": .70, "MID": .95, "FWD": 1.05}.get(pos, .8)
        sd = max(total * base_spread * (1.0 + 0.6 * (1.0 - abs(2 * p_60 - 1))), 0.8)

        try:
            fpl_ep = float(el.get("ep_next") or 0)
        except (TypeError, ValueError):
            fpl_ep = 0.0

        k = max(n_fix, 0)
        out.append({
            "id": el.get("id"), "name": el.get("web_name"), "pos": pos,
            "team": teams.get(team_id, "?"), "team_id": team_id,
            "cost": (el.get("now_cost", 0) or 0) / 10.0,
            "fixtures": n_fix, "status": el.get("status"),
            "news": (el.get("news") or "").strip(),
            "chance": el.get("chance_of_playing_next_round"),
            "own": _f(el.get("selected_by_percent")),
            "xp": round(total, 2), "fpl_ep": round(fpl_ep, 2),
            "exp_minutes": round(exp_min, 1),
            "p_start": round(p_60, 3), "p_appear": round(p_appear, 3),
            "p_defcon": round(p_dc, 3), "team_cs": round(team_cs, 3),
            "is_new": int(feat.iloc[i]["is_new"]),
            "has_prior": int(feat.iloc[i]["is_new"]) == 0,
            "c_app": round(pts_app * k, 2), "c_goals": round(pts_goals * k, 2),
            "c_assists": round(pts_assists * k, 2), "c_cs": round(pts_cs * k, 2),
            "c_saves": round(pts_saves * k, 2), "c_defcon": round(pts_dc * k, 2),
            "c_bonus": round(pts_bonus * k, 2),
            "p10": round(max(0.0, total - 1.28 * sd), 1),
            "p90": round(total + 1.28 * sd, 1),
            "confidence": _confidence(feat.iloc[i], avail, p_60),
        })

    out.sort(key=lambda r: r["xp"], reverse=True)
    return out


def _cold_training_set(hist: pd.DataFrame) -> pd.DataFrame:
    seasons = sorted(hist["season"].unique())
    frames = []
    for s in seasons[1:]:
        d = hist[(hist["season"] == s) & (hist["GW"] == 1)].copy()
        if d.empty:
            continue
        d["price"] = d["value"] / 10.0
        rows = d[["pkey", "position", "price", "mins_bucket"]].dropna(subset=["position"])
        frames.append(M.build_cold_features(rows, M.prev_season_aggregates(hist, s)))
    return pd.concat(frames, ignore_index=True)


def _aggregates_for(hist: pd.DataFrame, season: str) -> pd.DataFrame:
    p = hist[hist["season"] == season]
    g = p.groupby("pkey").agg(
        prev_minutes=("minutes", "sum"),
        prev_starts=("starts", "sum"),
        prev_gws=("GW", "nunique"),
        prev_points=("total_points", "sum"),
    ).reset_index()
    g["prev_start_rate"] = g["prev_starts"] / g["prev_gws"].clip(lower=1)
    g["prev_mins_per_gw"] = g["prev_minutes"] / g["prev_gws"].clip(lower=1)
    g["prev_pts_per90"] = np.where(g["prev_minutes"] > 0,
                                   g["prev_points"] / g["prev_minutes"] * 90.0, 0.0)
    return g


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _confidence(row, avail: float, p_60: float) -> str:
    if avail == 0.0:
        return "n/a"
    if int(row["is_new"]) == 1:
        return "very low"
    if 0.3 < p_60 < 0.7:
        return "low"
    return "medium"
