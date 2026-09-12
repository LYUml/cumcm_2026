# Q2 corrected delivery changelog

## Cost-figure layout revision

- Updated the median-cost example to a 6 × 4.65-inch three-panel layout, matching the cost-figure typography. All 144 interval values now use 145 explicit edges; the final next-day 00:00–00:10 interval is fully drawn. An annotation identifies the observed 20:40 lower-bound state and emergency episode ending at 22:10.
- Example-only regeneration: `PYTHONDONTWRITEBYTECODE=1 python3 02_q2/scripts/figures/make_example_figure.py`.

- Replaced correction-increment lollipops with signed horizontal bars; hatching identifies the total.
- Reserved a right-aligned numeric column in the six-policy figure, moved legends above the data, and removed top/right borders.
- Used 6-inch canvases and explicitly sized text for the Prism manuscript. Numeric labels are checked against rendered axes bounds before export.
- Cost-only regeneration: `PYTHONDONTWRITEBYTECODE=1 python3 02_q2/scripts/figures/make_cost_figures.py`. The delivery pipeline calls the same module.
- Final PDF/PNG files now live only in `outputs/figures/`. The redundant pre-layout figure directory was moved to the macOS Trash during cleanup; the broader pre-cleanup state remains in `archive/legacy_snapshot.zip`.

## Folder cleanup and modularization

- Separated model code (`src/`), runnable pipelines (`scripts/`), figure generators (`scripts/figures/`), manuscript files (`paper/`), and generated figures (`outputs/figures/`).
- Kept `paper/Q2_PRISM` as an extensionless Prism exchange text. It is intentionally not treated as a TeX source.
- Removed generated caches and duplicate superseded figure files while retaining `archive/legacy_snapshot.zip` for recovery.

## What changed

- Anchored all 144 source columns to the official `result2.xlsx` interval headers. Source label 00:10 is treated as the left endpoint of 00:10-00:20; index 143 is 00:00-00:10 on the next date.
- Added the full source-label/physical-interval/index/workbook-column/state mapping.
- Recomputed the selected four-hour-tree policy. In addition to committing before the pending 00:00-00:10 interval is replayed, forecasting now excludes that still-unobserved cell from the recent-PV statistic, complete residual pool, and January persistence rule.
- Restored and recomputed six policies under this same strict boundary: Separate Q0.5, Direct Q0.8, Separate Q0.8, fixed-action scenarios, four-hour tree, and two-stage relaxation. Full daily and NPZ traces are in `outputs/model_comparison/`.
- Corrected emergency interval labels and the figure axis. Natural-day four-hour storage summaries now cross adjacent purchase rows and cover exactly 00:00-24:00.
- Saved all planning charge, discharge, storage, emergency, and spill variables, plus executed trajectories.
- Added planning-versus-feedback replay diagnostics, future-data perturbation tests, and the four required-date result tables.
- Updated the English manuscript to separate overall cost, matched-parameter comparison, sensitivity, and execution validation; removed strict-optimality language and retained the 3000 kWh condition only as a planning reserve.
- Resynchronized the manuscript after the corrected-data rerun: the authoritative cost table now contains only the corrected policy, archived comparisons are explicitly labeled as legacy evidence, the physical midnight execution order is stated correctly, all four required-date storage tables are included, and figure/evidence paths match the modular directory layout.
- Added `scripts/validate_paper.py` to detect stale headline costs, missing required dates, and broken final-figure paths after future reruns.
- Reworked both paper data figures with the installed vivid-figures workflow: the chronology figure now separates absolute cost composition from the small correction increment, and the representative-day figure now shows supply, signed battery action, and stored energy in aligned panels. The style helper is vendored in `src/plot_utils.py` so Q2 remains self-contained.

## Recalculation and cost change

The selected policy was recalculated. Legacy total cost was CNY 13,785,890.36. Strict-causal planned, emergency, and total costs are CNY 13,163,054.77, CNY 730,154.55, and CNY 13,893,209.32, respectively. The corrected total is CNY 107,318.96 higher (+0.7785%). Old outputs remain preserved in the archive.

## Validation completed

- Energy balance, storage recursion, inter-row state linkage, capacity, power limits, simultaneous charging/discharging, emergency-with-actual-charging, official workbook totals, CSV/NPZ consistency, requested-date extraction, and future-data prefix causality.
- Actual midnight state is below 3000 kWh on 74 days.
- The planning surrogate has zero simultaneous charge/discharge but 15,200 scenario intervals with emergency purchase and charging. Scenario feedback replay has 478 terminal states below 3000 kWh; maximum terminal-state difference is 5392.32 kWh.
- Added a targeted perturbation test for row `d-1`, slot 143. Scenarios and the midnight purchase plan remain bitwise unchanged when that unavailable measurement is altered.

## Remaining source ambiguity

Neither the problem statement nor Attachments 1/2 explicitly says whether timestamps are samples or interval representatives. The official template uniquely supports the left-end convention without inventing 2026 data, so that convention is used. This assumption must remain disclosed. The exact interpretation of the unrepresented 00:00-00:10 interval on 1 January is not recoverable from the supplied files; the stated 6000 kWh initial state is used at 00:00 and January is a causal warm-up.
