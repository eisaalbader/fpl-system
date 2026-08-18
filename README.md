# FPL Decision System — v0.2

A point-in-time FPL data logger, projection engine and squad optimiser that
runs entirely on free GitHub Actions. **Nothing runs on your computer. Nothing
is stored on your computer.**

Cost: £0/month, forever.

---

## Setup — about 20 minutes, browser only

You can do all of this from a phone.

### 1. Create the repo
Go to github.com → **New repository**.

- Name: `fpl-system` (or anything)
- **Public** ← important. Public repos get *unlimited* free Actions minutes. Private repos get 2,000/month, which this would eventually exceed.
- Tick "Add a README"

### 2. Get the files in

**Option A — PowerShell (faster):** extract the zip, open PowerShell in that
folder, run:

```powershell
.\setup.ps1 -RepoUrl "https://github.com/YOURNAME/fpl-system.git"
```

**Option B — browser:** **Add file → Upload files**, drag everything in, commit.

### 3. Add your team ID
Open `config/settings.yaml` (click it, then the pencil icon).

Change `team_id: null` to your FPL team ID — the number in your FPL URL when
you view your own team. Commit.

> **There is no email or password field, and there never will be.** Everything
> here uses public endpoints. See "Why no auto-transfers" below.

### 4. Turn on Actions
**Actions** tab → "I understand my workflows, go ahead and enable them".

Then: **Settings → Actions → General → Workflow permissions** →
select **Read and write permissions** → Save.

Without that last step the collector cannot commit data and will fail silently.

### 5. Start the collector now
**Actions → collect → Run workflow**.

Wait ~40 seconds, then check `data/` for a new folder. If it's there, you're
live. It will now run every hour by itself.

### 6. Build history, then report
**Actions → backfill → Run workflow** (~2 min, builds 7 seasons / 186k rows).

Then **Actions → report → Run workflow**. Open `reports/latest.md`.

---

## What you do from now on

| When | What |
|---|---|
| Daily | **Nothing.** |
| Weekly | Open a chat, say "weekly briefing". Make the clicks in the FPL app. |

That's it.

---

## What's in here

```
config/
  rules_2026_27.yaml   Verified FPL rules. Nothing is hardcoded elsewhere.
  settings.yaml        The only file you edit.
src/
  fpl_api.py           API client. Defensive - survives FPL renaming fields.
  collect.py           Hourly point-in-time logger. The irreplaceable piece.
  backfill.py          7 seasons of history. Quarantines the leaky xP column.
  minutes.py           Minutes model. 25.7% better than a price heuristic.
  rates.py             Empirical-Bayes per-90 rates + DefCon threshold model.
  project.py           Assembles points from components, with an audit trail.
  squad.py             Integer programme. All FPL constraints enforced.
  report.py            Writes reports/latest.md.
  rules_check.py       Alarms if FPL changes the rules under you.
.github/workflows/
  collect.yml          Hourly, plus every 15 min in pre-deadline windows.
  report.yml           Friday + Saturday before deadlines.
```

---

## Why the collector matters more than the model

The FPL API only returns **current** state. There is no way to ask what a
player's price, ownership or injury flag was at a past deadline. Public
historical datasets store *end-of-gameweek* snapshots — contaminated for
backtesting, because news that broke during the gameweek is already baked in.

So we log it ourselves, hourly. Every hour not logged is ground truth
permanently lost. By GW10 you have something no public dataset has: a true
record of what was knowable *before* each deadline.

Storage is ~40MB per season. Each snapshot is written once and never modified,
so git doesn't bloat.

---

## Why no auto-transfers

Technically possible. Three reasons it isn't here:

1. It requires your FPL **email and password** in a config file.
2. Transfers are **irreversible and cost points**. A bot firing at 18:00 that
   doesn't know your captain was ruled out at 18:10 has no undo.
3. FPL changes its login flow periodically and breaks community libraries.
   You'd find out at the worst possible moment.

The system reads your squad from **public** endpoints using only your team ID.
You make the clicks — about 60 seconds a week.

---

## What v0.2 measures

| Component | Method | Out-of-sample result |
|---|---|---|
| Minutes | Multinomial logit over {0, 1-59, 60-89, 90} | Brier **0.173** vs 0.232 for a price heuristic — **25.7% better**, consistent across 4 held-out seasons |
| Per-90 rates | Empirical Bayes, prior strength fitted from data | k=60 (DEF) to k=27 (FWD) — learned, not hand-set |
| DefCon | Negative binomial threshold model | Dispersion measured at 1.6–2.1, confirming NB over Poisson |

Two bugs the validation caught and fixed:

1. **Position labels.** History uses `GK`/`GKP`/`AM` inconsistently. Unfixed,
   18,077 goalkeeper rows were invisible to the minutes model. Fixing it
   improved the model from 23.8% to 25.7%.
2. **Top-end bias.** 2025-26 showed the model 10 points overconfident above
   p=0.6. Checking all four held-out seasons showed +0.047, +0.065, +0.037,
   −0.103 — mean ≈ 0, sd 0.067. It was one outlier season, not a flaw.
   "Correcting" it would have made the model worse. No correction applied.

## Known limitations (deliberately visible)

Every report ends with a table of what the system can't do yet. At GW1 that
list is long: no minutes model, no clean-sheet model, no defensive
contribution model, no bonus model, no real probability distributions, no
backtest. Projections are priors from last season plus FPL's own `ep_next`.

This is honest rather than modest. A report that hides its own weakness
launders a guess into something that looks authoritative.

Real forecasting starts around GW3 when current-season match data exists.

## Things that will bite you

- **GitHub cron runs 10–30 min late** under load, and the minimum interval is
  5 minutes. Fine for hourly logging; don't rely on it to the minute.
- **GitHub does not email you when a scheduled job fails.** That's why every
  report starts with a data-freshness alarm. If it says 🔴, fix the collector
  before acting on anything.
- **Scheduled workflows auto-disable after 60 days of repo inactivity.** The
  collector commits data hourly, which counts as activity, so this shouldn't
  trigger — but if reports stop appearing, check the Actions tab first.
