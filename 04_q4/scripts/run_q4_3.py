"""Deprecated deterministic Q4-3 comparison; not the formal submission model.

This extends the Q3 v002 controller rather than rebuilding the earlier model:
the net-load forecasts, four issue times, contract settlement and physical
greedy battery recourse are inherited.  The fixed Q3 tariff is replaced by
causal price forecasts at 00:00 and optional intraday corrections based only
on prices observed before the current issue time.  Final accounting always
uses the realised Attachment-4 price. The formal Q4-2-consistent implementation
is ``run_q4_3_stochastic.py``. This file is retained only as an ablation record.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "03_q3/scripts"))
sys.path.insert(0, str(ROOT / "04_q4/scripts"))

import run_corrected as rc  # noqa: E402
import run_free_battery as q3  # noqa: E402
from run_q4_2_comparison import generate_price_forecasts, read_prices  # noqa: E402

OUT = ROOT / "04_q4/outputs/q4_3"
OUT.mkdir(parents=True, exist_ok=True)

ACTUAL_PRICE = read_prices()
PRICE_FORECASTS, _PRICE_MODEL_DIAGNOSTICS = generate_price_forecasts(
    ACTUAL_PRICE, rc.DATES
)
EVAL_DAYS = rc.EVAL_DAYS
SELECTION_END = pd.Timestamp("2025-06-30")


def issue_price_forecast(
    day: int,
    issue_hour: int,
    model: str,
    update: str,
    decay_hours: float = 6.0,
) -> np.ndarray:
    """Return a causal forecast from the issue slot to the end of the day.

    ``level_decay`` estimates the current-day price-level error from the last
    six observed hours and lets that correction decay over the future horizon.
    No price at or after the issue boundary enters the update.
    """
    start = rc.ISSUE_STARTS[issue_hour]
    base = PRICE_FORECASTS[model][day, start:].copy()
    if issue_hour == 0 or update == "static_midnight":
        return base
    if update != "level_decay":
        raise ValueError(update)

    lookback = 36  # six hours on the official 10-minute grid
    hist_start = max(0, start - lookback)
    realised = ACTUAL_PRICE[day, hist_start:start]
    predicted = PRICE_FORECASTS[model][day, hist_start:start]
    if realised.size == 0:
        return base
    # Median is resistant to isolated real-time price spikes.
    level_error = float(np.median(realised - predicted))
    lead = np.arange(len(base), dtype=float) * rc.INTERVAL_HOURS
    correction = level_error * np.exp(-lead / decay_hours)
    return np.maximum(base + correction, 0.0)


def price_forecast_diagnostics(model: str, update: str) -> dict:
    rows = []
    for day in EVAL_DAYS:
        for issue in rc.ISSUE_HOURS:
            start = rc.ISSUE_STARTS[issue]
            pred = issue_price_forecast(day, issue, model, update)
            actual = ACTUAL_PRICE[day, start:]
            rows.append(
                {
                    "date": rc.DATES[day],
                    "issue_hour": issue,
                    "mae": float(np.mean(np.abs(pred - actual))),
                    "rmse": float(np.sqrt(np.mean((pred - actual) ** 2))),
                }
            )
    frame = pd.DataFrame(rows)
    return {
        "rows": frame,
        "mae": float(frame.mae.mean()),
        "rmse": float(frame.rmse.mean()),
    }


def simulate_policy(
    price_model: str,
    price_update: str,
    terminal_multiplier: float = 1.0,
    oracle_price: bool = False,
    update_hours: tuple[int, ...] = (6, 12, 18),
) -> dict:
    """Run the inherited Q3 policy with causal (or oracle) price information."""
    n_days = len(rc.DATES)
    nt = rc.INTERVALS_PER_DAY
    fields = ("plan", "adjusted", "charge", "discharge", "soc", "emergency", "spill")
    arrays = {name: np.zeros((n_days, nt)) for name in fields}
    soc_open = np.zeros(n_days)
    current_soc = rc.SOC_TARGET_KWH

    for day in range(rc.MIN_FORECAST_DAY, n_days):
        soc_open[day] = current_soc
        if oracle_price:
            p0 = ACTUAL_PRICE[day].copy()
        else:
            p0 = issue_price_forecast(day, 0, price_model, price_update)
        # Value remaining SOC at the forecast overnight price.  The multiplier
        # is selected only on the first evaluation subperiod.
        terminal_value = terminal_multiplier * float(np.mean(p0[:36]))
        da = q3.solve_horizon(
            q3.target_net(day, 0, q3.Q0), p0, current_soc,
            baseline_purchase=None, terminal_value=terminal_value,
        )
        arrays["plan"][day] = da["purchase"]

        for block, issue in enumerate(rc.ISSUE_HOURS):
            start, end = rc.BLOCK_BOUNDS[block], rc.BLOCK_BOUNDS[block + 1]
            if issue == 0:
                planned = da
            elif issue in update_hours:
                p_issue = (ACTUAL_PRICE[day, start:].copy() if oracle_price else
                           issue_price_forecast(day, issue, price_model, price_update))
                planned = q3.solve_horizon(
                    q3.target_net(day, issue, q3.Q_ADJ[issue]),
                    p_issue,
                    current_soc,
                    baseline_purchase=arrays["plan"][day, start:],
                    terminal_value=terminal_value,
                )
            else:
                planned = {
                    "purchase": arrays["plan"][day, start:],
                    "charge": np.zeros(nt - start),
                    "discharge": np.zeros(nt - start),
                }

            width = end - start
            purchase = planned["purchase"][:width]
            rec = q3.greedy_recourse(
                purchase, rc.NET_KWH[day, start:end], current_soc
            )
            arrays["adjusted"][day, start:end] = purchase
            for name in ("charge", "discharge", "soc", "emergency", "spill"):
                arrays[name][day, start:end] = rec[name]
            current_soc = float(rec["soc_close"])

    idx = EVAL_DAYS
    result = {name: value[idx] for name, value in arrays.items()}
    result["soc_open"] = soc_open[idx]
    result["soc_close"] = arrays["soc"][idx, -1]
    plan = result["plan"]
    final = result["adjusted"]
    up = np.maximum(final - plan, 0.0)
    down = np.maximum(plan - final, 0.0)
    price = ACTUAL_PRICE[idx]
    result["upward"] = up
    result["downward"] = down
    result["plan_cost"] = np.sum(price * plan, axis=1)
    result["adjustment_cost"] = np.sum(price * (1.5 * up - 0.5 * down), axis=1)
    result["emergency_cost"] = np.sum(5.0 * price * result["emergency"], axis=1)
    result["total_cost"] = (
        result["plan_cost"] + result["adjustment_cost"] + result["emergency_cost"]
    )
    result["metrics"] = {
        "total_cost": float(result["total_cost"].sum()),
        "plan_cost": float(result["plan_cost"].sum()),
        "adjustment_cost": float(result["adjustment_cost"].sum()),
        "emergency_cost": float(result["emergency_cost"].sum()),
        "plan_kwh": float(plan.sum()),
        "final_kwh": float(final.sum()),
        "upward_kwh": float(up.sum()),
        "downward_kwh": float(down.sum()),
        "emergency_kwh": float(result["emergency"].sum()),
        "spill_kwh": float(result["spill"].sum()),
        "min_soc": float(result["soc"].min()),
        "max_soc": float(result["soc"].max()),
    }
    return result


def export_result(result: dict) -> Path:
    """Reuse the verified Q3 workbook writer and rename its output."""
    old_out = q3.OUTPUT_DIR
    try:
        q3.OUTPUT_DIR = OUT
        q3.write_tables(result)
        q3.write_result3(result)
    finally:
        q3.OUTPUT_DIR = old_out
    src = OUT / "result3.xlsx"
    dst = OUT / "result4-3.xlsx"
    shutil.move(src, dst)
    return dst


def main() -> None:
    tic = time.perf_counter()
    candidates = []
    results = {}
    # Q4-2's two strongest causal forecasters, with and without an intraday
    # correction.  Terminal multipliers are deliberately a small transparent grid.
    for model in ("weekday_mean_4w", "ridge_arx"):
        for update in ("static_midnight", "level_decay"):
            for multiplier in (0.75, 1.0, 1.25):
                name = f"{model}|{update}|tv={multiplier:.2f}"
                print("RUN", name, flush=True)
                result = simulate_policy(model, update, multiplier)
                results[name] = result
                selection = rc.REPORT_DAY_INDEX <= SELECTION_END
                holdout = ~selection
                row = {
                    "name": name,
                    "price_model": model,
                    "price_update": update,
                    "terminal_multiplier": multiplier,
                    **result["metrics"],
                    "selection_cost": float(result["total_cost"][selection].sum()),
                    "holdout_cost": float(result["total_cost"][holdout].sum()),
                }
                candidates.append(row)
                print(f"  total={row['total_cost']:,.2f}", flush=True)

    comparison = pd.DataFrame(candidates).sort_values("selection_cost")
    comparison.to_csv(OUT / "policy_comparison.csv", index=False, encoding="utf-8-sig")
    selected_name = str(comparison.iloc[0]["name"])
    selected = results[selected_name]

    selected_row = comparison.iloc[0]
    subset_rows = []
    for hours in ((), (6,), (6, 12), (6, 12, 18)):
        label = "+".join(map(str, hours)) if hours else "00-only"
        print("RUN update subset", label, flush=True)
        subset_result = simulate_policy(
            str(selected_row["price_model"]),
            str(selected_row["price_update"]),
            float(selected_row["terminal_multiplier"]),
            update_hours=hours,
        )
        subset_rows.append({
            "updates": label,
            **subset_result["metrics"],
        })
    pd.DataFrame(subset_rows).sort_values("total_cost").to_csv(
        OUT / "update_subset_comparison.csv", index=False, encoding="utf-8-sig"
    )

    print("RUN perfect-price information benchmark", flush=True)
    oracle = simulate_policy("weekday_mean_4w", "static_midnight", 1.0, oracle_price=True)
    oracle_row = {"name": "perfect_price_information", **oracle["metrics"]}
    pd.DataFrame([oracle_row]).to_csv(OUT / "oracle_benchmark.csv", index=False)

    diagnostic_rows = []
    for model in ("weekday_mean_4w", "ridge_arx"):
        for update in ("static_midnight", "level_decay"):
            diag = price_forecast_diagnostics(model, update)
            diagnostic_rows.append({
                "price_model": model, "price_update": update,
                "mean_issue_mae": diag["mae"], "mean_issue_rmse": diag["rmse"],
            })
            diag["rows"].to_csv(
                OUT / f"price_diagnostics_{model}_{update}.csv", index=False
            )
    pd.DataFrame(diagnostic_rows).to_csv(OUT / "price_forecast_comparison.csv", index=False)

    np.savez_compressed(
        OUT / "selected_policy.npz",
        **{k: v for k, v in selected.items() if isinstance(v, np.ndarray)},
    )
    workbook = export_result(selected)
    summary = {
        "selected_on": "2025-02-01 to 2025-06-30",
        "selected_policy": selected_name,
        "selected_metrics": selected["metrics"],
        "holdout_cost_yuan": float(selected["total_cost"][rc.REPORT_DAY_INDEX > SELECTION_END].sum()),
        "oracle_information_benchmark": oracle["metrics"],
        "workbook": str(workbook),
        "elapsed_s": time.perf_counter() - tic,
        "causality": "At each issue time, only earlier realised prices and forecasts based on earlier days are used; settlement uses Attachment 4 actual prices.",
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
