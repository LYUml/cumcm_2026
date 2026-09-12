"""Second-round Q4-2 robustness experiments on the leading price models."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04_q4/scripts"))
sys.path.insert(0, str(ROOT / "02_q2/src"))
from q2_model import read_inputs  # noqa: E402
from run_q4_2_comparison import (  # noqa: E402
    START_DAY, generate_price_forecasts, read_prices, run_policy,
)

OUT = ROOT / "04_q4/outputs/q4_2_robustness"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dates, load, pv, _ = read_inputs(ROOT)
    net = load - pv
    prices = read_prices()
    forecasts, _ = generate_price_forecasts(prices, dates)

    # The first round eliminated the one-week model.  Keep the empirical winner
    # and the strongest regularized model, then isolate modeling choices.
    # Continue only the informative cells after the first partial sweep.  The
    # default f3000/p4.5 results already exist in the first-round comparison.
    configs = [
        ("weekday_mean_4w", "joint", "net", 3000.0, 5.0),
        ("weekday_mean_4w", "joint", "net", 6000.0, 4.0),
        ("weekday_mean_4w", "joint", "net", 6000.0, 4.5),
        ("weekday_mean_4w", "joint", "net", 6000.0, 5.0),
        # Same aggressive setting for Ridge, testing whether the conclusion is
        # driven by the price forecaster or by the reserve/penalty pair.
        ("ridge_arx", "joint", "net", 1200.0, 5.0),
        # Point-price and joint-tree ablations at the Q2 reference settings.
        ("weekday_mean_4w", "point", "net", 3000.0, 4.5),
        ("ridge_arx", "point", "net", 3000.0, 4.5),
        ("weekday_mean_4w", "joint", "joint", 3000.0, 4.5),
        ("ridge_arx", "joint", "joint", 3000.0, 4.5),
    ]

    partial_path = OUT / "robustness_comparison_partial.csv"
    records = (pd.read_csv(partial_path).to_dict("records")
               if partial_path.exists() else [])
    for i, (model, price_mode, tree_signal, floor, penalty) in enumerate(configs, 1):
        tag = f"{model}_{price_mode}_{tree_signal}_f{floor:g}_p{penalty:g}"
        print(f"CONFIG {i}/{len(configs)} {tag}", flush=True)
        rows, grids, traces, _, seconds = run_policy(
            tag, forecasts[model], prices, dates, load, pv, net,
            price_mode=price_mode, terminal_floor=floor,
            planning_penalty=penalty, tree_signal=tree_signal,
        )
        eval_dates = dates[START_DAY:]
        train_mask = eval_dates < "2025-07-01"
        test_mask = ~train_mask
        record = dict(
            model=model, price_mode=price_mode, tree_signal=tree_signal,
            terminal_floor_kwh=floor, planning_penalty=penalty,
            full_total_yuan=float(rows[:, 2].sum()),
            selection_period_total_yuan=float(rows[train_mask, 2].sum()),
            holdout_period_total_yuan=float(rows[test_mask, 2].sum()),
            planned_yuan=float(rows[:, 0].sum()),
            emergency_yuan=float(rows[:, 1].sum()),
            emergency_kwh=float(rows[:, 3].sum()), seconds=seconds,
            min_soc_kwh=float(traces[:, :, 1].min()),
            max_soc_kwh=float(traces[:, :, 1].max()),
        )
        records.append(record)
        pd.DataFrame(records).to_csv(OUT / "robustness_comparison_partial.csv", index=False)
        print(json.dumps(record), flush=True)

    table = pd.DataFrame(records)
    table.to_csv(OUT / "robustness_comparison.csv", index=False)
    eligible = table[(table.price_mode == "joint") & (table.tree_signal == "net")]
    selected = eligible.sort_values("selection_period_total_yuan").iloc[0]
    holdout_rank = eligible.sort_values("holdout_period_total_yuan").reset_index(drop=True)
    conclusion = {
        "selection_period": ["2025-02-01", "2025-06-30"],
        "holdout_period": ["2025-07-01", "2025-12-31"],
        "selected_on_first_period": selected.to_dict(),
        "selected_holdout_rank": int(holdout_rank.index[
            (holdout_rank.model == selected.model)
            & (holdout_rank.terminal_floor_kwh == selected.terminal_floor_kwh)
            & (holdout_rank.planning_penalty == selected.planning_penalty)
        ][0]) + 1,
        "best_holdout_configuration": holdout_rank.iloc[0].to_dict(),
    }
    (OUT / "robustness_conclusion.json").write_text(
        json.dumps(conclusion, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(table.sort_values("full_total_yuan").head(12).to_string(index=False))
    print(json.dumps(conclusion, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
