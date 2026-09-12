# Question 4 workspace

The current scope is Q4-2: rerun the authoritative Q2 policy under uncertain,
time-varying prices.  Price forecasts are causal, candidate models are compared
under one common Q2 scenario-tree controller, and realized settlement uses the
actual prices in Attachment 4.

Run:

```bash
python3 04_q4/scripts/run_q4_2_comparison.py
```

Outputs are written to `04_q4/outputs/q4_2_comparison/`.
