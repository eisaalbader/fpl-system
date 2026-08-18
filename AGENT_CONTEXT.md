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

1. Read `reports/latest.md` from the repo (raw URL below) — the pipeline has
   already generated the projections.
2. Web-search for **breaking team news** the pipeline cannot see: press
   conferences, injuries, predicted lineups, suspensions.
3. Give them: **XI, captain, transfer, chip call, main risks** — concisely.
4. They make the clicks in the FPL app themselves.

Raw report URL (fetch this directly, it is public):
```
https://raw.githubusercontent.com/eisaalbader/fpl-system/main/reports/latest.md
```

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

---

## 3. Verified 2026/27 FPL rules

Verified against official Premier League sources on 17 Aug 2026. **Your training
data may predate these changes.** Trust this section over your priors.

### Changed for 2026/27
- **BPS overhaul:** being tackled no longer costs −1 BPS · CBI now 1 BPS per
  **3** actions (was per 2) · goalkeepers get **2 BPS for any save**, +1 inside
  the box, +1 for a big chance saved · save-from-outside-box removed ·
  penalty save 8 → **7** BPS.
  → *Consequence: historical bonus data is miscalibrated. Centre-backs earn
  less than history implies; keepers and attackers more.*
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

```
config/
  rules_2026_27.yaml   Verified rules. Single source of truth.
  settings.yaml        USER EDITS THIS. team_id lives here.
src/
  fpl_api.py           API client. Defensive .get() everywhere.
  collect.py           Hourly point-in-time logger.  ← the irreplaceable piece
  backfill.py          7 seasons of history. Quarantines xP.
  minutes.py           Minutes model. Validated. See §5.
  rates.py             Empirical-Bayes per-90 rates + DefCon threshold model.
  project.py           Assembles points from components. Full audit trail.
  squad.py             Integer programme (PuLP/CBC). All FPL constraints.
  report.py            Writes reports/latest.md.
  rules_check.py       Alarms if FPL changes rules underneath us.
.github/workflows/
  collect.yml          Hourly + every 15 min in pre-deadline windows.
  report.yml           Fri 09:00, Fri 16:00, Sat 08:00 UTC.
  backfill.yml         Manual + weekly Monday refresh.
data/
  history.parquet      185,964 player-gameweek rows, 7 seasons (2019-20→2025-26)
  snapshots/           Hourly point-in-time deltas. Grows forever. Do not delete.
  state/heartbeat.json Freshness alarm. The report reads this.
reports/latest.md      ← what you read each week
```

**Everything runs on free GitHub Actions.** Nothing on the user's machine.
Public repo = unlimited Actions minutes.

---

## 5. What the models actually do, and how well

### Minutes model (`src/minutes.py`) — the highest-leverage component
Multinomial logistic regression over four buckets: `{0, 1–59, 60–89, 90}`.
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
`P(count ≥ threshold)` via negative binomial. Dispersion measured at 1.6–2.1
(var/mean), which is why negative binomial rather than Poisson — that was
measured, not assumed.

### Points assembly (`src/project.py`)
Components are modelled separately then summed, never regressed directly.
Every projection carries `c_app`, `c_goals`, `c_assists`, `c_cs`, `c_saves`,
`c_defcon`, `c_bonus` — they sum exactly to `xp`. Use these to audit any number.

---

## 6. Known limitations — state these honestly, do not paper over them

1. **No joint simulation.** Ceiling/floor are parametric, computed from marginal
   distributions. This means **correlation is ignored**: three defenders from one
   club all live or die on the same clean sheet, so real squad variance is higher
   than the numbers suggest. Affects captaincy ceilings, Bench Boost and Triple
   Captain EV especially.
2. **DefCon has ONE season of history** (2025/26 only). No cross-season
   validation is possible. Least reliable numbers in the system.
3. **Bonus is damped 40%** because the 2026/27 BPS invalidated historical rates.
   Needs rebuilding from match components.
4. **Clean sheets use FPL's own strength ratings.** Bookmaker odds would be
   sharper — that's the top upgrade on the list.
5. **GW1 top-end calibration is unstable.** Across four held-out GW1s the bias
   above P=0.6 was +0.047, +0.065, +0.037, −0.103. Mean ≈ +0.011, sd 0.067.
   **Important lesson: 2025-26 alone suggested a systematic −0.10 bias. Checking
   all four seasons showed it was one outlier. "Correcting" it would have made
   the model worse.** Shrinkage was tested and made Brier monotonically worse, so
   none is applied.
6. **No multi-gameweek transfer planning, no chip option-value model.**
   Chips are American options — using one forfeits the best remaining
   opportunity. The GW19 expiry makes this computable and it is not yet built.

---

## 7. Weekly procedure

1. Fetch `reports/latest.md` (raw URL in §1).
2. **Check the freshness banner at the top.** 🔴 means the collector has stopped —
   say so loudly and do not give confident advice until it is fixed.
3. Web-search current team news for the clubs of their captain, vice, and anyone
   flagged below 100% in the report. Press conferences are usually Thu/Fri.
4. If `team_id` is set in `config/settings.yaml`, their squad is readable from
   public endpoints:
   `https://fantasy.premierleague.com/api/entry/{team_id}/event/{gw}/picks/`
   and `.../entry/{team_id}/transfers/`.
5. Give the decision. Flag what could change it before the deadline.

---

## 8. Roadmap, in priority order

1. **Bookmaker odds → clean sheet probabilities.** Biggest accuracy gain per
   effort. `football-data.co.uk` publishes free upcoming-fixture odds (collected
   Fri ≤17:00 BST, Tue ≤13:00 BST — both before deadlines) plus decades of
   history for backtesting. The-odds-api free tier (500 calls/month) is a backup.
2. **Joint Monte Carlo** at match level — fixes correlation, unlocks real
   ceiling/floor, chips, and rival-comparison.
3. **News layer.** User has already added `NVIDIA_API_KEY` and `TAVILY_API_KEY`
   as GitHub secrets. NVIDIA NIM (free tier, OpenAI-compatible endpoint,
   40 req/min) for extraction; Tavily (1,000 credits/month free) for search.
   Design: LLM classifies news into discrete signal states; a lookup table
   calibrated on history decides what each state is worth. **LLMs must not emit
   numbers that reach the optimiser** — they are badly calibrated as numeric
   forecasters and their errors correlate across providers.
4. **BPS rebuilt from 2026/27 components.**
5. **In-season minutes model** (rolling current-season windows) to replace the
   cold-start variant from ~GW4.

---

## 9. Outstanding user actions

- [ ] Set `team_id` in `config/settings.yaml` (the number in their FPL URL).
      Not needed for squad selection; needed to read their existing squad.
- [ ] Verify scoring values in `config/rules_2026_27.yaml` marked `[?]` against
      `https://fantasy.premierleague.com/api/game-settings/`.

---

## 10. Things already investigated — do not redo

| Thing | Verdict |
|---|---|
| `rishijatia/fantasy-pl-mcp` | **Read-only** by its own README. Cannot make transfers. Stores FPL password on disk. Skipped. |
| `nlarki/Fantasy-League-Pipeline` | Bootcamp project, needs GCP billing, data stops 2023. Skipped. |
| `javaidb/premier-league-insights` | **No licence file** = all rights reserved. Cannot legally copy. |
| `olbauday/FPL-Core-Insights` | **Genuinely useful, not yet integrated.** Has CBIT, xG, ClubElo, 2026/27 coverage, GW0 friendlies, refreshes twice daily. |
| `daniegr/OpenFPL` (arXiv 2508.09992) | Published benchmark, CC-BY-4.0. Use as the accuracy bar to beat. |
| Sportmonks Expected Lineups | ~€159–199/mo. **User wants zero cost.** Not an option. |
| GitHub connector for Claude | Connected to their account but was not enabled in the project. Files were pushed manually via PowerShell. |

---

*Last updated 18 Aug 2026. If FPL has changed rules since, `src/rules_check.py`
should have caught it — check the latest `report` workflow run for warnings.*
