"""Sweep residual-quantile buffers on the corrected-billing Q3 pipeline.

Does not overwrite result3.xlsx. Writes Q3_new/outputs/buffer_sweep.csv
and buffer_diagnostics.csv. Do not git push.
"""
from __future__ import annotations

import sys
import time
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_corrected as rc  # noqa: E402


OUTPUT_DIR = HERE / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPDATE_SUBSETS = [
    subset
    for subset_size in range(4)
    for subset in combinations(rc.ISSUE_HOURS[1:], subset_size)
]


def subset_label(subset: tuple[int, ...]) -> str:
    if not subset:
        return "00:00 only"
    return " + ".join(f"{hour:02d}:00" for hour in subset)


def quantile_label(value: float | None) -> str:
    return "none" if value is None else f"{value:.2f}"


def summarize_policy(policy: dict) -> dict[str, float]:
    series = rc.policy_summary(policy)
    return {
        "total_cost": float(series["total cost (yuan)"]),
        "plan_cost": float(series["planned purchase cost (yuan)"]),
        "adjustment_cost": float(series["adjustment cost (yuan)"]),
        "emergency_cost": float(series["emergency cost (yuan)"]),
        "plan_kwh": float(series["planned energy (kWh)"]),
        "final_kwh": float(series["final purchased energy (kWh)"]),
        "upward_kwh": float(series["upward adjustment (kWh)"]),
        "downward_kwh": float(series["downward adjustment (kWh)"]),
        "emergency_kwh": float(series["emergency energy (kWh)"]),
        "spill_kwh": float(series["unused surplus (kWh)"]),
        "emergency_days": float(series["days with emergency purchase"]),
    }


def buffer_diagnostics() -> pd.DataFrame:
    """How large the buffer is, and how often actual net-load stays under it."""
    rows = []
    for issue_hour in rc.ISSUE_HOURS:
        start = rc.ISSUE_STARTS[issue_hour]
        raw = rc.FORECASTS_BY_ISSUE[issue_hour]["net_kwh"][rc.EVAL_DAYS]
        actual = rc.NET_KWH[rc.EVAL_DAYS, start:]
        residual = actual - raw
        for quantile in (0.50, 0.60, 0.70, 0.80, 0.90, None):
            if quantile is None:
                buffered = raw
                buffer = np.zeros_like(raw)
                label = "none"
            else:
                buffer = np.vstack(
                    [rc.residual_buffer(int(day), issue_hour, quantile) for day in rc.EVAL_DAYS]
                )
                buffered = raw + buffer
                label = f"{quantile:.2f}"
            rows.append(
                {
                    "issue": f"{issue_hour:02d}:00",
                    "quantile": label,
                    "mean_buffer_kwh": float(buffer.mean()),
                    "median_buffer_kwh": float(np.median(buffer)),
                    "p90_buffer_kwh": float(np.quantile(buffer, 0.90)),
                    "mean_raw_net_kwh": float(raw.mean()),
                    "mean_actual_net_kwh": float(actual.mean()),
                    "mean_residual_kwh": float(residual.mean()),
                    "coverage": float((actual <= buffered + 1e-9).mean()),
                    "mae_raw_kwh": float(np.abs(residual).mean()),
                    "mae_buffered_kwh": float(np.abs(actual - buffered).mean()),
                    "mean_underage_kwh": float(np.maximum(actual - buffered, 0.0).mean()),
                    "mean_overage_kwh": float(np.maximum(buffered - actual, 0.0).mean()),
                }
            )
    return pd.DataFrame(rows)


def hourly_buffer_profile(issue_hour: int = 0, quantile: float = 0.80) -> pd.DataFrame:
    """Mean 00:00 buffer by hour of day, evaluation period only."""
    start = rc.ISSUE_STARTS[issue_hour]
    buffers = np.vstack(
        [rc.residual_buffer(int(day), issue_hour, quantile) for day in rc.EVAL_DAYS]
    )
    hour_index = np.minimum(
        (np.arange(start, rc.INTERVALS_PER_DAY) * rc.INTERVAL_HOURS).astype(int),
        23,
    )
    rows = []
    for hour in range(24):
        mask = hour_index == hour
        if not mask.any():
            continue
        rows.append(
            {
                "hour": hour,
                "mean_buffer_kwh": float(buffers[:, mask].mean()),
                "mean_buffer_kw": float(buffers[:, mask].mean() / rc.INTERVAL_HOURS),
            }
        )
    return pd.DataFrame(rows)


def run_one(plan_q: float | None, adj_q: float | None) -> list[dict]:
    static_policy, rolling_policy = rc.run_backtest(plan_q, adj_q)
    rows = []
    for subset in UPDATE_SUBSETS:
        policy = rc.combine_update_subset(subset, static_policy, rolling_policy)
        summary = summarize_policy(policy)
        summary.update(
            {
                "plan_quantile": quantile_label(plan_q),
                "adj_quantile": quantile_label(adj_q),
                "updates": subset_label(subset),
            }
        )
        rows.append(summary)
    return rows


def main() -> None:
    print("Building buffer diagnostics (no LP)...")
    diagnostics = buffer_diagnostics()
    diagnostics.to_csv(OUTPUT_DIR / "buffer_diagnostics.csv", index=False, encoding="utf-8-sig")
    print(diagnostics.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    profile = hourly_buffer_profile(0, 0.80)
    profile.to_csv(OUTPUT_DIR / "buffer_hourly_00_q80.csv", index=False, encoding="utf-8-sig")
    print("\n00:00 q=0.80 mean buffer by hour (kW):")
    print(profile.to_string(index=False, float_format=lambda x: f"{x:,.1f}"))

    # 1-D around the teammate pair, plus a small 2-D grid and the no-buffer case.
    jobs: list[tuple[float | None, float | None]] = []
    seen: set[tuple[str, str]] = set()

    def add(plan_q: float | None, adj_q: float | None) -> None:
        key = (quantile_label(plan_q), quantile_label(adj_q))
        if key not in seen:
            seen.add(key)
            jobs.append((plan_q, adj_q))

    add(0.80, 0.70)  # teammate
    add(None, None)  # raw forecast, no buffer
    for plan_q in (0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90):
        add(plan_q, 0.70)
    for adj_q in (0.50, 0.60, 0.70, 0.80, 0.90):
        add(0.80, adj_q)
    for plan_q in (0.70, 0.75, 0.80, 0.85):
        for adj_q in (0.60, 0.70, 0.80):
            add(plan_q, adj_q)

    print(f"\nRunning {len(jobs)} full-year backtests...")
    all_rows: list[dict] = []
    t0 = time.perf_counter()
    for i, (plan_q, adj_q) in enumerate(jobs, start=1):
        job_t0 = time.perf_counter()
        rows = run_one(plan_q, adj_q)
        all_rows.extend(rows)
        best = min(rows, key=lambda r: r["total_cost"])
        print(
            f"[{i}/{len(jobs)}] plan={quantile_label(plan_q)} adj={quantile_label(adj_q)} "
            f"best={best['updates']} cost={best['total_cost']:,.2f} "
            f"emerg={best['emergency_kwh']:,.0f} kWh "
            f"({time.perf_counter() - job_t0:.1f}s)"
        )

    table = pd.DataFrame(all_rows)
    table = table.sort_values(["total_cost", "plan_quantile", "adj_quantile", "updates"])
    table.to_csv(OUTPUT_DIR / "buffer_sweep.csv", index=False, encoding="utf-8-sig")
    print(f"\nWrote {OUTPUT_DIR / 'buffer_sweep.csv'} in {time.perf_counter() - t0:.1f}s")

    focus = table[table["updates"].isin(["00:00 only", "06:00 + 12:00"])].copy()
    print("\nFocus: 00:00-only and 06:00+12:00")
    cols = [
        "plan_quantile",
        "adj_quantile",
        "updates",
        "total_cost",
        "plan_cost",
        "adjustment_cost",
        "emergency_cost",
        "plan_kwh",
        "downward_kwh",
        "upward_kwh",
        "emergency_kwh",
        "spill_kwh",
    ]
    print(focus[cols].to_string(index=False, float_format=lambda x: f"{x:,.2f}"))


if __name__ == "__main__":
    main()
