# Question 2 workspace

This directory contains one authoritative corrected Q2 implementation and one compact legacy snapshot.

## Structure

- `src/` — reusable models, availability rules, time mapping, plotting utilities, and the small legacy comparison input used by the chronology figure.
- `scripts/` — executable final, comparison, delivery, and validation pipelines.
- `scripts/figures/` — figure generators only; they read authoritative outputs and do not solve the model.
- `paper/Q2_PAPER_ENGLISH.md` — current English manuscript source.
- `paper/Q2_PRISM` — extensionless plain-text exchange copy for Prism; it is intentionally not a `.tex` file.
- `outputs/` — authoritative workbook, CSV/NPZ/JSON results.
- `outputs/figures/` — final PNG and vector PDF figures.
- `docs/` — reproduction instructions and changelog.
- `archive/legacy_snapshot.zip` — preserved pre-cleanup files and old results. No production script reads this archive.

## Final commands

```bash
python3 02_q2/scripts/run_final.py
python3 02_q2/scripts/run_model_comparison.py
python3 02_q2/scripts/make_delivery.py
python3 02_q2/scripts/validate_paper.py
```

Do not copy results from `archive/legacy_snapshot.zip` into the paper without rerunning and reconciling their time convention.
