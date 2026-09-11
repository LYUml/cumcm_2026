# Question 2 workspace

This directory contains one authoritative corrected Q2 implementation and a separate legacy archive.

## Structure

- `src/` — reusable model, stochastic policy, time mapping, and the one small legacy comparison input required by the comparison figure.
- `scripts/` — executable final pipeline. Run `run_final.py`, then `make_delivery.py`.
- `paper/` — the current English Q2 manuscript only.
- `outputs/` — authoritative workbook, CSV/NPZ/JSON results, and PNG/PDF figures.
- `docs/` — reproduction instructions and changelog.
- `archive/legacy/` — superseded experiments, drafts, validation outputs, and the pre-cleanup delivery ZIP. Nothing here is used by `run_final.py`.

## Final commands

```bash
python3 02_q2/scripts/run_final.py
python3 02_q2/scripts/make_delivery.py
python3 02_q2/scripts/validate_paper.py
```

Do not copy results from `archive/legacy/` into the paper without rerunning and reconciling their time convention.
