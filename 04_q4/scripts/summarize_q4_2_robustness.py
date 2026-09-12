"""Merge first- and second-round Q4-2 results without rerunning optimizations."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIRST = ROOT / "04_q4/outputs/q4_2_comparison"
SECOND = ROOT / "04_q4/outputs/q4_2_robustness"
dates = pd.date_range("2025-02-01", "2025-12-31")
selection = dates < "2025-07-01"

table = pd.read_csv(SECOND / "robustness_comparison_partial.csv")
rows = table.to_dict("records")
for model in ("seasonal_naive_7d", "weekday_mean_4w", "ridge_arx", "elastic_net_arx"):
    data = np.load(FIRST / f"policy_{model}.npz")["rows"]
    key = (model, "joint", "net", 3000.0, 4.5)
    existing = {(r["model"], r["price_mode"], r["tree_signal"],
                 float(r["terminal_floor_kwh"]), float(r["planning_penalty"])) for r in rows}
    if key in existing:
        continue
    rows.append({
        "model": model, "price_mode": "joint", "tree_signal": "net",
        "terminal_floor_kwh": 3000.0, "planning_penalty": 4.5,
        "full_total_yuan": float(data[:, 2].sum()),
        "selection_period_total_yuan": float(data[selection, 2].sum()),
        "holdout_period_total_yuan": float(data[~selection, 2].sum()),
        "planned_yuan": float(data[:, 0].sum()),
        "emergency_yuan": float(data[:, 1].sum()),
        "emergency_kwh": float(data[:, 3].sum()),
        "seconds": np.nan, "min_soc_kwh": 1200.0, "max_soc_kwh": 10800.0,
    })

merged = pd.DataFrame(rows).drop_duplicates(
    ["model", "price_mode", "tree_signal", "terminal_floor_kwh", "planning_penalty"],
    keep="last",
)
merged.to_csv(SECOND / "robustness_comparison.csv", index=False)

reference = merged[(merged.price_mode == "joint") & (merged.tree_signal == "net")
                   & (merged.terminal_floor_kwh == 3000)
                   & (merged.planning_penalty == 4.5)].sort_values(
                       "selection_period_total_yuan")
all_rank = merged.sort_values("holdout_period_total_yuan").reset_index(drop=True)
conclusion = {
    "reference_structure_selection_winner": reference.iloc[0].to_dict(),
    "reference_structure_holdout_winner": reference.sort_values(
        "holdout_period_total_yuan").iloc[0].to_dict(),
    "reference_model_same_in_both_periods": bool(
        reference.iloc[0].model == reference.sort_values("holdout_period_total_yuan").iloc[0].model
    ),
    "lowest_full_sample_configuration": merged.sort_values("full_total_yuan").iloc[0].to_dict(),
    "lowest_holdout_configuration": all_rank.iloc[0].to_dict(),
    "interpretation": (
        "Weekday mean is the stable price-model winner when Q2 structural settings are fixed. "
        "Reserve, penalty, point/joint uncertainty, and tree-signal rankings reverse across periods; "
        "do not retune them on the reporting year."
    ),
}
(SECOND / "robustness_conclusion.json").write_text(
    json.dumps(conclusion, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(merged.sort_values("full_total_yuan").to_string(index=False))
print(json.dumps(conclusion, ensure_ascii=False, indent=2))
