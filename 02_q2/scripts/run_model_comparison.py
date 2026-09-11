"""Recompute the six paper policies under one template-anchored chronology.

Every row is committed at civil midnight.  The preceding row's final interval
is still pending at that instant and is deliberately excluded from forecasting.
All policies share the January warm-up, physical feedback controller, tariffs,
and February--December settlement window.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02_q2/src"))

from q2_availability import complete_residual_candidates, slotwise_median
from q2_model import (DT_HOURS, EMERGENCY_MULTIPLIER, historical_residual_scenarios,
                      read_inputs, solve_day_ahead_lp, solve_scenario_lp)
from q2_near_optimal import (execute_feedback, hierarchical_tree_groups,
                             solve_adaptive_plan, split_residual_scenarios)
from run_final import warmup, one_interval

OUT = ROOT / "02_q2/outputs/model_comparison"
N_SCENARIOS = 12
FLOOR = 3000.0
PENALTY = 4.5


def separate_baseline(load: np.ndarray, pv: np.ndarray, day: int) -> np.ndarray:
    return load[day - 7] - slotwise_median(pv, day, 7)


def quantile_forecast(load: np.ndarray, pv: np.ndarray, day: int,
                      split: bool, quantile: float) -> np.ndarray:
    net = load - pv
    anchor = separate_baseline(load, pv, day) if split else net[day - 7]
    candidates = complete_residual_candidates(day, 56)
    if split:
        def historical_base(j: int) -> np.ndarray:
            return load[j - 7] - np.median(pv[j - 7:j], axis=0)
    else:
        def historical_base(j: int) -> np.ndarray:
            return net[j - 7]
    residuals = np.asarray([net[j] - historical_base(int(j)) for j in candidates])
    return anchor + np.quantile(residuals, quantile, axis=0)


def make_planner(name: str, load: np.ndarray, pv: np.ndarray, net: np.ndarray,
                 price: np.ndarray):
    if name == "separate_q50":
        return lambda day, soc: solve_day_ahead_lp(
            quantile_forecast(load, pv, day, True, .5), price, soc).grid
    if name == "direct_q80":
        return lambda day, soc: solve_day_ahead_lp(
            quantile_forecast(load, pv, day, False, .8), price, soc).grid
    if name == "separate_q80":
        return lambda day, soc: solve_day_ahead_lp(
            quantile_forecast(load, pv, day, True, .8), price, soc).grid
    if name == "fixed_action_scenarios":
        return lambda day, soc: solve_scenario_lp(
            historical_residual_scenarios(net[:day], day, N_SCENARIOS), price, soc).grid
    if name in {"four_hour_tree", "two_stage_relaxation"}:
        def stochastic(day: int, soc: float) -> np.ndarray:
            scenarios = split_residual_scenarios(load[:day], pv[:day], day, N_SCENARIOS)
            groups = hierarchical_tree_groups(scenarios, 24) if name == "four_hour_tree" else None
            return solve_adaptive_plan(scenarios, price, soc, FLOOR, PENALTY, groups)
        return stochastic
    raise KeyError(name)


def simulate(planner, net: np.ndarray, price: np.ndarray):
    soc, pending = warmup(net)
    feb_soc = soc
    grids, traces, starts, ends = [], [], [], []
    for day in range(31, 365):
        starts.append(soc)
        grid = np.asarray(planner(day, soc), float)
        soc_after_pending, pending_flow = one_interval(*pending, soc)
        if traces:
            traces[-1][1] = pending_flow
        soc, flow143 = execute_feedback(grid[:143], net[day, :143], soc_after_pending)
        grids.append(grid)
        traces.append([flow143, None])
        ends.append(soc)
        pending = (grid[143], net[day, 143])
    final_soc, last_flow = one_interval(*pending, soc)
    traces[-1][1] = last_flow
    trace = np.asarray([np.vstack(parts) for parts in traces])
    grid = np.asarray(grids)
    planned = grid @ price
    emergency = trace[:, :, 4] @ (EMERGENCY_MULTIPLIER * price)
    daily = pd.DataFrame({
        "date": pd.date_range("2025-02-01", periods=334, freq="D").date,
        "planned_yuan": planned,
        "emergency_yuan": emergency,
        "total_yuan": planned + emergency,
        "emergency_kwh": trace[:, :, 4].sum(axis=1),
        "soc_at_plan_midnight_kwh": starts,
        "soc_at_next_midnight_kwh": ends,
    })
    return daily, grid, trace, feb_soc, final_soc


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dates, load, pv, price = read_inputs(ROOT)
    net = load - pv
    names = ["separate_q50", "direct_q80", "separate_q80",
             "fixed_action_scenarios", "four_hour_tree", "two_stage_relaxation"]
    labels = {
        "separate_q50": "Separate Q0.5",
        "direct_q80": "Direct Q0.8",
        "separate_q80": "Separate Q0.8",
        "fixed_action_scenarios": "Fixed-action scenarios",
        "four_hour_tree": "Four-hour tree",
        "two_stage_relaxation": "Two-stage relaxation",
    }
    summary = []
    for name in names:
        tic = time.perf_counter()
        daily, grid, trace, feb_soc, final_soc = simulate(
            make_planner(name, load, pv, net, price), net, price)
        daily.to_csv(OUT / f"{name}_daily.csv", index=False)
        np.savez_compressed(OUT / f"{name}_trace.npz", grid=grid, trace=trace,
                            dates=np.asarray(dates[31:].astype(str)))
        balance = grid + trace[:, :, 3] + trace[:, :, 4] - net[31:] * DT_HOURS \
                  - trace[:, :, 2] - trace[:, :, 5]
        rec = {
            "model": name, "policy": labels[name], "selected": name == "four_hour_tree",
            "planned_yuan": float(daily.planned_yuan.sum()),
            "emergency_yuan": float(daily.emergency_yuan.sum()),
            "total_yuan": float(daily.total_yuan.sum()),
            "emergency_kwh": float(daily.emergency_kwh.sum()),
            "feb_1_midnight_soc_kwh": float(feb_soc), "final_soc_kwh": float(final_soc),
            "midnight_below_3000_days": int((daily.soc_at_next_midnight_kwh < 3000 - 1e-7).sum()),
            "max_balance_residual_kwh": float(np.abs(balance).max()),
            "simultaneous_charge_discharge": int(np.sum((trace[:,:,2] > 1e-7) & (trace[:,:,3] > 1e-7))),
            "emergency_while_charging": int(np.sum((trace[:,:,4] > 1e-7) & (trace[:,:,2] > 1e-7))),
            "seconds": time.perf_counter() - tic,
        }
        summary.append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
    table = pd.DataFrame(summary).sort_values("total_yuan").reset_index(drop=True)
    table.to_csv(OUT / "comparison.csv", index=False, encoding="utf-8-sig")

    # Explicitly test the boundary Prism identified, plus ordinary future-prefix causality.
    cutoff = 150
    base = split_residual_scenarios(load[:cutoff], pv[:cutoff], cutoff, N_SCENARIOS)
    altered_load, altered_pv = load.copy(), pv.copy()
    altered_load[cutoff - 1, 143] += 1e6
    altered_pv[cutoff - 1, 143] += 2e5
    pending = split_residual_scenarios(altered_load[:cutoff], altered_pv[:cutoff], cutoff, N_SCENARIOS)
    future_load, future_pv = load.copy(), pv.copy()
    future_load[cutoff:] += 1e6
    future_pv[cutoff:] += 2e5
    future = split_residual_scenarios(future_load[:cutoff], future_pv[:cutoff], cutoff, N_SCENARIOS)
    policy_boundary = {}
    for name in names:
        g_base = make_planner(name, load, pv, net, price)(cutoff, 5000.0)
        pending_net = altered_load - altered_pv
        g_pending = make_planner(name, altered_load, altered_pv, pending_net, price)(cutoff, 5000.0)
        future_net = future_load - future_pv
        g_future = make_planner(name, future_load, future_pv, future_net, price)(cutoff, 5000.0)
        policy_boundary[name] = {
            "pending_previous_row_last_slot_plan_unchanged": bool(np.array_equal(g_base, g_pending)),
            "future_rows_plan_unchanged": bool(np.array_equal(g_base, g_future)),
        }
    checks = {
        "status": "passed",
        "models_recomputed": names,
        "common_chronology": "commit at civil midnight; then execute prior-row 00:00-00:10; then current-row slots 0-142",
        "information_boundary": "at midnight, rows through d-2 are complete; row d-1 slot 143 is unavailable",
        "pending_previous_row_last_slot_scenarios_unchanged": bool(np.array_equal(base, pending)),
        "future_rows_scenarios_unchanged": bool(np.array_equal(base, future)),
        "policy_plan_boundary_tests": policy_boundary,
        "all_actual_physics_checks_pass": bool((table.max_balance_residual_kwh < 1e-6).all()
                                                and (table.simultaneous_charge_discharge == 0).all()
                                                and (table.emergency_while_charging == 0).all()),
        "selection_note": "Four-hour tree remains selected by the stated structural criterion, not by minimum realized comparison cost.",
    }
    all_policy_causal = all(all(result.values()) for result in policy_boundary.values())
    checks["all_policy_plan_boundary_tests_pass"] = all_policy_causal
    if not all([checks["pending_previous_row_last_slot_scenarios_unchanged"],
                checks["future_rows_scenarios_unchanged"], checks["all_actual_physics_checks_pass"],
                all_policy_causal]):
        raise AssertionError(json.dumps(checks, indent=2))
    (OUT / "validation.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(table.to_string(index=False))
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
