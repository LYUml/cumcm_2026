"""Prepare audited cell values for the official Q4-2 workbook template."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02_q2/src"))
sys.path.insert(0, str(ROOT / "02_q2/scripts"))
from q2_model import DT_HOURS, read_inputs  # noqa: E402
from q2_near_optimal import execute_feedback  # noqa: E402
from q2_time_mapping import interval_label  # noqa: E402
from run_final import warmup, one_interval  # noqa: E402

SOURCE = ROOT / "04_q4/outputs/q4_2_comparison/policy_weekday_mean_4w.npz"
OUT = ROOT / "04_q4/outputs/final"


def merge_emergency(values: np.ndarray) -> list[tuple[str, float]]:
    groups = []
    i = 0
    while i < 144:
        if values[i] <= 1e-7:
            i += 1
            continue
        j = i + 1
        while j < 144 and values[j] > 1e-7:
            j += 1
        start = interval_label(i).split("-")[0]
        end = interval_label(j - 1).split("-")[1]
        groups.append((f"{start}-{end}", float(values[i:j].sum())))
        i = j
    return groups


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dates, load, pv, _ = read_inputs(ROOT)
    net = load - pv
    price = pd.read_excel(ROOT / "00_problem/appendix/附件4.xlsx").iloc[:, 1:].to_numpy(float)
    data = np.load(SOURCE)
    grid = data["grid"]
    trace = data["trace"]
    if grid.shape != (334, 144) or trace.shape != (334, 144, 6):
        raise ValueError((grid.shape, trace.shape))

    soc_midnight, pending = warmup(net)
    _, previous_last_flow = one_interval(*pending, soc_midnight)
    plan_rows = []
    battery_rows = []
    emergency_rows = []
    natural_soc_errors = []
    for i, day in enumerate(range(31, 365)):
        date = dates[day]
        plan_cost = float(price[day] @ grid[i])
        plan_rows.append([
            date.isoformat(), *np.round(grid[i], 6).tolist(),
            round(float(grid[i].sum()), 6), round(plan_cost, 6),
        ])
        prev = previous_last_flow if i == 0 else trace[i - 1, 143]
        civil = np.vstack([prev, trace[i, :143]])
        soc0 = float(prev[0])
        soc24 = float(trace[i, 142, 1])
        natural_soc_errors.append(abs(civil[-1, 1] - soc24))
        labels = ["0:00-4:00", "4:00-8:00", "8:00-12:00",
                  "12:00-16:00", "16:00-20:00", "20:00-24:00"]
        for block, label in enumerate(labels):
            part = civil[24*block:24*(block+1)]
            battery_rows.append([
                date.isoformat() if block == 0 else None,
                label,
                round(float(part[:, 2].sum()), 6),
                round(float(part[:, 3].sum()), 6),
                "0:00" if block == 0 else ("24:00" if block == 1 else None),
                round(soc0 if block == 0 else soc24, 6) if block < 2 else None,
            ])
        groups = merge_emergency(trace[i, :, 4])
        if not groups:
            emergency_rows.append([date.isoformat(), None, 0.0])
        else:
            for k, (label, amount) in enumerate(groups):
                emergency_rows.append([
                    date.isoformat() if k == 0 else None,
                    label, round(amount, 6),
                ])

    balance = grid + trace[:, :, 3] + trace[:, :, 4] \
        - net[31:] * DT_HOURS - trace[:, :, 2] - trace[:, :, 5]
    expected_plan = np.sum(price[31:] * grid, axis=1)
    expected_emergency = np.sum(5 * price[31:] * trace[:, :, 4], axis=1)
    checks = {
        "model": "weekday_mean_4w + paired price residual paths + Q2 net-load tree",
        "dates": [str(dates[31].date()), str(dates[-1].date())],
        "plan_shape": list(grid.shape),
        "battery_rows": len(battery_rows),
        "emergency_rows": len(emergency_rows),
        "planned_yuan": float(expected_plan.sum()),
        "emergency_yuan": float(expected_emergency.sum()),
        "total_yuan": float(expected_plan.sum() + expected_emergency.sum()),
        "emergency_kwh": float(trace[:, :, 4].sum()),
        "max_balance_error_kwh": float(np.abs(balance).max()),
        "max_natural_day_soc_assembly_error_kwh": float(max(natural_soc_errors)),
        "min_soc_kwh": float(trace[:, :, 1].min()),
        "max_soc_kwh": float(trace[:, :, 1].max()),
        "simultaneous_charge_discharge": int(np.sum(
            (trace[:, :, 2] > 1e-7) & (trace[:, :, 3] > 1e-7)
        )),
    }
    payload = {"plan": plan_rows, "battery": battery_rows, "emergency": emergency_rows}
    (OUT / "result4_2_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "result4_2_model_validation.json").write_text(
        json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
