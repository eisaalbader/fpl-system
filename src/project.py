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

# --- current-season blending -------------------------------------------------
# The cold minutes model is trained on GW1 rows of past seasons and keyed on
# LAST season's aggregates, so from GW3 onward it is the weakest thing we know
# about a player who has started every week. Treat it as a prior worth this
# many pseudo-matches and let observed starts take over.
MINUTES_PRIOR_GAMES = 2.0
# Historical per-90 rates are worth this many minutes of current-season
# evidence. At 270 minutes played, this season carries ~40% of the weight.
RATE_PRIOR_MINUTES = 400.0
# Team attack/defence are shrunk toward the league mean by this many matches.
TEAM_PRIOR_MATCHES = 3.0


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


def team_match_counts(fixtures) -> Dict[int, int]:
    """Finished matches per team, so "this season so far" means the same thing
    for a club that has had a postponement as for one that has not."""
    played: Dict[int, int] = {}
    for f in fixtures:
        if f.get("finished"):
            for k in ("team_h", "team_a"):
                if f.get(k) is not None:
                    played[f[k]] = played.get(f[k], 0) + 1
    return played


def team_strengths(bs, fixtures) -> Dict[str, Any]:
    """
    Per-team attack and defence rates for the CURRENT season, shrunk toward the
    league mean.

    WHY THIS REPLACED THE strength_* FIELDS
    ---------------------------------------
    The previous implementation read strength_attack_home / strength_defence_home
    from bootstrap. In 2026/27 the API returns 0 for all four of those fields.
    The "or avg" fallbacks then resolved every ratio to exactly 1.0, so every
    club got an identical clean-sheet probability - Arsenal and Ipswich scored
    the same. It failed silently, which is worse than failing loudly.

    Strength now comes from the season's own numbers: attack from summed player
    expected_goals; defence from expected_goals_conceded carried by a
    near-ever-present player, since that column accumulates only while the
    player is on the pitch, so a full-time starter's total IS the team's.
    Actual goals conceded from finished fixtures is the fallback.
    """
    teams = {t["id"]: t for t in bs.get("teams", [])}
    played = team_match_counts(fixtures)

    xgf = {tid: 0.0 for tid in teams}
    xga_best = {tid: (0.0, 0.0) for tid in teams}      # (minutes, xgc)
    for el in bs.get("elements", []):
        tid = el.get("team")
        if tid not in teams:
            continue
        xgf[tid] += _f(el.get("expected_goals"))
        m = _f(el.get("minutes"))
        if m > xga_best[tid][0]:
            xga_best[tid] = (m, _f(el.get("expected_goals_conceded")))

    ga_actual = {tid: 0.0 for tid in teams}
    for f in fixtures:
        if not f.get("finished"):
            continue
        h, a_ = f.get("team_h"), f.get("team_a")
        hs, as_ = f.get("team_h_score"), f.get("team_a_score")
        if h in ga_actual and as_ is not None:
            ga_actual[h] += float(as_)
        if a_ in ga_actual and hs is not None:
            ga_actual[a_] += float(hs)

    att, dfn = {}, {}
    for tid in teams:
        n = max(played.get(tid, 0), 0)
        if n == 0:
            att[tid] = dfn[tid] = LEAGUE_AVG_GOALS
            continue
        att[tid] = xgf[tid] / n
        mins, xgc = xga_best[tid]
        if mins >= 0.75 * 90.0 * n and xgc > 0:
            dfn[tid] = xgc / n
        else:
            dfn[tid] = ga_actual[tid] / n

    if not teams:
        return {"att": {}, "def": {}, "league_att": LEAGUE_AVG_GOALS,
                "league_def": LEAGUE_AVG_GOALS, "played": played}

    la = float(np.mean([att[t] for t in teams]))
    ld = float(np.mean([dfn[t] for t in teams]))
    if la <= 0 or ld <= 0:
        log.warning("team strength degenerate (att=%.3f def=%.3f) - falling "
                    "back to league average; clean sheets will be flat", la, ld)
        la = la if la > 0 else LEAGUE_AVG_GOALS
        ld = ld if ld > 0 else LEAGUE_AVG_GOALS

    K = TEAM_PRIOR_MATCHES
    for tid in teams:
        n = max(played.get(tid, 0), 0)
        w = n / (n + K)
        att[tid] = w * att[tid] + (1 - w) * la
        dfn[tid] = w * dfn[tid] + (1 - w) * ld

    return {"att": att, "def": dfn, "league_att": la, "league_def": ld,
            "played": played}


def team_cs_probability(bs, fixtures, gw, strengths=None) -> Dict[int, float]:
    """Expected clean sheets per team in the gameweek, summed over fixtures so a
    double gameweek correctly yields more than one."""
    teams = {t["id"]: t for t in bs.get("teams", [])}
    if not teams:
        return {}
    st = strengths or team_strengths(bs, fixtures)
    att, dfn = st["att"], st["def"]
    la, ld = max(st["league_att"], 1e-6), max(st["league_def"], 1e-6)

    out: Dict[int, float] = {}
    for f in fixtures:
        if f.get("event") != gw:
            continue
        h, a_ = f.get("team_h"), f.get("team_a")
        if h not in teams or a_ not in teams:
            continue
        xgc_h = float(np.clip(
            LEAGUE_AVG_GOALS * (att[a_] / la) * (dfn[h] / ld) * 0.92, 0.20, 3.5))
        xgc_a = float(np.clip(
            LEAGUE_AVG_GOALS * (att[h] / la) * (dfn[a_] / ld) * 1.08, 0.20, 3.5))
        out[h] = out.get(h, 0.0) + float(np.exp(-xgc_h))
        out[a_] = out.get(a_, 0.0) + float(np.exp(-xgc_a))
    return out


def blend_current_minutes(dist: Dict[str, float], el: Dict[str, Any],
                          games: int, prev_minutes: float = None) -> Dict[str, float]:
    """
    Beta-binomial update of the cold model's bucket distribution using this
    season's observed starts and minutes.

    The cold model cannot know that a player who missed most of last season has
    started every game of this one - it is keyed on last season's aggregates
    and price. Observed starts should dominate from roughly GW3, which is
    exactly the point at which the previous code kept trusting the prior alone.
    """
    if games <= 0:
        return dist
    mins = _f(el.get("minutes"))
    starts = min(_f(el.get("starts")), float(games))

    # The prior deserves only as much weight as the evidence behind it. A
    # forward who managed 694 minutes last season through injury tells us far
    # less about this season than one who played 3,000, and a new signing tells
    # us nothing at all - so their priors must yield to observed starts much
    # faster. Without this, anyone with a disrupted previous season stays stuck
    # near the cold model's guess no matter how many games he starts.
    K = MINUTES_PRIOR_GAMES
    if prev_minutes is not None:
        K *= float(np.clip(_f(prev_minutes) / 1500.0, 0.25, 1.0))

    p60_prior = dist["partial"] + dist["full"]
    exp_prior = sum(dist[bk] * M.BUCKET_MINUTES[bk] for bk in M.BUCKETS)

    # Starting is not the same as clearing the 60-minute gate. A striker hooked
    # on the hour three weeks running has started every game but earned the
    # second appearance point roughly once, and was ineligible for a clean
    # sheet the rest of the time. Discount starts by how long they actually
    # last instead of counting each one whole.
    mws = (mins / starts) if starts > 0 else 0.0
    starts_60 = starts * float(np.clip((mws - 45.0) / 30.0, 0.0, 1.0))

    p60 = (starts_60 + K * p60_prior) / (games + K)
    exp_min = (mins + K * exp_prior) / (games + K)
    full_share = (0.85 if mws >= 87 else 0.65 if mws >= 80
                  else 0.45 if mws >= 70 else 0.35)
    full = p60 * full_share
    partial = p60 - full
    rest = max(0.0, 1.0 - p60)
    sub_minutes = max(
        0.0, exp_min - (full * 90.0 + partial * M.BUCKET_MINUTES["partial"]))
    sub = min(rest, sub_minutes / M.BUCKET_MINUTES["sub"])
    none = max(0.0, rest - sub)

    out = {"none": none, "sub": sub, "partial": partial, "full": full}
    s = sum(out.values())
    return {k: v / s for k, v in out.items()} if s > 0 else dist


def blend_rate(hist_p90: float, cur_total: float, cur_minutes: float) -> float:
    """
    Blend a historical per-90 rate with this season's observed rate.

    The weight is minutes-based: 270 minutes carries about 40% current-season
    weight, 900 minutes about 69%. Attacking input uses expected goals/assists
    rather than actual, because three gameweeks of finishing is noise.
    """
    if cur_minutes <= 0:
        return hist_p90
    cur_p90 = cur_total / cur_minutes * 90.0
    w = cur_minutes / (cur_minutes + RATE_PRIOR_MINUTES)
    return w * cur_p90 + (1.0 - w) * hist_p90


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

    strengths = team_strengths(bs, fixtures)
    cs_prob = team_cs_probability(bs, fixtures, gw, strengths)
    played = strengths["played"]

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

        cur_min = _f(el.get("minutes"))
        dist = {b: float(dist_df.iloc[i][b]) for b in M.BUCKETS}
        dist = blend_current_minutes(dist, el, int(played.get(team_id, 0)),
                                     feat.iloc[i].get("prev_minutes"))
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
        g90 = blend_rate(rate("goals_scored_p90"),
                         _f(el.get("expected_goals")), cur_min)
        a90 = blend_rate(rate("assists_p90"),
                         _f(el.get("expected_assists")), cur_min)
        pts_goals = g90 * mins_share * POINTS_PER_GOAL.get(pos, 4)
        pts_assists = a90 * mins_share * ASSIST_POINTS
        team_cs = cs_prob.get(team_id, 0.25)
        pts_cs = team_cs * p_60 * POINTS_PER_CS.get(pos, 0)
        pts_saves = ((blend_rate(rate("saves_p90"), _f(el.get("saves")), cur_min)
                      * mins_share / 3.0) if pos == "GKP" else 0.0)

        p_dc = 0.0
        if pos in ("DEF", "MID", "FWD") and not dc_tbl.empty and pk in dc_tbl.index:
            d = dc_tbl.loc[pk]
            if isinstance(d, pd.DataFrame):
                d = d.iloc[0]
            col = "cbit_p90" if pos == "DEF" else "cbirt_p90"
            v = d.get(col, np.nan)
            if not pd.isna(v):
                v = blend_rate(float(v),
                               _f(el.get("defensive_contribution")), cur_min)
                p_dc = R.p_defcon(float(v), pos, dist)
        pts_dc = p_dc * 2.0

        bps90 = blend_rate(rate("bps_p90"), _f(el.get("bps")), cur_min)
        pts_bonus = min(bps90 * mins_share / 28.0, 1.2) * BONUS_DAMPING

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
