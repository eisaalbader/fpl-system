# What was added, and what was measured

| File | Status | Tested against |
|---|---|---|
| `src/baselines.py` | ✅ working | 185,964 rows, 7 seasons |
| `src/backtest.py` | ✅ working | 6 held-out seasons, leakage guard passes |
| `src/bps.py` | ✅ working | 2025-26, 11,498 played rows, 380 fixtures |
| `src/purchase_price.py` | ✅ logic verified | FPL sell-value rule |
| `src/ft_guard.py` | ✅ logic verified | synthetic picks diffs |
| `src/odds.py` | ⚠️ **math validated, live fetch NOT run** | synthetic round-trip only |
| `.github/workflows/backtest.yml` | ⚠️ not yet run in Actions | — |
| `BRIEF_TEMPLATE.md` | spec | — |

`odds.py` could not be run against football-data.co.uk because that host is
blocked from the environment it was written in. It will work in Actions. Do not
merge it into `project.py` until `python src/odds.py --backtest` has actually
been run and beaten the incumbent clean sheet model.

## The accuracy bar (mean, 6 held-out seasons, players who appeared)

| model | MAE | spearman | top20_hit | captain_capture |
|---|--:|--:|--:|--:|
| xgi | **1.894** | 0.256 | 0.149 | 0.298 |
| ppg | 2.090 | 0.285 | 0.171 | 0.351 |
| minutes_x_ppm | 2.104 | **0.301** | 0.171 | **0.368** |
| form5 | 2.157 | 0.279 | 0.157 | 0.335 |
| price | 2.242 | 0.197 | **0.181** | 0.336 |
| naive_last | 2.566 | 0.233 | 0.152 | 0.243 |

`project.py` must beat **minutes_x_ppm** on spearman / captain_capture. It has
not been scored yet.

## BPS: the flat 0.6 damp was wrong

Recovered 2025-26 weights by regression (R² 0.82–0.93). CBI came out at
+0.478 BPS/action — independent confirmation of the old "1 per 2" rule.
After applying 2026/27 deltas and re-ranking within fixture:

**DEF 0.93 · MID 1.01 · FWD 1.02 · GKP unresolved (0.77–1.85)**

The real change is far smaller than 40%. GKP is left at 0.60 because it depends
on an unobservable term.
