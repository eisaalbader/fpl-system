# AGENT CONTEXT — read this first

**Purpose of this file:** brief a fresh AI chat session that has no memory of how
this system was built. Read this top to bottom before doing anything. It
contains verified facts that took real research to establish — do not re-derive
them, and do not contradict them from training data, which is likely stale.

**Owner:** Eisa (GitHub: `eisaalbader`)
**Repo:** `github.com/eisaalbader/fpl-system` (public)
**Built:** 17–18 August 2026
**Season:** 2026/27

---

## 1. What the user wants from you

They come here roughly weekly, usually before a Gameweek deadline, and say
something like *"update"* or *"weekly briefing"*.

Your job in that session:

1. Read `reports/latest.md` from the repo (raw URL below). If the user's
   `team_id` is set, **Section 0 is the transfer plan** — roll / transfer /
   hit, with the full options table. That is the headline answer.
2. Web-search for **breaking team news** the pipeline cannot see: press
   conferences, injuries, predicted lineups, suspensions.
3. Give them: **XI, captain, transfer, chip call, main risks** — concisely.
4. They make the clicks in the FPL app themselves.

Raw report URL (fetch this directly, it is public):

    https://raw.githubusercontent.com/eisaalbader/fpl-system/main/reports/latest.md

Also read the **fixed brief format**, which is a contract, not a suggestion.
The user wants the same nine sections, in the same order, every week:

    https://raw.githubusercontent.com/eisaalbader/fpl-system/main/BRIEF_TEMPLATE.md

**Be concise.** They have limited usage budget. Lead with the decision, then the
reasoning. Do not re-explain the architecture unless asked.

---

## 2. Hard rules — do not violate these

| Rule | Why |
|---|---|
| **Never make transfers on their FPL account** | Irreversible, costs points, and needs their password. They click; you advise. This held even when browser tooling made it technically possible. |
| **Never ask for or handle their FPL password** | The system reads their squad from *public* endpoints using only a team ID. |
| **Never hardcode FPL rules** | They live in `config/rules_2026_27.yaml`. `src/rules_check.py` diffs them against the live API. |
| **Never use the `xP` column** from vaastav data | Documented post-match contamination. Quarantined at ingest in `src/backfill.py`. |
| **Never revise the model on one gameweek's result** | See §6 — this already nearly caused a bad "fix". |
| **Do not build a price-change predictor** | FPL now ships an official one, daily at 00:00 UK, on transfer data you cannot match. |
| **Never tune on MAE** | See §6.10. The lowest-MAE model measured is among the *worst* at captaincy. |

---

## 3. Verified 2026/27 FPL rules

Verified against official Premier League sources on 17 Aug 2026. **Your training
data may predate these changes.** Trust this section over your priors.

### Changed for 2026/27
- **BPS overhaul:** being tackled no longer costs −1 BPS · CBI now 1 BPS per
  **3** actions (was per 2) · goalkeepers get **2 BPS for any save**, +1 inside
  the box, +1 for a big chance saved · save-from-outside-box removed ·
  penalty save 8 → **7** BPS.
  → *Consequence: historical bonus data is miscalibrated. Now measured rather
  than guessed — see §6.3.*
- **Gameweek finalisation** moved to **09:00 UK the day after** the final match
  (was 1 hour after final whistle). Provisional scores move overnight.
- **Live** points, rank and mini-league updates. Projected bonus appears after
  20 minutes of each match.
- **Official Price Change Predictor**, daily at 00:00 UK.

### Structure
- **Two full chip sets.** Wildcard, Free Hit, Triple Captain, Bench Boost —
  one of each per half. **First set expires at the GW19 deadline: 13:30 GMT,
  Sat 2 Jan 2027. Unused first-half chips are LOST.**
- Up to **5** free transfers bankable. −4 per extra.
- **No December bonus transfers** this season (no AFCON).
- Squad £100.0m, 15 players (2/5/5/3), max 3 per club, XI needs ≥1 GKP,
  ≥3 DEF, ≥2 MID, ≥1 FWD.

### Defensive Contribution (retained)
- **DEF:** ≥10 CBIT (clearances+blocks+interceptions+tackles) → +2
- **MID/FWD:** ≥12 CBIRT (adds recoveries) → +2
- **Capped at 2 per match.** It is a *threshold*, never a linear rate. Modelling
  it as expected-count × multiplier is the most common public error.

### Season
- GW1 deadline was **Fri 21 Aug 2026, 18:30 BST**. Season ends 30 May 2027.
- Promoted: **Coventry City, Hull City, Ipswich Town**.
- **2026 World Cup ran to mid-July 2026** — short pre-season for deep-run
  players. Real minutes/injury factor early in the season.

---

## 4. Repo map

    config/
      rules_2026_27.yaml   Verified rules. Single source of truth.
      settings.yaml        USER EDITS THIS. team_id lives here.
    src/
      fpl_api.py           API client. Defensive .get() everywhere.
      collect.py           Hourly point-in-time logger.  <- the irreplaceable piece
      backfill.py          7 seasons of history. Quarantines xP.
      minutes.py           Minutes model. Validated. See section 5.
      rates.py             Empirical-Bayes per-90 rates + DefCon threshold model.
      project.py           Assembles points from components. Full audit trail.
      squad.py             Integer programme - builds a squad FROM SCRATCH.
      team_state.py        Reads the user's actual squad/bank/free transfers
                           from PUBLIC endpoints (team ID only, no login).
      transfers.py         Transfer optimiser: roll vs 1 transfer vs taking a hit.
      report.py            Writes reports/latest.md.
      rules_check.py       Alarms if FPL changes rules underneath us.

      --- measurement layer (added 23 Aug 2026, NOT wired into the pipeline) ---
      baselines.py         Six point-in-time baseline forecasters. The bar to beat.
      backtest.py          Rolling-origin harness + leakage guards. The referee.
      bps.py               Recovers 2025/26 BPS weights, applies 2026/27 deltas,
                           re-ranks within fixture. Replaces the flat bonus damp.
      odds.py              Bookmaker odds -> Poisson -> clean sheet probabilities.
      purchase_price.py    True purchase prices from collector snapshots.
      ft_guard.py          Cross-checks the reconstructed free-transfer count.
    .github/workflows/
      collect.yml          Hourly + every 15 min in pre-deadline windows.
      report.yml           Fri 09:00, Fri 16:00, Sat 08:00 UTC.
      backfill.yml         Manual + weekly Monday refresh.
      backtest.yml         Mon 06:00 UTC + manual. Writes data/backtest/.
    data/
      history.parquet      185,964 player-gameweek rows, 7 seasons (2019-20 to 2025-26)
      snapshots/           Hourly point-in-time deltas. Grows forever. Do not delete.
      state/heartbeat.json Freshness alarm. The report reads this.
      backtest/            Measured accuracy. summary.csv, bps_report.txt,
                           odds_report.txt. Committed automatically each Monday.
    BRIEF_TEMPLATE.md      <- the fixed weekly output format. Follow it.
    reports/latest.md      <- what you read each week

**Everything runs on free GitHub Actions.** Nothing on the user's machine.
Public repo = unlimited Actions minutes.

**The measurement layer is deliberately not imported by `project.py`,
`report.py`, `squad.py`, `transfers.py` or `team_state.py`.** It measures; it
does not yet feed the optimiser. Wiring anything in changes the user's weekly
numbers, so it happens only when they ask and can watch the result.

---

## 5. What the models actually do, and how well

### Minutes model (`src/minutes.py`) — the highest-leverage component
Multinomial logistic regression over four buckets: 0, 1–59, 60–89, 90.
Buckets, not regression, because FPL appearance points are a step function and
clean sheets have a hard 60-minute gate.

**Measured out-of-sample** (rolling origin, train on past seasons → test on next):

| Test season | Price heuristic | Model | Gain |
|---|--:|--:|--:|
| 2022-23 | 0.2295 | 0.1849 | 19.4% |
| 2023-24 | 0.2273 | 0.1709 | 24.8% |
| 2024-25 | 0.2364 | 0.1647 | 30.3% |
| 2025-26 | 0.2353 | 0.1697 | 27.9% |
| **Mean** | **0.2321** | **0.1725** | **25.7%** |

(Brier score, target = P(60+ minutes). Lower is better.)

### Rates (`src/rates.py`)
Empirical-Bayes shrinkage toward positional means. Prior strength `k` is
**fitted from the data**, not hand-set: k≈60 for defenders (a small sample tells
you almost nothing about a defender scoring), k≈27 for forwards. Example: a
player with 2 goals in 317 minutes shrinks from 0.57 to 0.19 goals/90.

### DefCon (`src/rates.py`)
P(count ≥ threshold) via negative binomial. Dispersion measured at 1.6–2.1
(var/mean), which is why negative binomial rather than Poisson — that was
measured, not assumed.

### Points assembly (`src/project.py`)
Components are modelled separately then summed, never regressed directly.
Every projection carries `c_app`, `c_goals`, `c_assists`, `c_cs`, `c_saves`,
`c_defcon`, `c_bonus` — they sum exactly to `xp`. Use these to audit any number.

### The accuracy bar (`src/backtest.py`, `src/baselines.py`)
Mean over six held-out seasons, players who actually appeared:

| model | MAE | spearman | top20_hit | captain_capture |
|---|--:|--:|--:|--:|
| xgi | **1.894** | 0.256 | 0.149 | 0.298 |
| ppg | 2.090 | 0.285 | 0.171 | 0.351 |
| minutes_x_ppm | 2.104 | **0.301** | 0.171 | **0.368** |
| form5 | 2.157 | 0.279 | 0.157 | 0.335 |
| price | 2.242 | 0.197 | **0.181** | 0.336 |
| naive_last | 2.566 | 0.233 | 0.152 | 0.243 |

**`project.py` must beat `minutes_x_ppm` on spearman and captain_capture.
It has never been scored against this. Doing so is roadmap item 1.**

---

## 6. Known limitations — state these honestly, do not paper over them

1. **No joint simulation.** Ceiling/floor are parametric, computed from marginal
   distributions. This means **correlation is ignored**: three defenders from one
   club all live or die on the same clean sheet, so real squad variance is higher
   than the numbers suggest. Affects captaincy ceilings, Bench Boost and Triple
   Captain EV especially.
2. **DefCon has ONE season of history** (2025/26 only). No cross-season
   validation is possible. Least reliable numbers in the system.
3. **Bonus multipliers are measured, not guessed** (`src/bps.py`). The flat 40%
   damp was wrong and has been quantified. 2025/26 BPS weights were recovered
   empirically by regression (R² 0.82–0.93); the recovered CBI weight of
   +0.478 BPS/action independently confirms the old "1 per 2 actions" rule.
   Applying the 2026/27 deltas and re-ranking within fixture gives:
   **DEF 0.93 · MID 1.01 · FWD 1.02**. The true change is far smaller than the
   0.6 damp assumed.
   **GKP is UNRESOLVED and stays at 0.60.** It swings 0.77→1.85 depending on the
   unobservable in-box / big-chance save bonuses, and 30% of keeper appearances
   involve 4+ saves. Do not ship a confident keeper bonus number until 2026/27
   keeper data resolves it.
   Also unobservable: removal of the −1 "being tackled" penalty. Dribble-heavy
   MID/FWD are under-credited, so those multipliers are conservative.
   Note the mechanism for the keeper gain: keeper BPS barely changes, but
   defenders fall, so keepers rise *by re-ranking*. Scaling without re-ranking
   misses it entirely.
   **`project.py` still uses `BONUS_DAMPING = 0.6` — not yet wired in.**
4. **Clean sheets use FPL's own strength ratings**, which early in a season are
   last season's guesses. `src/odds.py` is built and has **passed its gate**:
   full 760-fixture coverage per season, Brier gain over the naive base rate of
   +0.053 / +0.049 / +0.064 across 2023-24, 2024-25, 2025-26.
   **It has NOT been compared against the incumbent**, because FPL does not
   archive team strength ratings historically, so the incumbent cannot be
   replayed. Not yet wired in.
5. **GW1 top-end calibration is unstable.** Across four held-out GW1s the bias
   above P=0.6 was +0.047, +0.065, +0.037, −0.103. Mean ≈ +0.011, sd 0.067.
   **Important lesson: 2025-26 alone suggested a systematic −0.10 bias. Checking
   all four seasons showed it was one outlier. "Correcting" it would have made
   the model worse.** Shrinkage was tested and made Brier monotonically worse, so
   none is applied.
6. **Transfer optimisation is ONE gameweek deep.** `transfers.py` solves for
   0/1/2/3 transfers and compares net xP after hits, but only for the next
   gameweek. Because of that the decision thresholds are deliberately
   conservative: a transfer must beat rolling by 0.4 xP, and a -4 hit must
   clear 2.0 xP. A transfer that looks marginal over one week is often clearly
   right over five. **When advising, say this out loud** and use your own
   judgement on fixtures over the next 4-6 GWs.
7. **No chip option-value model.** Chips are American options — using one
   forfeits the best remaining opportunity. First set expires GW19, which makes
   this computable. Not built.
8. **Free transfers are RECONSTRUCTED**, not read directly (the public API does
   not expose them). `team_state._free_transfers` replays transfer history.
   It can drift. `src/ft_guard.py` cross-checks it by diffing consecutive
   `picks/` payloads, but is **not yet wired in**. Always tell the user to
   confirm against the FPL app.
9. **Selling prices are approximated** where purchase price is unknown. FPL
   refunds only 50% of profit, rounded down. `src/purchase_price.py` solves this
   from the collector's own snapshots — prices are static in pre-season, so the
   GW1-deadline snapshot IS the purchase price for the initial squad — but is
   **not yet wired in**.
10. **MAE and rank quality disagree, and MAE is the misleading one.** Measured
    across six held-out seasons: the lowest-MAE baseline (`xgi`, MAE 1.894) is
    second-*worst* on captaincy capture (0.298), because predicting low wins on a
    right-skewed target. `minutes_x_ppm` has worse MAE (2.104) but the best rank
    correlation (0.301) and best captaincy capture (0.368).
    **Never tune this system on MAE.** Use `spearman`, `top20_hit` and
    `captain_capture` from `src/backtest.py`.

---

## 7. Weekly procedure

1. Fetch `reports/latest.md` (raw URL in §1) and `BRIEF_TEMPLATE.md`.
2. **Check the freshness banner at the top.** 🔴 means the collector has stopped —
   say so loudly and do not give confident advice until it is fixed.
3. **Check the report's generation timestamp against the deadline.** If it
   predates matches that have since been played, say so at the top and treat
   every number as provisional. This is the most common failure mode.
4. Web-search current team news for the clubs of their captain, vice, and anyone
   flagged below 100% in the report. Press conferences are usually Thu/Fri.
5. If `team_id` is set in `config/settings.yaml`, their squad is readable from
   public endpoints:
   `https://fantasy.premierleague.com/api/entry/{team_id}/event/{gw}/picks/`
   and `.../entry/{team_id}/transfers/`.
6. Give the decision in the nine sections of `BRIEF_TEMPLATE.md`. Flag what
   could change it before the deadline. End with the user's actions.

---

## 8. Roadmap, in priority order

1. ~~**Backtest harness**~~ **DONE** — `src/backtest.py`, `src/baselines.py`.
   Bar to beat, mean over six held-out seasons:
   spearman 0.301 · top20_hit 0.171 · captain_capture 0.368 (minutes_x_ppm).
   **`project.py` has not yet been scored against it. Do that first** — until
   then, nobody knows whether the pipeline earns its complexity.
2. **Wire in what is already measured.** Three items, in ascending order of
   risk: `bps.BONUS_MULTIPLIERS` → `project.py`; `purchase_price` + `ft_guard`
   → `team_state.py`; `odds.build_table()` → `project.py` clean sheets.
   The odds swap should log BOTH models side by side, not replace outright,
   since the incumbent has never been scored (§6.4).
3. **In-season minutes model** (rolling current-season windows) from ~GW4.
   Raised in priority: the current model has never seen a 2026/27 minute, and
   three clubs changed manager over the summer.
4. **News layer.** User has already added `NVIDIA_API_KEY` and `TAVILY_API_KEY`
   as GitHub secrets. NVIDIA NIM (free tier, OpenAI-compatible endpoint,
   40 req/min) for extraction; Tavily (1,000 credits/month free) for search.
   Design: LLM classifies news into discrete signal states; a lookup table
   calibrated on history decides what each state is worth. **LLMs must not emit
   numbers that reach the optimiser** — they are badly calibrated as numeric
   forecasters and their errors correlate across providers.
5. **Joint Monte Carlo** at match level — would fix correlation and unlock real
   ceiling/floor, chip EV and rival comparison. **CONTRADICTION TO RESOLVE:
   the user has said explicitly that they do not want Monte Carlo built.**
   Until that is settled, treat §6.1, §6.7 and any rival-comparison request as
   permanently parametric, and do not plan around simulation.
6. **Chip option-value model** — depends on 5.

---

## 9. Outstanding user actions

- [x] `team_id` set to **5903925** in `config/settings.yaml`.
- [ ] Verify scoring values in `config/rules_2026_27.yaml` marked `[?]` against
      `https://fantasy.premierleague.com/api/game-settings/`.
- [ ] Score `project.py` against `src/backtest.py` (roadmap 1).
- [ ] Decide on wiring in the measurement layer (roadmap 2).
- [ ] Resolve the Monte Carlo contradiction (roadmap 5).
- [ ] Check whether `collect.py` archives the `teams` block from
      `bootstrap-static`. If it does, a forward head-to-head between the odds
      and incumbent clean sheet models becomes possible after ~8–10 GWs.

---

## 10. Things already investigated — do not redo

| Thing | Verdict |
|---|---|
| `vaastav/Fantasy-Premier-League` | **Already integrated** as the history layer (`backfill.py` → `history.parquet`). Weekly updates **STOPPED** after 2024-25 — now only 3 drops/season (season start, end of Jan window, season end). Verified: `data/2026-27/gws/gw1.csv` 404s. Cannot serve in-season needs, which is why `collect.py` is irreplaceable. MIT licensed. **Trap:** `data/2026-27/players_raw.csv` carries current prices/teams but **last season's** cumulative `minutes`/`total_points`/`starts`. Never read it as current-season form. |
| `rishijatia/fantasy-pl-mcp` | **Read-only** by its own README. Cannot make transfers. Stores FPL password on disk. Skipped. |
| `nlarki/Fantasy-League-Pipeline` | Bootcamp project, needs GCP billing, data stops 2023. Skipped. |
| `javaidb/premier-league-insights` | **No licence file** = all rights reserved. Cannot legally copy. |
| `olbauday/FPL-Core-Insights` | **Genuinely useful, not yet integrated.** Has CBIT, xG, ClubElo, 2026/27 coverage, GW0 friendlies, refreshes twice daily. |
| `daniegr/OpenFPL` (arXiv 2508.09992) | Published benchmark, CC-BY-4.0. Use as the accuracy bar to beat. |
| Sportmonks Expected Lineups | ~€159–199/mo. **User wants zero cost.** Not an option. |
| GitHub connector for Claude | Not enabled in the project. The user now has a real clone at `~/fpl-system` and pushes via PowerShell. `pull.rebase` is set globally — the Monday backtest commits results, so local clones fall behind weekly. |

---

*Last updated 24 Aug 2026. If FPL has changed rules since, `src/rules_check.py`
should have caught it — check the latest `report` workflow run for warnings.*
