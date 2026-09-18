# GW5 decision log - 2026/27

**Deadline:** Fri 18 Sep 2026, 17:30 UTC (Friday game, BRE v CHE) | **Executed:** ~16:48 UTC in Chrome, verified after a page reload | **Data:** FPL API pulled 16:13 UTC (bootstrap, fixtures, 433 element summaries, all 9 league entries)
**Models:** independent v3.1 (`tools/independent/plan.py`, added in this PR) as primary; the repo GW5 report (13:23 UTC) as cross-check.

## Executed

| | |
|---|---|
| Transfers (3 FT, 0 hit) | White -> Tarkowski, João Pedro -> Calvert-Lewin, G. Hemmings -> Le Fée |
| Chip | Bench Boost (first set) |
| Captain / vice | Haaland / B.Fernandes |
| Bank after | £0.1m (squad value £99.5m) |
| Free transfers for GW6 | 1 |

Projection (v3.1): all 15 players 70.9 xP + captain 7.1 = **~78 xP**. Doing nothing (João Pedro injured, Bruno still captain, no chip) was ~60.

## Why

- **João Pedro.** FPL flag said 75% "unspecified injury". ESPN (18 Sep) reported a knee ligament injury, ~3.5 weeks out, unavailable vs Brentford. Modelled availability 0 / 0.37 / 0.9 for GW5 / GW6 / GW7+. 7 of 8 rivals own him.
- **Options** (Bench Boost in GW5, weighted GW5-10 objective): 0 transfers 317.9 | 1: 324.0 (JP -> Thiago) | 2: 330.4 (JP -> Calvert-Lewin, Hemmings -> Le Fée) | **3: 335.0** (+ White -> Tarkowski). Each move was worth more than a rolled free transfer.
- **Bench Boost now.** After the GW4 wildcard all 15 are nailed starters, so the bench is worth ~13-14 xP this week - about what any later set-1 week offers (no doubles before GW19) - and spending it now frees future transfers for the XI.
- **Captain.** Haaland 7.11 (SUN H) > B.Fernandes 6.25 (FUL A) > Mbeumo 6.05. 8/8 rivals own Haaland; no reason to oppose him with a lower-EV pick.
- **Repo report disagreed** (1 transfer, White -> Murillo): single-GW horizon, no chip logic, João Pedro still at 75%, and it counted 4 free transfers (the app showed 3 - fixed below).
- **Team news checked:** Tarkowski predicted to start (Sports Mole), Calvert-Lewin fit and in the England squad (Farke presser), Le Fée 79+ minutes in all four games.

## GW5 projections (for error analysis)

| Player | xP | xMin | | Player | xP | xMin |
|---|--:|--:|---|---|--:|--:|
| Trafford | 3.37 | 79 | | Mbeumo | 6.05 | 87 |
| Muharemović | 4.09 | 83 | | B.Fernandes (V) | 6.25 | 89 |
| Guéhi | 5.03 | 89 | | Haaland (C) | 7.11 | 88 |
| De Cuyper | 4.21 | 78 | | Calvert-Lewin | 5.31 | 79 |
| Tarkowski | 4.47 | 90 | | Barry | 4.91 | 79 |
| Tavernier | 5.60 | 85 | | Scherpen | 2.71 | 78 |
| Janelt | 4.34 | 83 | | Thomas (COV) | 3.18 | 81 |
| Le Fée | 4.22 | 87 | | | | |

## GW4 post-mortem

- Scored **65** (global average 69; rivals 72-97). The XI projection was ~50, so the squad beat its projection - the loss was relative, not absolute.
- **Captaincy was the gap.** Bruno 2 x2 = 4. Haaland scored 9 and João Pedro 12 - we owned both. 4/8 rivals captained João Pedro (24), 2/8 Haaland (18). That explains ~15-20 points of the shortfall. Both models had Bruno top (6.10-6.13 xP vs Haaland 5.81) and MUN lost 0-1 to MCI. One gameweek: no model change.
- Per player: Trafford 3, Muharemović 7, Guéhi 6, De Cuyper 11, White 1 (45'), Tavernier 8, Mbeumo 2, B.Fernandes 2, Haaland 9, João Pedro 12, Barry 2 | bench Scherpen 1, Janelt 4, Thomas 0, Hemmings 1 (45').
- **Hull test:** conceded 2 at Chelsea after three clean sheets - the xG view holds; keep avoiding Hull defenders.
- **Arsenal test:** clean sheet at Sunderland but 1.80 xG allowed (after 0.20 / 0.33 / 0.39) - regressing as the shrinkage expected.
- **Minutes model:** the two lowest-P60 picks (White, Hemmings) both played 45'. Both sold in GW5.
- **Repo vs independent DEF pick:** Gabriel 9, White 1. One week - noted, not acted on.
- AMG +32 and z3Tor +22 on us in GW4.

## League after GW4 (الوردات, 1649984)

| # | Team | Pts | Set-1 chips used |
|--:|---|--:|---|
| 1 | AMG | 325 | BB GW1, TC GW3 |
| 2 | z3Tor | 314 | BB GW2 |
| 3 | aam22 | 292 | - |
| 4 | bo khaled | 276 | - |
| 5 | KDD | 275 | BB GW1, TC GW3 |
| 6 | Bokhalifa | 255 | - |
| 7 | Poison FC | 240 | FH GW4 |
| 8 | **eisa** | 225 | WC GW4, BB GW5 |
| 9 | SOC | 196 | - |

## Plan GW6-GW10

| GW | Deadline (Kuwait) | Captain (xP) | Chip | Transfers |
|--:|---|---|---|---|
| 6 | Sat 10 Oct, 13:00 | B.Fernandes v TOT (H) 6.8 | - | 1 FT: only for international-break injuries, else roll |
| 7 | Sat 17 Oct, 13:00 | Haaland v IPS (H) 7.6 | **Triple Captain** | up to 2 FT |
| 8 | Fri 23 Oct, 20:30 | Haaland at AVL 7.0 | - | |
| 9 | Sat 31 Oct, 14:00 | Haaland v BHA (H) 7.6 | TC fallback | |
| 10 | Sat 7 Nov, 16:30 | B.Fernandes v AVL (H) 7.0 | - | |

- **Free Hit:** insurance for an injury-wrecked week. Must be used by the GW19 deadline (Fri 1 Jan 2027, 21:30 Kuwait).
- **Weak spots for future transfers:** goalkeeper (Trafford ~3.0/GW), Muharemović (benched most weeks), and a João Pedro return from GW7 if fit (7/8 rivals own him).
- **Watch over the break:** Haaland (Norway), Calvert-Lewin (England), Bruno and Mbeumo, João Pedro's recovery, Tarkowski.

## Fixed in this PR

- `src/team_state._free_transfers` added +1 free transfer for the wildcard week (report said 4; the app showed 3). WC/FH weeks now neither consume nor earn a free transfer, and the replay spends before earning before capping at 5. `src/ft_guard.reconcile` updated to match.
- Name collisions: two players share the web name "Thomas". The new planner resolves players by id or `NAME:TEAM`.
