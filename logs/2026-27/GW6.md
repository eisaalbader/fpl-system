# Prediction Log — Gameweek 6, 2026/27

**Deadline:** Sat 10 Oct 2026, 10:00 UTC (13:00 Kuwait)
**Decision:** Eisa picked option 1 (Bruno captain) at 04:25 Kuwait / 01:25 UTC
**Executed on the live account:** saved in Chrome, then verified via `/api/my-team` after a page reload; clock read 01:30:37 UTC immediately afterwards
**Data timestamp:** 01:16–01:20 UTC 10 Oct (bootstrap-static, fixtures, element summaries, entry, league and my-team endpoints, pulled from the PC)
**Models:** independent v3.1 (`tools/independent/plan.py --ft 1 --max-transfers 2`) as primary; repo model (`src/report.py`, run locally on the PC because the CI report job is broken) as cross-check

---

## What was executed

| | |
|---|---|
| Transfers | **None.** 1 FT rolled, so 2 FT for GW7 |
| Chip | None |
| Captain / vice | **B.Fernandes** / Haaland |
| XI (3-5-2) | Trafford · Guéhi, Tarkowski, Thomas · Le Fée, Janelt, Tavernier, Mbeumo, B.Fernandes · Haaland, Barry |
| Bench | Scherpen (GK) → De Cuyper → Calvert-Lewin → Muharemović |
| Money | Bank £0.1m; selling value £99.1m (market value £99.6m) |

## Decisions and evidence

### Transfers: roll
- Independent (GW6–11 weighted objective, bench ×0.1): 0 transfers **314.89**; best single move Guéhi → Mukiele (SUN £5.4m) **316.88 (+1.99)**; a second transfer added nothing.
- Repo (single GW): Muharemović → Van Hecke (TOT £4.9m), **+0.42**.
- The models picked different defenders to sell, so neither move is robust. Both gains are at or below the value of a rolled FT (~1.5–2.5). Rolled, giving 2 FT for GW7: João Pedro re-buy (7/8 rivals own him) or a keeper (Scherpen played 0 mins in GW5).
- Confidence: medium.

### Captain: B.Fernandes (vice Haaland)

| Player | Fixture | Indep xP | Repo xP | Repo p10 / p90 | Rivals who captained him in GW5 |
|---|---|--:|--:|--:|--:|
| **B.Fernandes** | TOT (H) | **6.35** | 5.87 | 0.0 / 13.1 | 0/8 |
| Mbeumo | TOT (H) | 6.18 | 5.27 | — | 0/8 |
| Haaland | LIV (A) | 6.09 | **5.98** | 0.0 / 14.2 | 6/8 |

- On expected points it is a tie across the two models (average Bruno 6.11, Haaland 6.04).
- Tie-break: league position (7th, 66 behind). All 8 rivals own Haaland and 6/8 captained him in GW5, so Bruno is the differential at no EV cost.
- Confidence: **low** — a coin flip on EV. The decision rests on game theory.

### Lineup
- Both models start Le Fée and Janelt and bench Muharemović (Leeds are at Arsenal).
- The models disagree on Thomas vs De Cuyper (indep 4.5 / 3.9; repo 3.59 / 3.91) and on Barry vs Calvert-Lewin (indep 4.3 / 3.9; repo 3.81 / 3.98). Went with the primary model.
- Bench order: De Cuyper first because he covers a defender absence in a 3-defender shape; then Calvert-Lewin; then Muharemović.

### Chips
- None played. TC → Haaland GW7 v IPS (H), 7.65 indep, the best TC slot. Fallbacks: GW11 (7.58) or GW9 v BHA (H) (7.54).
- FH is held as insurance. Set 1 expires at the GW19 deadline (Fri 1 Jan 2027 18:30 UTC).

## News check (source tier in brackets)
- **Bruno, hip (highly credible: Portugal coach Jorge Jesus, via Sports Mole, World Soccer Talk and BBC syndication).** He played through pain v Wales (24 Sep) and sat out Norway (27 Sep). He then started v Denmark (1 Oct, 2 assists) and played v Norway (4 Oct, booked late). FPL flag is `a` after the Friday press conferences. Treated as fit, with residual risk. His GW3–5 returns (2, 2, 2) line up with the period he was carrying the knock.
- **Haaland:** no club or Norway injury news; flag `a`. Squawka preview: MCI 5/5 wins, Haaland 5 goals.
- **Tarkowski and Barry** (EVE @ HUL): predicted starters (Squawka; The Stats Zone). EVE are without Röhl; Nørgaard and Mykolenko are doubts.
- **Le Fée** (SUN v BHA): expected to start (Squawka). SUN have Brobbey doubtful (thigh) and Ballard hurt (hamstring, NI duty).
- **Janelt** (BRE @ AVL): set to feature (Squawka).
- **Tavernier** (BOU @ CHE): fit. BOU are without Kluivert, Kroupi, Araujo, Milosavljević and Adli (Squawka).
- **Thomas** (COV v NEW, Monday): not on the COV absence list. That list has Amenda, Eccles, Kesler-Hayden, Woolfenden and Wright out, and Onyeka doubtful (starting11).
- **Calvert-Lewin:** fit to lead the line (Squawka). LEE are without Joseph, Rodon and Wilson.
- **Rotation:** MUN play Atlético (UCL) on Tue 13 Oct and ARS also play UCL midweek, a minor rotation risk.

## GW6 per-player projections (for error analysis)

| Player | Pos | Fixture | Indep xP | Repo xP | xMin | P60 |
|---|---|---|--:|--:|--:|--:|
| Trafford | GK | ARS (A) | 3.3 | 4.22 | 79 | 0.88 |
| Guéhi | DEF | LIV (A) | 3.7 | 4.54 | 89 | 0.99 |
| Tarkowski | DEF | HUL (A) | 4.8 | 4.95 | 90 | 1.00 |
| Thomas (COV) | DEF | NEW (H) | 4.5 | 3.59 | 82 | 0.92 |
| Le Fée | MID | BHA (H) | 5.1 | 4.42 | 88 | 0.98 |
| Janelt | MID | AVL (A) | 4.1 | 3.95 | 83 | 0.92 |
| Tavernier | MID | CHE (A) | 5.1 | 4.56 | 80 | 0.98 |
| Mbeumo | MID | TOT (H) | 6.18 | 5.27 | 87 | 0.98 |
| B.Fernandes (C) | MID | TOT (H) | 6.35 | 5.87 | 89 | 0.99 |
| Haaland (V) | FWD | LIV (A) | 6.09 | 5.98 | 88 | 0.99 |
| Barry | FWD | HUL (A) | 4.3 | 3.81 | 82 | 0.94 |
| Scherpen | GK | FUL (H) | 1.7 | 3.20 | 50 | 0.56 |
| De Cuyper | DEF | SUN (A) | 3.9 | 3.91 | 80 | 0.93 |
| Calvert-Lewin | FWD | ARS (A) | 3.9 | 3.98 | 81 | 0.97 |
| Muharemović | DEF | ARS (A) | 3.5 | 3.32 | 83 | 0.92 |

XI projection with the captain counted: **≈60.5** independent (planner) and **≈57.0** repo, for this XI.

---

## GW5 post-mortem
- Scored **83** (average 48, highest 126), the best score in the league that week (rivals 25–75). Overall rank 6.87M → 3.73M. League position 8th → 7th; 66 behind AMG.
- The projection was ~78 and the actual was 83 (15 players 77, plus 6 for the captain).
- Per player, actual (projected): Trafford 10 (3.37) · Muharemović 6 (4.09) · Guéhi 4 (5.03) · De Cuyper 6 (4.21) · Tarkowski 14 (4.47) · Tavernier 2 (5.60) · Mbeumo 2 (6.05) · Bruno 2 (6.25) · Haaland 6 (7.11) · Calvert-Lewin 2 (5.31) · Barry 6 (4.91) · Scherpen 0 (2.71, 0 mins) · Janelt 3 (4.34) · Thomas 9 (3.18) · Le Fée 5 (4.22).
- Pattern: GK and defenders came in about 27 over projection; attackers about 19 under. One GW, so no model change.
- **João Pedro played 0 mins v BRE**, which validates acting on ESPN over the 75% flag. 7/8 rivals carried his 0.
- **Bench Boost** realised 17 (Scherpen 0, Janelt 3, Thomas 9, Le Fée 5) vs ~13.3 projected.
- **Captain:** Haaland 6 (×2) vs Bruno 2 and Mbeumo 2, so the right call.
- **FT check:** `my-team.transfers.limit` = 1 for GW6, as predicted.
- **Rival GW5 captains:** Haaland ×6 (z3Tor with TC), Gibbs-White (KDD), Gyökeres (SOC). Nobody sold João Pedro before the deadline.
- **Minutes-model miss:** Scherpen was projected 78 xMin and played 0. His xMin is now 50.

## Biggest risks this week
1. Bruno's hip: a recurrence, or an early sub with the UCL game on Tuesday. Haaland as vice only covers a full non-appearance.
2. The captaincy is a coin flip against most of the league: a Haaland haul at Anfield costs relative points.
3. Three defenders and the keeper are away (Guéhi @ LIV, Tarkowski @ HUL, Trafford @ ARS).
4. The models disagree on Thomas/De Cuyper and Barry/Calvert-Lewin; the stakes are small.

## To check after GW6
1. Every player's actual points against the table above.
2. Captain counterfactual: Bruno vs Haaland vs Mbeumo.
3. Bruno's minutes: did the hip hold for 90?
4. Did Scherpen play? If not, the backup keeper becomes a GW7 transfer target.
5. Which model was right on Thomas vs De Cuyper and Barry vs Calvert-Lewin.
6. Rival GW6 captains and chips, and who bought or sold João Pedro.

**Do not revise the model on one gameweek of results.**

## Infrastructure notes (10 Oct)
- `report.yml` has failed every scheduled run since 25 Sep (runs 21–28) at the "Build report" step. The same code and data (an archive of origin/main) build fine on the PC (Python 3.14, pandas 3.0.5, scikit-learn 1.9.1, pyarrow 26), so the fault is in the CI environment, not the model. The job logs need a signed-in GitHub view to diagnose.
- **Budget rule correction:** `my-team.transfers.value` (99.6) is the squad's *market* value. The budget is `sum(picks[].selling_price) + bank` (99.1 + 0.1 = 99.2). This supersedes the GW4 rule "budget from my-team.transfers.value".

**Update 16 Oct:** cause found. CI installs the newest PuLP on every run (`pulp>=2.7` was unpinned); PuLP 4.0.1 dropped `LpVariable(cat=...)` and the bundled CBC solver, so `squad.optimise` crashed with a `TypeError` (the PC still had PuLP 3, which is why local builds passed). Fixed by pinning `pulp>=2.7,<4`.
