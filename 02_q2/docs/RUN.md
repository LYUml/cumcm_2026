# Reproduction

From the repository root:

```bash
python3 02_q2/scripts/run_final.py
python3 02_q2/scripts/make_delivery.py
python3 02_q2/scripts/validate_paper.py
```

Recorded environment: macOS arm64; Python 3.13.11; NumPy 2.5.2; pandas 3.0.5; SciPy 1.18.1; scikit-learn 1.9.0; Matplotlib 3.11.1. Optimization uses `scipy.optimize.linprog(method="highs")`.

The run is deterministic: K-means uses `random_state=0, n_init=20`. It takes roughly one minute on the recorded machine.
