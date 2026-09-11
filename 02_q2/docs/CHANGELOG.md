# Q2 corrected delivery changelog

## What changed

- Anchored all 144 source columns to the official `result2.xlsx` interval headers. Source label 00:10 is treated as the left endpoint of 00:10-00:20; index 143 is 00:00-00:10 on the next date.
- Added the full source-label/physical-interval/index/workbook-column/state mapping.
- Recomputed the selected four-hour-tree policy. The 00:00 decision is now made before the preceding row's final 00:00-00:10 interval is replayed, removing the old use of the realized 00:10 state.
- Corrected emergency interval labels and the figure axis. Natural-day four-hour storage summaries now cross adjacent purchase rows and cover exactly 00:00-24:00.
- Saved all planning charge, discharge, storage, emergency, and spill variables, plus executed trajectories.
- Added planning-versus-feedback replay diagnostics, future-data perturbation tests, and the four required-date result tables.
- Updated the English manuscript to separate overall cost, matched-parameter comparison, sensitivity, and execution validation; removed strict-optimality language and retained the 3000 kWh condition only as a planning reserve.
- Resynchronized the manuscript after the corrected-data rerun: the authoritative cost table now contains only the corrected policy, archived comparisons are explicitly labeled as legacy evidence, the physical midnight execution order is stated correctly, all four required-date storage tables are included, and figure/evidence paths match the modular directory layout.
- Added `scripts/validate_paper.py` to detect stale headline costs, missing required dates, and broken final-figure paths after future reruns.

## Recalculation and cost change

The selected policy was recalculated. Legacy total cost was CNY 13,785,890.36. Corrected planned, emergency, and total costs are CNY 13,171,963.91, CNY 618,266.63, and CNY 13,790,230.54, respectively. The corrected total is CNY 4,340.18 higher (+0.0315%). Old outputs remain untouched outside this directory.

## Validation completed

- Energy balance, storage recursion, inter-row state linkage, capacity, power limits, simultaneous charging/discharging, emergency-with-actual-charging, official workbook totals, CSV/NPZ consistency, requested-date extraction, and future-data prefix causality.
- Actual midnight state is below 3000 kWh on 68 days.
- The planning surrogate has zero simultaneous charge/discharge but 15,260 scenario intervals with emergency purchase and charging. Scenario feedback replay has 452 terminal states below 3000 kWh; maximum terminal-state difference is 5573.44 kWh.

## Remaining source ambiguity

Neither the problem statement nor Attachments 1/2 explicitly says whether timestamps are samples or interval representatives. The official template uniquely supports the left-end convention without inventing 2026 data, so that convention is used. This assumption must remain disclosed. The exact interpretation of the unrepresented 00:00-00:10 interval on 1 January is not recoverable from the supplied files; the stated 6000 kWh initial state is used at 00:00 and January is a causal warm-up.
