# Reproduction

From the repository root:

```bash
python3 02_q2/scripts/run_final.py
python3 02_q2/scripts/run_model_comparison.py
python3 02_q2/scripts/make_delivery.py
python3 02_q2/scripts/validate_paper.py
```

To regenerate figures only:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 02_q2/scripts/figures/make_cost_figures.py
PYTHONDONTWRITEBYTECODE=1 python3 02_q2/scripts/figures/make_example_figure.py
```

Final figures are written to `02_q2/outputs/figures/`. `paper/Q2_PRISM` is an intentionally extensionless plain-text exchange file, not a LaTeX source.

Recorded environment: macOS arm64; Python 3.13.11; NumPy 2.5.2; pandas 3.0.5; SciPy 1.18.1; scikit-learn 1.9.0; Matplotlib 3.11.1. Optimization uses `scipy.optimize.linprog(method="highs")`.

The run is deterministic: K-means uses `random_state=0, n_init=20`. The comparison adds Separate Q0.5, Direct Q0.8, Separate Q0.8, fixed-action scenarios, and the two-stage relaxation to the selected four-hour tree. At midnight, row `d-1` slot 143 is explicitly unavailable to every forecast and scenario builder.
