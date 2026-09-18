#!/usr/bin/env python3
"""
Independent FPL model (v3.1) + multi-gameweek, chip-aware ILP transfer planner.

Why this exists
  * An independent cross-check of the main pipeline (src/project.py): different
    code, simpler assumptions. When the two disagree, that is information.
  * src/transfers.py scores ONE gameweek and has no chip logic. This planner
    optimises transfers over a horizon (default 6 GWs) and can evaluate a
    Bench Boost week.

Run from the repo root (PowerShell or bash):
  python tools/independent/plan.py --ft 1                  # live data, next GW
  python tools/independent/plan.py --ft 2 --max-transfers 3
  python tools/independent/plan.py --ft 1 --bb 7           # Bench Boost in GW7
  python tools/independent/plan.py --ft 1 --avail "Joao Pedro:CHE=0,0.35,0.9"
  python tools/independent/plan.py --ft 1 --cache DIR      # reuse a download

--avail takes per-GW availability multipliers starting at the next GW (the last
value repeats). Use it for news the FPL flag has not priced yet.

Only public, unauthenticated endpoints are used. The number of free transfers
is NOT in the public API: read it from the FPL app and pass --ft.
Requires: pulp (CBC).
"""
import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import json
import math
import os
import sys
import tempfile
import time
import unicodedata
import urllib.request

API = "https://fantasy.premierleague.com/api/"
UA = {"User-Agent": "Mozilla/5.0"}
POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
SQUAD_SHAPE = {1: 2, 2: 5, 3: 5, 4: 3}
XI_BOUNDS = {1: (1, 1), 2: (3, 5), 3: (2, 5), 4: (1, 3)}

# ---- model constants (v3.1, see README.md) --------------------------------
TEAM_SHRINK_K = 3.5        # matches at which a team rating is 50% own data
OPP_EXP = 0.85             # opponent-strength elasticity
HOME_ATT, AWAY_ATT = 1.08, 0.93
RATE_K = {"expected_goals": 300, "expected_assists": 300, "saves": 300,
          "bonus": 400, "defensive_contribution": 250}   # minutes for 50% weight
RECENT_W = [0.4, 0.6, 0.8, 1.0]   # last four matches, oldest -> newest
PRIOR_MATCHES = 0.6        # last-season minutes prior is worth 0.6 matches
BONUS_DAMP = 0.85
DEFCON_SLOPE = 0.75
DEFCON_THRESHOLD = {"DEF": 10, "MID": 12, "FWD": 12}   # 2026/27 rules
HORIZON_W = [1.0, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6]
BENCH_W = 0.1              # expected autosub value of a bench slot


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1 + i)


def load(cache, entry, league):
    os.makedirs(cache, exist_ok=True)

    def cached(name, fn):
        path = os.path.join(cache, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        data = fn()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data

    bs = cached("bs.json", lambda: get(API + "bootstrap-static/"))
    fx = cached("fx.json", lambda: get(API + "fixtures/"))

    def summaries():
        ids = [e["id"] for e in bs["elements"] if e["minutes"] > 0 or e["now_cost"] >= 55]
        with cf.ThreadPoolExecutor(10) as ex:
            got = list(ex.map(lambda i: get(f"{API}element-summary/{i}/"), ids))
        return {str(i): d for i, d in zip(ids, got)}

    es = cached("es.json", summaries)
    cur = next(e["id"] for e in bs["events"] if e["is_current"])

    def entries():
        ids = [entry]
        if league:
            lg = get(f"{API}leagues-classic/{league}/standings/")
            ids = [r["entry"] for r in lg["standings"]["results"]]
            if entry not in ids:
                ids.append(entry)
        return {str(e): {"hist": get(f"{API}entry/{e}/history/"),
                         "picks": get(f"{API}entry/{e}/event/{cur}/picks/"),
                         "entry": get(f"{API}entry/{e}/"),
                         "tr": get(f"{API}entry/{e}/transfers/")} for e in ids}

    legacy = os.path.join(cache, "league_entries.json")   # older cache layout
    if not os.path.exists(os.path.join(cache, "entries.json")) and os.path.exists(legacy):
        with open(legacy, encoding="utf-8") as f:
            le = json.load(f)
        for v in le.values():
            v.setdefault("picks", v.pop("p4", None))
    else:
        le = cached("entries.json", entries)
    return bs, fx, {int(k): v for k, v in es.items()}, le


def efloor(mu, d):
    """E[floor(X/d)] for X ~ Poisson(mu)."""
    if mu <= 0:
        return 0.0
    p, tot = math.exp(-mu), 0.0
    for k in range(1, 40):
        p *= mu / k
        tot += (k // d) * p
    return tot


def fold(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


class Model:
    def __init__(self, bs, fx, es, gws, overrides=None):
        self.S = bs["game_config"]["scoring"]
        self.E = {e["id"]: e for e in bs["elements"]}
        self.TM = {t["id"]: t["short_name"] for t in bs["teams"]}
        self.FX = {f["id"]: f for f in fx}
        self.es, self.gws, self.next_gw = es, gws, gws[0]
        self.override = overrides or {}
        y = int(bs["events"][0]["deadline_time"][:4])          # season start year
        self.last_season = f"{y - 1}/{str(y)[2:]}"
        self.prev_season = f"{y - 2}/{str(y - 1)[2:]}"
        self._team_ratings(fx)
        self.tf = collections.defaultdict(list)
        for f in fx:
            if f["event"] in gws:
                self.tf[(f["team_h"], f["event"])].append((f["team_a"], True))
                self.tf[(f["team_a"], f["event"])].append((f["team_h"], False))
        self.pp = {k: collections.defaultdict(list) for k in RATE_K}
        for pid, e in self.E.items():
            for k in RATE_K:
                r = self.prior(pid, k)
                if r is not None:
                    self.pp[k][e["element_type"]].append((e["now_cost"], r))
        self.mm, self.xp = {}, {}
        for pid in self.E:
            self._player(pid)

    # -- teams ---------------------------------------------------------------
    def _team_ratings(self, fx):
        txg = collections.defaultdict(float)
        for d in self.es.values():
            for h in d["history"]:
                f = self.FX.get(h["fixture"])
                if f is None:
                    continue
                t = f["team_h"] if h["was_home"] else f["team_a"]
                txg[(t, f["id"])] += float(h["expected_goals"] or 0)
        ts = collections.defaultdict(list)
        for f in fx:
            if not f["finished"]:
                continue
            h, a = f["team_h"], f["team_a"]
            ts[h].append((txg[(h, f["id"])], txg[(a, f["id"])]))
            ts[a].append((txg[(a, f["id"])], txg[(h, f["id"])]))
        allxg = [m[0] for v in ts.values() for m in v]
        self.lg = sum(allxg) / len(allxg) if allxg else 1.4
        self.att, self.dfn = {}, {}
        for t in self.TM:
            ms, n = ts[t], len(ts[t])
            a = sum(m[0] for m in ms) / n if n else self.lg
            d = sum(m[1] for m in ms) / n if n else self.lg
            self.att[t] = self.lg + (a - self.lg) * n / (n + TEAM_SHRINK_K)
            self.dfn[t] = self.lg + (d - self.lg) * n / (n + TEAM_SHRINK_K)

    def lam(self, t, o, home):
        return self.att[t] * (self.dfn[o] / self.lg) ** OPP_EXP * (HOME_ATT if home else AWAY_ATT)

    # -- players -------------------------------------------------------------
    def prior(self, pid, key):
        w = {self.last_season: 1.0}
        if key != "defensive_contribution":          # DefCon only exists from 2025/26
            w[self.prev_season] = 0.5
        num = den = 0.0
        for h in self.es.get(pid, {}).get("history_past", []):
            k = w.get(h["season_name"])
            if not k or h["minutes"] < 600 or h.get(key) is None:
                continue
            num += k * float(h[key])
            den += k * h["minutes"]
        return num / den * 90 if den else None

    def rate(self, pid, key):
        e, k = self.E[pid], RATE_K[key]
        m = e["minutes"]
        cur = float(e.get(key) or 0) / m * 90 if m > 0 else 0.0
        pr = self.prior(pid, key)
        if pr is None:                                # no PL history: price/position prior
            lst = self.pp[key][e["element_type"]]
            pr = 0.0
            for band in (7, 15, 999):
                v = [r for c, r in lst if abs(c - e["now_cost"]) <= band]
                if len(v) >= 3:
                    pr = sum(v) / len(v)
                    break
            pr *= 0.85
            k *= 0.5
        w = m / (m + k)
        return w * cur + (1 - w) * pr

    def minutes(self, pid):
        hist = self.es.get(pid, {}).get("history", [])
        rows = sorted((h for h in hist if self.FX.get(h["fixture"], {}).get("finished")),
                      key=lambda h: h["kickoff_time"])
        mins = [h["minutes"] for h in rows][-len(RECENT_W):]
        n = len(mins)
        rec = p60 = pap = 0.0
        if n:
            ws = RECENT_W[-n:]
            sw = sum(ws)
            rec = sum(w * m for w, m in zip(ws, mins)) / sw
            p60 = sum(w * (m >= 60) for w, m in zip(ws, mins)) / sw
            pap = sum(w * (m > 0) for w, m in zip(ws, mins)) / sw
        last = [h for h in self.es.get(pid, {}).get("history_past", [])
                if h["season_name"] == self.last_season]
        if last:
            pm, ps = min(last[0]["minutes"] / 38, 90), min(last[0]["starts"] / 38, 1.0)
            wc = n / (n + PRIOR_MATCHES)
            rec, p60 = wc * rec + (1 - wc) * pm, wc * p60 + (1 - wc) * ps
            pap = wc * pap + (1 - wc) * min(1.0, ps * 1.15)
        elif n:
            wc = n / (n + 0.5)
            rec, p60, pap = wc * rec + (1 - wc) * 30, wc * p60 + (1 - wc) * 0.3, wc * pap + (1 - wc) * 0.45
        else:
            rec, p60, pap = 5.0, 0.03, 0.08
        return rec, p60, pap, mins

    def avail(self, pid, gw):
        if pid in self.override:
            v = self.override[pid]
            return v[min(gw - self.next_gw, len(v) - 1)]
        e = self.E[pid]
        st, c = e["status"], e["chance_of_playing_next_round"]
        if st == "a":
            return 1.0
        if gw == self.next_gw:
            return c / 100 if c is not None else (0.75 if st == "d" else 0.0)
        if st == "d":
            return 0.95
        if st == "i":
            return 0.4 if gw == self.next_gw + 1 else 0.65
        if st == "s":
            return 0.5 if gw == self.next_gw + 1 else 1.0
        return 0.0

    def _player(self, pid):
        e, S = self.E[pid], self.S
        pos, t = POS[e["element_type"]], e["team"]
        rec, p60, pap, mins = self.minutes(pid)
        g90, a90, s90, b90, dc90 = (self.rate(pid, k) for k in RATE_K)
        self.mm[pid] = dict(xmin=rec, p60=p60, papp=pap, recent=mins, g90=g90, a90=a90,
                            s90=s90, b90=b90, dc90=dc90)
        self.xp[pid] = {}
        for gw in self.gws:
            av, tot = self.avail(pid, gw), 0.0
            for o, home in self.tf[(t, gw)]:
                mn, q60, qa = rec * av, p60 * av, pap * av
                lf, la = self.lam(t, o, home), self.lam(o, t, not home)
                r = lf / self.att[t]
                xg, xa = g90 * mn / 90 * r, a90 * mn / 90 * r
                pts = qa + q60 + xg * S["goals_scored"][pos] + xa * S["assists"]
                cs = q60 * math.exp(-la * 0.97)
                if pos in ("GKP", "DEF"):
                    pts += cs * S["clean_sheets"][pos] + S["goals_conceded"][pos] * efloor(la * mn / 90, 2)
                elif pos == "MID":
                    pts += cs * S["clean_sheets"]["MID"]
                if pos == "GKP":
                    pts += S["saves"] * efloor(s90 * mn / 90 * (la / self.lg) ** 0.6, 3)
                else:
                    z = (dc90 * 0.97 - DEFCON_THRESHOLD[pos]) * DEFCON_SLOPE
                    pts += q60 * S["defensive_contribution"][pos] / (1 + math.exp(-z))
                bf = (math.exp(-la) / math.exp(-self.lg)) ** 0.5 if pos in ("GKP", "DEF") else r ** 0.6
                pts += b90 * mn / 90 * bf * BONUS_DAMP
                tot += pts
            self.xp[pid][gw] = tot

    def resolve(self, key):
        if str(key).isdigit():
            return int(key)
        name, _, team = str(key).partition(":")
        hits = [p for p, e in self.E.items() if fold(e["web_name"]) == fold(name)
                and (not team or self.TM[e["team"]] == team.upper())]
        if len(hits) != 1:
            raise SystemExit(f"'{key}' matches {len(hits)} players; use NAME:TEAM or the element id")
        return hits[0]

    def label(self, p):
        return f"{self.E[p]['web_name']} ({self.TM[self.E[p]['team']]})"


def squad_state(le, entry, bs, es, next_gw):
    d, E = le[str(entry)], {e["id"]: e for e in bs["elements"]}
    picks = [p["element"] for p in d["picks"]["picks"]]
    bank = d["picks"]["entry_history"]["bank"]
    purchase = {}
    for t in sorted(d["tr"], key=lambda x: x["time"]):
        purchase[t["element_in"]] = t["element_in_cost"]
    pending = [t for t in d["tr"] if t["event"] == next_gw]   # confirmed, not yet in picks
    for t in sorted(pending, key=lambda x: x["time"]):
        if t["element_out"] in picks:
            picks[picks.index(t["element_out"])] = t["element_in"]
            bank += t["element_out_cost"] - t["element_in_cost"]

    def sell(p):
        now, pp = E[p]["now_cost"], purchase.get(p)
        if pp is None:                                       # initial squad
            h = sorted(es.get(p, {}).get("history", []), key=lambda x: x["round"])
            pp = h[0]["value"] if h else now
        return pp + (now - pp) // 2 if now > pp else now

    return picks, bank, {p: sell(p) for p in picks}, len(pending)


def solve(m, picks, bank, sell, ft, max_t, weights, bb_gw=None, force_in=(), force_out=(), min_h=9.0):
    import pulp
    E, XP, gws = m.E, m.xp, m.gws
    cand = sorted({p for p in E if p in picks or p in force_in or (
        E[p]["status"] not in ("u", "n") and sum(XP[p][g] * weights[g] for g in gws) >= min_h)})
    pr = pulp.LpProblem("fpl", pulp.LpMaximize)
    x = {p: pulp.LpVariable(f"x{p}", cat="Binary") for p in cand}
    s = {(p, g): pulp.LpVariable(f"s{p}_{g}", cat="Binary") for p in cand for g in gws}
    c = {(p, g): pulp.LpVariable(f"c{p}_{g}", cat="Binary") for p in cand for g in gws}
    hits = pulp.LpVariable("hits", lowBound=0)
    obj = []
    for p in cand:
        for g in gws:
            v = weights[g] * XP[p][g]
            obj.append(v * (x[p] + c[p, g]) if g == bb_gw
                       else v * (s[p, g] + c[p, g] + BENCH_W * (x[p] - s[p, g])))
    pr += pulp.lpSum(obj) - 4 * hits
    for et, n in SQUAD_SHAPE.items():
        pr += pulp.lpSum(x[p] for p in cand if E[p]["element_type"] == et) == n
    for t in m.TM:
        pr += pulp.lpSum(x[p] for p in cand if E[p]["team"] == t) <= 3
    pr += pulp.lpSum((sell[p] if p in picks else E[p]["now_cost"]) * x[p] for p in cand) <= bank + sum(sell.values())
    ntr = pulp.lpSum(x[p] for p in cand if p not in picks)
    pr += ntr <= max_t
    pr += hits >= ntr - ft
    for p in force_in:
        pr += x[p] == 1
    for p in force_out:
        pr += x[p] == 0
    for g in gws:
        pr += pulp.lpSum(s[p, g] for p in cand) == 11
        pr += pulp.lpSum(c[p, g] for p in cand) == 1
        for et, (lo, hi) in XI_BOUNDS.items():
            v = pulp.lpSum(s[p, g] for p in cand if E[p]["element_type"] == et)
            pr += v >= lo
            pr += v <= hi
        for p in cand:
            pr += s[p, g] <= x[p]
            pr += c[p, g] <= s[p, g]
    pr.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=120))
    sel = [p for p in cand if x[p].value() > 0.5]
    out, inn = [p for p in picks if p not in sel], [p for p in sel if p not in picks]
    spend = sum(E[p]["now_cost"] for p in inn) - sum(sell[p] for p in out)
    return dict(obj=pulp.value(pr.objective), squad=sel, out=out, inn=inn,
                xi={g: [p for p in cand if s[p, g].value() > 0.5] for g in gws},
                cap={g: next(p for p in cand if c[p, g].value() > 0.5) for g in gws},
                hits=round(hits.value() or 0), bank_after=bank - spend)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entry", type=int, default=5903925)
    ap.add_argument("--league", type=int, default=1649984, help="0 to skip rival ownership")
    ap.add_argument("--ft", type=int, required=True, help="free transfers, from the FPL app")
    ap.add_argument("--max-transfers", type=int, default=None, help="default: ft + 1")
    ap.add_argument("--horizon", type=int, default=6)
    ap.add_argument("--bb", type=int, default=None, help="GW in which to play Bench Boost")
    ap.add_argument("--avail", action="append", default=[], help='"NAME[:TEAM]=a1,a2,..." or "ID=..."')
    ap.add_argument("--force-in", action="append", default=[])
    ap.add_argument("--force-out", action="append", default=[])
    ap.add_argument("--cache", default=None, help="data dir; reused if it already holds a download")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    cache = a.cache or os.path.join(tempfile.gettempdir(), "fpl-indep",
                                    dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%MZ"))
    bs, fx, es, le = load(cache, a.entry, a.league)
    nxt = next(e for e in bs["events"] if e["is_next"])
    gws = [g for g in range(nxt["id"], nxt["id"] + a.horizon) if g <= 38]
    weights = {g: HORIZON_W[min(i, len(HORIZON_W) - 1)] for i, g in enumerate(gws)}

    probe = Model.__new__(Model)                              # resolve names before building
    probe.E = {e["id"]: e for e in bs["elements"]}
    probe.TM = {t["id"]: t["short_name"] for t in bs["teams"]}
    overrides = {}
    for spec in a.avail:
        k, _, v = spec.partition("=")
        overrides[Model.resolve(probe, k.strip())] = [float(x) for x in v.split(",")]
    m = Model(bs, fx, es, gws, overrides)
    fin = [m.resolve(k) for k in a.force_in]
    fout = [m.resolve(k) for k in a.force_out]
    picks, bank, sell, pending = squad_state(le, a.entry, bs, es, nxt["id"])
    max_t = a.max_transfers if a.max_transfers is not None else a.ft + 1

    def wsum(p):
        return sum(m.xp[p][g] * weights[g] for g in gws)

    print(f"# Independent model v3.1 - GW{gws[0]}-GW{gws[-1]}")
    print(f"Data: `{cache}` | deadline GW{nxt['id']}: {nxt['deadline_time']} | league xG/match {m.lg:.2f}")
    print(f"Bank GBP{bank / 10:.1f}m | FT {a.ft} | pending transfers already applied: {pending}"
          + (f" | Bench Boost in GW{a.bb}" if a.bb else "") + "\n")
    print("## Current squad\n")
    print("| Player | Pos | Sell | Status | xMin | P60 | " + " | ".join(f"GW{g}" for g in gws) + " | Wtd |")
    print("|---|---|--:|---|--:|--:|" + "--:|" * len(gws) + "--:|")
    for p in sorted(picks, key=lambda p: (m.E[p]["element_type"], -wsum(p))):
        e, mm = m.E[p], m.mm[p]
        st = e["status"] + (f" {e['chance_of_playing_next_round']}%" if e["status"] != "a" else "")
        print(f"| {m.label(p)} | {POS[e['element_type']]} | {sell[p] / 10:.1f} | {st} | {mm['xmin']:.0f} | "
              f"{mm['p60']:.2f} | " + " | ".join(f"{m.xp[p][g]:.1f}" for g in gws) + f" | {wsum(p):.1f} |")

    print("\n## Options (objective = weighted horizon xP, bench x0.1, hits -4)\n")
    print("| Transfers | Objective | Out -> In | Hits | Bank after |")
    print("|--:|--:|---|--:|--:|")
    best = None
    for k in range(0, max_t + 1):
        r = solve(m, picks, bank, sell, a.ft, k, weights, a.bb, fin, fout)
        mv = ", ".join(f"{m.label(o)} -> {m.label(i)}" for o, i in zip(
            sorted(r["out"], key=lambda p: m.E[p]["element_type"]),
            sorted(r["inn"], key=lambda p: m.E[p]["element_type"]))) or "-"
        print(f"| {k} | {r['obj']:.2f} | {mv} | {r['hits']} | {r['bank_after'] / 10:.1f} |")
        if best is None or r["obj"] > best["obj"] + 1e-6:
            best = r
    print("\n## Best plan: captain and XI by GW\n")
    for g in gws:
        xi, cap = best["xi"][g], best["cap"][g]
        bench = [p for p in best["squad"] if p not in xi]
        tot = sum(m.xp[p][g] for p in xi) + m.xp[cap][g]
        if g == a.bb:
            tot += sum(m.xp[p][g] for p in bench)
        top = sorted(best["squad"] if g == a.bb else xi, key=lambda p: -m.xp[p][g])[:3]
        print(f"- GW{g}: {tot:.1f} xP | C {m.label(cap)} {m.xp[cap][g]:.2f} | next: "
              + ", ".join(f"{m.label(p)} {m.xp[p][g]:.2f}" for p in top if p != cap)
              + (" | Bench Boost: all 15 score" if g == a.bb
                 else f" | bench {', '.join(m.E[p]['web_name'] for p in bench)}"))

    if a.league and len(le) > 1:
        own = collections.Counter()
        for eid, d in le.items():
            if int(eid) != a.entry and d.get("picks"):
                own.update(p["element"] for p in d["picks"]["picks"])
        rivals = len(le) - 1
        print(f"\n## Rival ownership ({rivals} rivals, last deadline)\n")
        for p, n in own.most_common(15):
            flag = "owned" if p in best["squad"] else "NOT owned"
            print(f"- {m.label(p)}: {n}/{rivals} ({flag}) GW{gws[0]} xP {m.xp[p][gws[0]]:.2f}")


if __name__ == "__main__":
    main()
