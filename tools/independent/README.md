# Independent model v3.1 + multi-GW planner

A deliberately simple second model, kept out of `src/` so it stays an independent cross-check of `src/project.py`, plus the multi-gameweek, chip-aware transfer planner that `src/transfers.py` does not have.

## Run

```
python tools/independent/plan.py --ft 1                      # next GW, live data
python tools/independent/plan.py --ft 2 --max-transfers 3    # allow up to 3 moves (hits cost 4)
python tools/independent/plan.py --ft 1 --bb 7               # plan with Bench Boost in GW7
python tools/independent/plan.py --ft 1 --avail "Joao Pedro:CHE=0,0.35,0.9"   # news the FPL flag has not priced
```

Free transfers are not in the public API: read them from the app. Each run caches its download under the temp dir (`--cache DIR` to reuse one). Needs `pulp`.

## Model (per player, per fixture)

- **Teams:** current-season xG for/against per match, shrunk to the league mean with k = 3.5 matches. Fixture lambda = att x (opp_def / league)^0.85 x 1.08 home / 0.93 away.
- **Rates** (xG, xA, saves, bonus, DefCon per 90): minutes-weighted blend of this season and a prior (last season x1.0, the one before x0.5, seasons with 600+ minutes; DefCon uses 2025/26 only). No PL history: position/price prior at half weight.
- **Minutes:** last four matches weighted 0.4 / 0.6 / 0.8 / 1.0, blended with last season's minutes/38 (worth 0.6 of a match), scaled by FPL status/chance or `--avail`.
- **Points:** appearance, goals, assists, clean sheets from exp(-lambda against), goals conceded and saves via Poisson floors, DefCon as a logistic on expected actions vs the 10/12 threshold, bonus per 90 x 0.85.

## Planner

Integer program over the horizon (default 6 GWs, weights 1.0 / 0.9 / 0.85 / 0.8 / 0.75 / 0.7): one transfer window now, best XI and captain per GW, bench at 0.1 (in full in the `--bb` week), hits at -4. It prints the best plan for every transfer count from 0 to `--max-transfers`, so the marginal value of each move is visible.

## Status and limits

- Used for the GW5 decision (`logs/2026-27/GW5.md`). Not yet backtested against `minutes_x_ppm`: a cross-check, not ground truth.
- No joint simulation (teammate correlation ignored), no price-change model, one season of DefCon data, team ratings from few matches early in the season.
- Only the current transfer window is optimised; rolled free transfers are not valued explicitly. Compare the per-count objectives against roughly 1.5-2.5 points per banked transfer.
