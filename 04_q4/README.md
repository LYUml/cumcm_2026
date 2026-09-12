# Question 4 workspace

Q4-2 reruns the authoritative Q2 policy under uncertain, time-varying prices.
Q4-3 then combines the selected causal price model with the Q3 rolling
PV/purchase controller. In both cases forecasts affect decisions, while final
settlement always uses the realized prices in Attachment 4.

Run:

```bash
python3 04_q4/scripts/run_q4_2_comparison.py
```

Outputs are written to `04_q4/outputs/q4_2_comparison/`.

The formal Q4-3 model directly extends Q4-2's paired scenario-tree LP and
requires `openpyxl` in addition to the scientific Python stack:

```bash
python3 04_q4/scripts/run_q4_3_stochastic.py
```

Outputs, including `result4-3.xlsx`, are written to
`04_q4/outputs/q4_3_stochastic/`. `run_q4_3.py` and `outputs/q4_3/` are retained
only as the deprecated deterministic-Q3 ablation and must not be cited as the
formal answer.
