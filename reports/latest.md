# GW1 Decision Report

Generated **2026-08-21 16:17 UTC** · Deadline **2026-08-21T17:30:00Z**

🟢 Data is 0.5h old.

> **Transfer mode unavailable:** no gameweek has started yet - no squad to read
> Showing a fresh optimal squad instead — ignore it if you already have a team.

> ### ⚠️ What is and is not modelled here
> There is **zero current-season Premier League data**. Everything below is built from 7 seasons of history (185,964 player-gameweek rows), not from current form.
> 
> **Modelled:** minutes distribution over {0, 1-59, 60-89, 90} (validated out-of-sample: Brier 0.173 vs 0.232 for a price heuristic — 25.7% better across 4 held-out seasons); goal and assist rates with empirical-Bayes shrinkage; clean-sheet probability; goalkeeper saves; defensive contributions as a threshold model.
> 
> **Not modelled:** joint Monte Carlo (so ceiling/floor are parametric, not sampled — they ignore that a team's defenders share clean-sheet outcomes); bonus rebuilt from the new 2026/27 BPS components; multi-gameweek planning; chip timing.
> 
> **Bonus is damped by 40%** because the 2026/27 BPS changed (CBI now 1 point per 3 actions rather than per 2, tackled penalty removed, keeper saves restructured). Historical bonus rates are miscalibrated by construction.
> 
> **Overall confidence: MODERATE.** The minutes and rate models are real and measured. Everything downstream of them is v1.

## 1. Recommended XI

Formation **5-4-1** · Squad cost **£100.0m** · XI expected points (captain doubled) **52.92**

| Player | Team | £ | xP | P(60+) | Mins | DefCon | Own% | Conf | Note |
|---|---|--:|--:|--:|--:|--:|--:|---|---|
| Pickford | EVE | 5.5 | 3.83 | 0.89 | 80 | - | 7.9 | medium |  |
| Gabriel | ARS | 8.0 | 4.74 | 0.93 | 83 | 0.36 | 29.7 | medium |  |
| Senesi | TOT | 6.0 | 4.48 | 0.90 | 81 | 0.56 | 8.2 | medium |  |
| Tarkowski | EVE | 6.0 | 4.47 | 0.90 | 81 | 0.45 | 8.7 | medium |  |
| Virgil | LIV | 6.5 | 4.38 | 0.92 | 83 | 0.38 | 18.7 | medium |  |
| Guéhi | MCI | 6.0 | 4.27 | 0.89 | 80 | 0.26 | 17.3 | medium |  |
| B.Fernandes | MUN | 12.0 | 5.06 | 0.95 | 82 | 0.15 | 51.8 | medium |  |
| Semenyo | MCI | 8.5 | 4.42 | 0.90 | 79 | 0.06 | 26.3 | medium |  |
| Anderson | MCI | 6.5 | 4.20 | 0.81 | 73 | 0.49 | 8.1 | medium |  |
| Rice | ARS | 7.5 | 4.12 | 0.85 | 75 | 0.30 | 18.2 | medium |  |
| Thiago | BRE | 8.0 | 3.89 | 0.76 | 70 | 0.03 | 17.1 | medium |  |

## 2. Bench (in auto-sub order)

| Order | Player | Team | £ | xP | Why here |
|---|---|---|--:|--:|---|
| GK | Dubravka | TOT | 4.0 | 2.92 | Backup keeper — only plays if your starter is dropped |
| 1 | Yarmoliuk | BRE | 5.0 | 2.56 | Ordered by expected points |
| 2 | Calvert-Lewin | LEE | 6.0 | 2.55 | Ordered by expected points |
| 3 | Obi | MUN | 4.5 | 0.44 | Ordered by expected points |

## 3. Captain

**Captain: B.Fernandes** (MUN, £12.0m)

| | xP | Floor (p10) | Ceiling (p90) | Exp mins | Own% |
|---|--:|--:|--:|--:|--:|
| B.Fernandes | 5.06 | 0.0 | 11.6 | 82 | 51.8 |
| Gabriel (vice) | 4.74 | 0.1 | 9.4 | 83 | 29.7 |


**Where the captain's points come from:**

| Appearance | Goals | Assists | Clean sheet | Saves | DefCon | Bonus |
|--:|--:|--:|--:|--:|--:|--:|
| 1.95 | 0.93 | 1.10 | 0.20 | 0.00 | 0.31 | 0.57 |

*Selected on expected points only. Ceiling/floor are parametric, not sampled. Ownership-adjusted and rank-relative captaincy needs the joint simulation (not yet built).*

## 4. Players flagged in FPL's own news field

| Player | Team | Status | Chance | News |
|---|---|---|--:|---|
| Bruno G. | ARS | d | 75% | Thigh injury - 75% chance of playing |
| Henderson | CRY | d | 75% | Ankle injury - 75% chance of playing |
| Šeško | MUN | d | 75% | Shin injury - 75% chance of playing |
| Welbeck | CHE | d | 75% | Unspecified injury - 75% chance of playing |
| C.Jones | LIV | d | 75% | Hip injury - 75% chance of playing |
| Adams | BOU | d | 75% | Unspecified injury - 75% chance of playing |
| Darlow | MUN | d | 75% | Unspecified injury - 75% chance of playing |
| Henderson | CHE | d | 75% | Wrist injury - 75% chance of playing |
| Brooks | BOU | d | 75% | Unspecified injury - 75% chance of playing |
| Garner | EVE | d | 25% | Groin injury - 25% chance of playing |
| Mount | MUN | d | 50% | Foot injury - 50% chance of playing |
| Abraham | AVL | d | 75% | Knock - 75% chance of playing |
| Kudus | TOT | d | 25% | Thigh injury - 25% chance of playing |
| Rodríguez | BOU | d | 75% | Unspecified injury - 75% chance of playing |
| Carvalho | BRE | d | 75% | Lack of match fitness - 75% chance of playing |

## 5. Biggest risks in this recommendation

1. **Minutes at the top end.** The model is measured 25.7% better than a price heuristic, but GW1 top-end calibration swings a lot season to season (+0.047, +0.065, +0.037, -0.103 across four held-out GW1s). For players shown above P(60+) = 0.6, treat the number as roughly +/- 0.07. Managers experiment in GW1.
2. **New signings and promoted-club players** have no usable prior.
3. **DefCon rests on ONE season.** Defensive contributions only exist from 2025/26, so there is no cross-season validation. Rates are shrunk hard, but treat DefCon columns as the least reliable numbers in this report.
4. **Clean sheets use FPL's own strength ratings**, which at GW1 are themselves last season's guesses. Bookmaker odds would be sharper.
5. **Correlation is ignored.** Owning three defenders from one club is riskier than the individual numbers suggest — they all live or die on the same clean sheet. The joint simulation will fix this.

## 6. News watchlist before the deadline

Check these before locking in:

- Press conferences for the clubs of your captain (MUN) and vice (ARS)
- Any player above with a `chance` below 100%
- Confirmed XIs are not available pre-deadline, but Friday-afternoon press conferences usually resolve the biggest doubts
- **World Cup 2026 minutes.** Players who went deep in July have had a very short pre-season. Managers have said publicly they will manage these loads. This is not in the model.

## 7. What this system cannot do yet

| Capability | Status | Available from |
|---|---|---|
| Point-in-time data logging | ✅ live | now |
| Rules engine + drift alerts | ✅ live | now |
| Squad optimisation (IP) | ✅ live | now |
| Minutes model (7 seasons, validated) | ✅ live | now |
| Shrunk goal / assist / save rates | ✅ live | now |
| Clean sheet probability | ✅ v1 (strength-based) | now |
| Defensive contribution model | ✅ live (1 season of data) | now |
| Clean sheet from bookmaker odds | ❌ | GW3 |
| BPS rebuilt from 2026/27 components | ❌ | GW4 |
| Monte Carlo joint distribution | ❌ | GW5 |
| Multi-GW transfer planning | ❌ | GW6 |
| Chip option-value model | ❌ | GW8 |
| Backtest vs baselines | ❌ | GW10 |

---

*Rules spec verified 2026-08-17. Chips: 2 sets, first set expires GW19. Max banked transfers: 5.*

## Appendix: top players by position

### GKP

| Player | Team | £ | xP | P(60+) | Mins | DefCon | Own% | Conf | Note |
|---|---|--:|--:|--:|--:|--:|--:|---|---|
| Pickford | EVE | 5.5 | 3.83 | 0.89 | 80 | - | 7.9 | medium |  |
| Raya | ARS | 6.0 | 3.79 | 0.92 | 82 | - | 37.4 | medium |  |
| Donnarumma | MCI | 5.5 | 3.77 | 0.88 | 79 | - | 8.2 | medium |  |
| Kelleher | BRE | 5.0 | 3.67 | 0.84 | 75 | - | 5.8 | medium |  |
| Verbruggen | BHA | 4.5 | 3.55 | 0.81 | 73 | - | 21.9 | medium |  |
| Leno | FUL | 4.5 | 3.44 | 0.80 | 72 | - | 3.1 | medium |  |
| Roefs | SUN | 5.0 | 3.40 | 0.81 | 72 | - | 4.5 | medium |  |
| Petrović | BOU | 4.5 | 3.34 | 0.81 | 73 | - | 3.3 | medium |  |
| Sánchez | CHE | 5.0 | 3.34 | 0.80 | 72 | - | 2.3 | medium |  |
| Lammens | MUN | 5.0 | 3.15 | 0.79 | 71 | - | 16.9 | medium |  |
| Martinez | AVL | 5.0 | 3.14 | 0.74 | 67 | - | 4.4 | medium |  |
| Sels | NFO | 5.0 | 3.10 | 0.70 | 63 | - | 1.6 | medium |  |

### DEF

| Player | Team | £ | xP | P(60+) | Mins | DefCon | Own% | Conf | Note |
|---|---|--:|--:|--:|--:|--:|--:|---|---|
| Gabriel | ARS | 8.0 | 4.74 | 0.93 | 83 | 0.36 | 29.7 | medium |  |
| Senesi | TOT | 6.0 | 4.48 | 0.90 | 81 | 0.56 | 8.2 | medium |  |
| Tarkowski | EVE | 6.0 | 4.47 | 0.90 | 81 | 0.45 | 8.7 | medium |  |
| Virgil | LIV | 6.5 | 4.38 | 0.92 | 83 | 0.38 | 18.7 | medium |  |
| Guéhi | MCI | 6.0 | 4.27 | 0.89 | 80 | 0.26 | 17.3 | medium |  |
| Lacroix | CHE | 6.0 | 4.21 | 0.88 | 79 | 0.49 | 9.0 | medium |  |
| O'Reilly | MCI | 6.5 | 3.97 | 0.86 | 77 | 0.10 | 21.0 | medium |  |
| Collins | BRE | 5.5 | 3.93 | 0.82 | 74 | 0.37 | 1.8 | medium |  |
| Matheus N. | MCI | 6.0 | 3.92 | 0.86 | 77 | 0.12 | 1.4 | medium |  |
| Truffert | BOU | 5.5 | 3.90 | 0.88 | 79 | 0.26 | 4.4 | medium |  |
| Van Hecke | TOT | 5.0 | 3.82 | 0.83 | 75 | 0.31 | 10.0 | medium |  |
| Milenković | NFO | 5.5 | 3.79 | 0.88 | 79 | 0.28 | 2.0 | medium |  |

### MID

| Player | Team | £ | xP | P(60+) | Mins | DefCon | Own% | Conf | Note |
|---|---|--:|--:|--:|--:|--:|--:|---|---|
| B.Fernandes | MUN | 12.0 | 5.06 | 0.95 | 82 | 0.15 | 51.8 | medium |  |
| Semenyo | MCI | 8.5 | 4.42 | 0.90 | 79 | 0.06 | 26.3 | medium |  |
| Anderson | MCI | 6.5 | 4.20 | 0.81 | 73 | 0.49 | 8.1 | medium |  |
| Rice | ARS | 7.5 | 4.12 | 0.85 | 75 | 0.30 | 18.2 | medium |  |
| Saka | ARS | 9.5 | 4.08 | 0.84 | 74 | 0.09 | 9.2 | medium |  |
| Gibbs-White | NFO | 8.0 | 4.07 | 0.86 | 76 | 0.02 | 11.7 | medium |  |
| Szoboszlai | LIV | 7.0 | 3.82 | 0.83 | 74 | 0.19 | 41.7 | medium |  |
| Palmer | CHE | 9.5 | 3.81 | 0.83 | 73 | 0.04 | 10.3 | medium |  |
| Rogers | CHE | 7.5 | 3.80 | 0.86 | 76 | 0.05 | 24.6 | medium |  |
| Cunha | MUN | 8.0 | 3.79 | 0.81 | 72 | 0.09 | 10.2 | medium |  |
| Enzo | CHE | 7.0 | 3.71 | 0.82 | 74 | 0.07 | 5.0 | medium |  |
| Mbeumo | MUN | 8.0 | 3.65 | 0.82 | 73 | 0.02 | 38.5 | medium |  |

### FWD

| Player | Team | £ | xP | P(60+) | Mins | DefCon | Own% | Conf | Note |
|---|---|--:|--:|--:|--:|--:|--:|---|---|
| Haaland | MCI | 15.5 | 5.24 | 0.94 | 81 | - | 69.5 | medium |  |
| Thiago | BRE | 8.0 | 3.89 | 0.76 | 70 | 0.03 | 17.1 | medium |  |
| Watkins | AVL | 8.0 | 3.54 | 0.71 | 65 | - | 10.3 | medium |  |
| João Pedro | CHE | 7.5 | 3.48 | 0.64 | 60 | - | 64.4 | low |  |
| Gyökeres | ARS | 7.5 | 3.00 | 0.57 | 54 | - | 9.3 | low |  |
| Calvert-Lewin | LEE | 6.0 | 2.55 | 0.50 | 49 | - | 31.3 | low |  |
| Isak | LIV | 9.0 | 2.45 | 0.43 | 45 | - | 16.6 | low |  |
| Mateta | CRY | 6.5 | 2.39 | 0.45 | 45 | - | 5.7 | low |  |
| Evanilson | BOU | 6.0 | 2.34 | 0.51 | 49 | - | 2.2 | low |  |
| Igor Jesus | NFO | 6.0 | 2.06 | 0.42 | 41 | - | 4.4 | low |  |
| Richarlison | TOT | 6.0 | 2.01 | 0.32 | 34 | 0.02 | 3.2 | low |  |
| Woltemade | NEW | 6.0 | 1.98 | 0.37 | 37 | - | 1.7 | low |  |
