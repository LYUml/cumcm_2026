"""Question 2: causal forecasting, day-ahead battery scheduling, and settlement.

The script compares several forecasts under exactly the same LP and settlement
rules, selects the method with the lowest realized annual cost, and exports the
official result2 workbook plus auditable CSV summaries.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import lil_matrix
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


# The bundled artifact runtime supplies openpyxl without shadowing the modeling
# environment's newer NumPy/SciPy stack.
_BUNDLED_SITE = Path(
    "/Users/lml/.cache/codex-runtimes/codex-primary-runtime/dependencies/"
    "python/lib/python3.12/site-packages"
)
if _BUNDLED_SITE.exists():
    sys.path.append(str(_BUNDLED_SITE))
from openpyxl import load_workbook  # noqa: E402


DT_HOURS = 1.0 / 6.0
SOC_MIN = 1200.0
SOC_MAX = 10800.0
SOC_INITIAL = 6000.0
POWER_MAX_KW = 5000.0
ENERGY_MAX = POWER_MAX_KW * DT_HOURS
ETA_CHARGE = 0.90
ETA_DISCHARGE = 0.90
EMERGENCY_MULTIPLIER = 5.0
TOL = 1e-6


@dataclass
class DayPlan:
    grid: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    spill_forecast: np.ndarray
    soc_end: np.ndarray
    objective: float


def _excel_engine_ready() -> None:
    if "openpyxl" not in sys.modules:
        raise RuntimeError("openpyxl is required to read and write the official files")


def read_inputs(root: Path) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray]:
    """Read dates, actual load/PV power, and the fixed 144-period price vector."""
    _excel_engine_ready()
    attachment2 = root / "00_problem/appendix/附件2.xlsx"
    attachment1 = root / "00_problem/appendix/附件1.xlsx"

    load_df = pd.read_excel(attachment2, sheet_name="小区负载", engine="openpyxl")
    pv_df = pd.read_excel(attachment2, sheet_name="光伏发电实际功率", engine="openpyxl")
    price_df = pd.read_excel(attachment1, engine="openpyxl")

    dates = pd.DatetimeIndex(pd.to_datetime(load_df.iloc[:, 0]))
    load = load_df.iloc[:, 1:].apply(pd.to_numeric, errors="raise").to_numpy(float)
    pv = pv_df.iloc[:, 1:].apply(pd.to_numeric, errors="raise").to_numpy(float)
    price = pd.to_numeric(price_df["电价"], errors="raise").to_numpy(float)

    if load.shape != (365, 144) or pv.shape != load.shape or price.shape != (144,):
        raise ValueError(f"Unexpected shapes: load={load.shape}, pv={pv.shape}, price={price.shape}")
    if not dates.is_monotonic_increasing or dates.has_duplicates:
        raise ValueError("Attachment 2 dates must be unique and increasing")
    if np.isnan(load).any() or np.isnan(pv).any() or np.isnan(price).any():
        raise ValueError("Inputs contain missing numerical values")
    if (load < 0).any() or (pv < 0).any() or (price < 0).any():
        raise ValueError("Load, PV, and price must be nonnegative")
    return dates, load, pv, price


def _feature_row(net: np.ndarray, day: int, slot: int, date: pd.Timestamp) -> list[float]:
    hour_angle = 2 * np.pi * slot / 144.0
    year_angle = 2 * np.pi * (date.dayofyear - 1) / 365.0
    lags = [net[day - lag, slot] for lag in (1, 7, 14, 21, 28)]
    return [
        np.sin(hour_angle), np.cos(hour_angle),
        np.sin(year_angle), np.cos(year_angle),
        np.sin(2 * year_angle), np.cos(2 * year_angle),
        float(date.dayofweek >= 5), *lags,
        float(np.mean([lags[1], lags[2], lags[3], lags[4]])),
    ]


def _fit_ridge(net: np.ndarray, dates: pd.DatetimeIndex, forecast_day: int):
    start = max(28, forecast_day - 90)
    x, y = [], []
    for day in range(start, forecast_day):
        for slot in range(144):
            x.append(_feature_row(net, day, slot, dates[day]))
            y.append(net[day, slot])
    model = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    model.fit(np.asarray(x), np.asarray(y))
    return model


def generate_causal_forecasts(
    net: np.ndarray, dates: pd.DatetimeIndex, start_day: int = 31
) -> dict[str, np.ndarray]:
    """Forecast every evaluation day using only rows strictly before that day."""
    horizon_days = len(net) - start_day
    forecasts = {
        "seasonal_naive_7d": np.zeros((horizon_days, 144)),
        "weekday_mean_4w": np.zeros((horizon_days, 144)),
        "recent_median_7d": np.zeros((horizon_days, 144)),
        "ridge_expanding": np.zeros((horizon_days, 144)),
        "cost_aware_q80": np.zeros((horizon_days, 144)),
    }
    ridge_model = None
    for out_day, day in enumerate(range(start_day, len(net))):
        lag7 = net[day - 7]
        weekday_mean = net[[day - 7, day - 14, day - 21, day - 28]].mean(axis=0)
        forecasts["seasonal_naive_7d"][out_day] = lag7
        forecasts["weekday_mean_4w"][out_day] = weekday_mean
        forecasts["recent_median_7d"][out_day] = np.median(net[day - 7 : day], axis=0)

        # Refit weekly. The latest training target is always day-1, so there is no leakage.
        if ridge_model is None or (day - start_day) % 7 == 0:
            ridge_model = _fit_ridge(net, dates, day)
        x_future = np.asarray([_feature_row(net, day, s, dates[day]) for s in range(144)])
        forecasts["ridge_expanding"][out_day] = ridge_model.predict(x_future)

        # Critical-fractile forecast: emergency energy costs 5p versus planned p,
        # giving tau=(5p-p)/((5p-p)+p)=0.8 in the uncoupled newsvendor limit.
        hist_start = max(7, day - 56)
        residuals = np.asarray([net[j] - net[j - 7] for j in range(hist_start, day)])
        q80_adjustment = np.quantile(residuals, 0.80, axis=0)
        forecasts["cost_aware_q80"][out_day] = lag7 + q80_adjustment
    return forecasts


def solve_day_ahead_lp(net_forecast_kw: np.ndarray, price: np.ndarray, start_soc: float) -> DayPlan:
    """Solve one 144-period deterministic day-ahead LP with cyclic terminal SOC."""
    t_count = 144
    # Variables: grid, charge, discharge, spill, end-of-period SOC.
    n = 5 * t_count
    grid = slice(0, t_count)
    charge = slice(t_count, 2 * t_count)
    discharge = slice(2 * t_count, 3 * t_count)
    spill = slice(3 * t_count, 4 * t_count)
    soc = slice(4 * t_count, 5 * t_count)
    c = np.zeros(n)
    c[grid] = price
    # Tiny throughput penalty removes degenerate simultaneous cycling without
    # changing reported electricity cost at meaningful precision.
    c[charge] = 1e-4
    c[discharge] = 1e-4

    aeq = lil_matrix((2 * t_count + 1, n))
    beq = np.zeros(2 * t_count + 1)
    net_kwh = np.asarray(net_forecast_kw, float) * DT_HOURS
    for t in range(t_count):
        # grid + discharge - charge - spill = net load
        aeq[t, t] = 1.0
        aeq[t, 2 * t_count + t] = 1.0
        aeq[t, t_count + t] = -1.0
        aeq[t, 3 * t_count + t] = -1.0
        beq[t] = net_kwh[t]

        row = t_count + t
        aeq[row, 4 * t_count + t] = 1.0
        aeq[row, t_count + t] = -ETA_CHARGE
        aeq[row, 2 * t_count + t] = 1.0 / ETA_DISCHARGE
        if t == 0:
            beq[row] = start_soc
        else:
            aeq[row, 4 * t_count + t - 1] = -1.0
    aeq[-1, 5 * t_count - 1] = 1.0
    beq[-1] = start_soc

    bounds = (
        [(0.0, None)] * t_count
        + [(0.0, ENERGY_MAX)] * t_count
        + [(0.0, ENERGY_MAX)] * t_count
        + [(0.0, None)] * t_count
        + [(SOC_MIN, SOC_MAX)] * t_count
    )
    result = linprog(c, A_eq=aeq.tocsr(), b_eq=beq, bounds=bounds, method="highs")
    if not result.success:
        raise RuntimeError(result.message)
    x = result.x
    return DayPlan(
        grid=x[grid], charge=x[charge], discharge=x[discharge],
        spill_forecast=x[spill], soc_end=x[soc],
        objective=float(np.dot(price, x[grid])),
    )


def solve_scenario_lp(
    net_scenarios_kw: np.ndarray,
    price: np.ndarray,
    start_soc: float,
    probabilities: np.ndarray | None = None,
) -> DayPlan:
    """Two-stage LP: one fixed plan, scenario-specific emergency settlement.

    Grid purchase and battery actions are fixed at 0:00. Emergency purchase and
    surplus are recourse/accounting variables for each possible realized path.
    """
    scenarios = np.asarray(net_scenarios_kw, float)
    s_count, t_count = scenarios.shape
    if t_count != 144 or s_count < 2:
        raise ValueError("Expected at least two 144-period scenarios")
    if probabilities is None:
        probabilities = np.full(s_count, 1.0 / s_count)
    probabilities = np.asarray(probabilities, float)
    if probabilities.shape != (s_count,) or (probabilities < 0).any():
        raise ValueError("Scenario probabilities are invalid")
    probabilities = probabilities / probabilities.sum()
    # First stage: grid, charge, discharge, SOC. Second stage: emergency, surplus.
    g0, c0, d0, soc0 = 0, t_count, 2 * t_count, 3 * t_count
    e0 = 4 * t_count
    w0 = e0 + s_count * t_count
    n = w0 + s_count * t_count
    objective = np.zeros(n)
    objective[g0:c0] = price
    objective[c0:d0] = 1e-4
    objective[d0:soc0] = 1e-4
    for s in range(s_count):
        objective[e0 + s * t_count : e0 + (s + 1) * t_count] = (
            EMERGENCY_MULTIPLIER * price * probabilities[s]
        )

    aeq = lil_matrix((s_count * t_count + t_count + 1, n))
    beq = np.zeros(s_count * t_count + t_count + 1)
    for s in range(s_count):
        for t in range(t_count):
            row = s * t_count + t
            aeq[row, g0 + t] = 1.0
            aeq[row, d0 + t] = 1.0
            aeq[row, c0 + t] = -1.0
            aeq[row, e0 + s * t_count + t] = 1.0
            aeq[row, w0 + s * t_count + t] = -1.0
            beq[row] = scenarios[s, t] * DT_HOURS
    state_row0 = s_count * t_count
    for t in range(t_count):
        row = state_row0 + t
        aeq[row, soc0 + t] = 1.0
        aeq[row, c0 + t] = -ETA_CHARGE
        aeq[row, d0 + t] = 1.0 / ETA_DISCHARGE
        if t == 0:
            beq[row] = start_soc
        else:
            aeq[row, soc0 + t - 1] = -1.0
    aeq[-1, soc0 + t_count - 1] = 1.0
    beq[-1] = start_soc
    bounds = (
        [(0.0, None)] * t_count
        + [(0.0, ENERGY_MAX)] * t_count
        + [(0.0, ENERGY_MAX)] * t_count
        + [(SOC_MIN, SOC_MAX)] * t_count
        + [(0.0, None)] * (2 * s_count * t_count)
    )
    result = linprog(objective, A_eq=aeq.tocsr(), b_eq=beq, bounds=bounds, method="highs")
    if not result.success:
        raise RuntimeError(result.message)
    x = result.x
    # Store expected scenario surplus only for diagnostics; settlement is redone on actuals.
    expected_surplus = x[w0:].reshape(s_count, t_count).mean(axis=0)
    return DayPlan(
        grid=x[g0:c0], charge=x[c0:d0], discharge=x[d0:soc0],
        spill_forecast=expected_surplus, soc_end=x[soc0:e0],
        objective=float(np.dot(price, x[g0:c0])),
    )


def historical_residual_scenarios(net: np.ndarray, day: int, count: int = 12) -> np.ndarray:
    """Construct causal whole-day trajectories around the 7-day base forecast."""
    candidates = np.arange(max(7, day - 56), day)
    # Prefer matching weekday residuals, then fill with the most recent residuals.
    matching = candidates[(day - candidates) % 7 == 0]
    remaining = candidates[~np.isin(candidates, matching)][::-1]
    chosen = np.concatenate([matching[::-1], remaining])[:count]
    residual_paths = np.asarray([net[j] - net[j - 7] for j in chosen])
    return net[day - 7][None, :] + residual_paths


def nearest_residual_scenarios(net: np.ndarray, day: int, count: int = 12) -> tuple[np.ndarray, np.ndarray]:
    """Prescriptive kNN: select errors whose known lag-7 profiles resemble today."""
    candidates = np.arange(max(7, day - 90), day)
    current_anchor = net[day - 7]
    distances = np.asarray([
        np.sqrt(np.mean((net[j - 7] - current_anchor) ** 2)) for j in candidates
    ])
    chosen = candidates[np.argsort(distances)[:count]]
    residuals = np.asarray([net[j] - net[j - 7] for j in chosen])
    scenarios = current_anchor[None, :] + residuals
    return scenarios, np.full(len(chosen), 1.0 / len(chosen))


def reduced_residual_scenarios(net: np.ndarray, day: int, count: int = 12) -> tuple[np.ndarray, np.ndarray]:
    """Fast-forward-style scenario reduction with reassigned cluster mass."""
    candidates = np.arange(max(7, day - 56), day)
    residuals = np.asarray([net[j] - net[j - 7] for j in candidates])
    n = len(residuals)
    count = min(count, n)
    # Distances between complete daily paths preserve temporal correlation.
    distance = np.sqrt(np.mean((residuals[:, None, :] - residuals[None, :, :]) ** 2, axis=2))
    selected = [int(np.argmin(distance.mean(axis=0)))]
    closest = distance[:, selected[0]].copy()
    while len(selected) < count:
        gains = np.asarray([
            np.mean(np.minimum(closest, distance[:, candidate]))
            if candidate not in selected else np.inf
            for candidate in range(n)
        ])
        pick = int(np.argmin(gains))
        selected.append(pick)
        closest = np.minimum(closest, distance[:, pick])
    selected = np.asarray(selected)
    assignment = np.argmin(distance[:, selected], axis=1)
    probabilities = np.bincount(assignment, minlength=count).astype(float) / n
    scenarios = net[day - 7][None, :] + residuals[selected]
    return scenarios, probabilities


def settle_plan(plan: DayPlan, actual_net_kw: np.ndarray, price: np.ndarray) -> dict:
    """Settle a fixed day-ahead schedule against actual net load."""
    actual_net_kwh = np.asarray(actual_net_kw) * DT_HOURS
    scheduled_supply = plan.grid + plan.discharge - plan.charge
    imbalance = actual_net_kwh - scheduled_supply
    emergency = np.maximum(imbalance, 0.0)
    surplus = np.maximum(-imbalance, 0.0)
    plan_cost = float(np.dot(price, plan.grid))
    emergency_cost = float(np.dot(EMERGENCY_MULTIPLIER * price, emergency))
    balance_residual = scheduled_supply + emergency - surplus - actual_net_kwh
    return {
        "emergency": emergency,
        "surplus": surplus,
        "plan_cost": plan_cost,
        "emergency_cost": emergency_cost,
        "total_cost": plan_cost + emergency_cost,
        "max_balance_residual": float(np.max(np.abs(balance_residual))),
    }


def evaluate_models(
    forecasts: dict[str, np.ndarray], actual_net: np.ndarray, dates: pd.DatetimeIndex,
    price: np.ndarray, start_day: int = 31,
) -> tuple[pd.DataFrame, dict[str, dict]]:
    details: dict[str, dict] = {}
    comparison_rows = []
    actual_eval = actual_net[start_day:]
    for name, forecast in forecasts.items():
        day_records, plans, settlements = [], [], []
        for k, day in enumerate(range(start_day, len(actual_net))):
            plan = solve_day_ahead_lp(forecast[k], price, SOC_INITIAL)
            settlement = settle_plan(plan, actual_net[day], price)
            plans.append(plan)
            settlements.append(settlement)
            day_records.append({
                "date": dates[day], "plan_cost": settlement["plan_cost"],
                "emergency_cost": settlement["emergency_cost"],
                "total_cost": settlement["total_cost"],
                "emergency_kwh": float(settlement["emergency"].sum()),
                "surplus_kwh": float(settlement["surplus"].sum()),
            })
        error = forecast - actual_eval
        total_plan = sum(r["plan_cost"] for r in day_records)
        total_emergency = sum(r["emergency_cost"] for r in day_records)
        comparison_rows.append({
            "model": name,
            "MAE_kW": float(np.mean(np.abs(error))),
            "RMSE_kW": float(np.sqrt(np.mean(error ** 2))),
            "pinball_q80_kW": float(np.mean(np.maximum(0.8 * (-error), -0.2 * (-error)))),
            "underforecast_rate": float(np.mean(forecast < actual_eval)),
            "planned_cost_yuan": total_plan,
            "emergency_cost_yuan": total_emergency,
            "total_cost_yuan": total_plan + total_emergency,
            "emergency_energy_kwh": sum(r["emergency_kwh"] for r in day_records),
            "surplus_energy_kwh": sum(r["surplus_kwh"] for r in day_records),
        })
        details[name] = {"plans": plans, "settlements": settlements, "daily": pd.DataFrame(day_records)}

    # Direct stochastic optimization is a policy candidate rather than a single
    # point forecaster. Its scenario mean is used only for forecast diagnostics.
    scenario_policies = [
        (f"scenario_recent_{count}", lambda day, count=count: (
            historical_residual_scenarios(actual_net, day, count=count), None
        ))
        for count in (6, 12, 20)
    ]
    scenario_policies.extend([
        ("scenario_knn_12", lambda day: nearest_residual_scenarios(actual_net, day, 12)),
        ("scenario_reduced_12", lambda day: reduced_residual_scenarios(actual_net, day, 12)),
    ])
    for name, scenario_builder in scenario_policies:
        day_records, plans, settlements, scenario_centers = [], [], [], []
        for day in range(start_day, len(actual_net)):
            scenarios, probabilities = scenario_builder(day)
            if probabilities is None:
                probabilities = np.full(len(scenarios), 1.0 / len(scenarios))
            center = np.average(scenarios, axis=0, weights=probabilities)
            plan = solve_scenario_lp(scenarios, price, SOC_INITIAL, probabilities)
            settlement = settle_plan(plan, actual_net[day], price)
            scenario_centers.append(center)
            plans.append(plan)
            settlements.append(settlement)
            day_records.append({
                "date": dates[day], "plan_cost": settlement["plan_cost"],
                "emergency_cost": settlement["emergency_cost"],
                "total_cost": settlement["total_cost"],
                "emergency_kwh": float(settlement["emergency"].sum()),
                "surplus_kwh": float(settlement["surplus"].sum()),
            })
        forecast = np.asarray(scenario_centers)
        error = forecast - actual_eval
        total_plan = sum(r["plan_cost"] for r in day_records)
        total_emergency = sum(r["emergency_cost"] for r in day_records)
        comparison_rows.append({
            "model": name,
            "MAE_kW": float(np.mean(np.abs(error))),
            "RMSE_kW": float(np.sqrt(np.mean(error ** 2))),
            "pinball_q80_kW": float(np.mean(np.maximum(0.8 * (-error), -0.2 * (-error)))),
            "underforecast_rate": float(np.mean(forecast < actual_eval)),
            "planned_cost_yuan": total_plan,
            "emergency_cost_yuan": total_emergency,
            "total_cost_yuan": total_plan + total_emergency,
            "emergency_energy_kwh": sum(r["emergency_kwh"] for r in day_records),
            "surplus_energy_kwh": sum(r["surplus_kwh"] for r in day_records),
        })
        details[name] = {"plans": plans, "settlements": settlements, "daily": pd.DataFrame(day_records)}
    comparison = pd.DataFrame(comparison_rows)
    # Select on Feb-Aug only; Sep-Dec remains an untouched final test block.
    selection_cutoff = pd.Timestamp("2025-09-01")
    selection_costs, test_costs = {}, {}
    for model_name, model_detail in details.items():
        daily = model_detail["daily"]
        selection_costs[model_name] = float(
            daily.loc[daily["date"] < selection_cutoff, "total_cost"].sum()
        )
        test_costs[model_name] = float(
            daily.loc[daily["date"] >= selection_cutoff, "total_cost"].sum()
        )
    comparison["selection_cost_Feb_Aug_yuan"] = comparison["model"].map(selection_costs)
    comparison["holdout_cost_Sep_Dec_yuan"] = comparison["model"].map(test_costs)
    comparison = comparison.sort_values("selection_cost_Feb_Aug_yuan").reset_index(drop=True)
    return comparison, details


def _interval_label(slot: int) -> str:
    start_min = (slot + 1) * 10
    end_min = (slot + 2) * 10
    def fmt(minute: int) -> str:
        suffix = "+1" if minute >= 24 * 60 else ""
        minute %= 24 * 60
        return f"{minute // 60}:{minute % 60:02d}{suffix}"
    return f"{fmt(start_min)}-{fmt(end_min)}"


def _merge_emergency(values: np.ndarray) -> list[tuple[str, float]]:
    positive = values > 1e-7
    groups = []
    i = 0
    while i < 144:
        if not positive[i]:
            i += 1
            continue
        j = i + 1
        while j < 144 and positive[j]:
            j += 1
        first = _interval_label(i).split("-")[0]
        last = _interval_label(j - 1).split("-")[1]
        groups.append((f"{first}-{last}", float(values[i:j].sum())))
        i = j
    return groups


def export_result2(
    root: Path, output_path: Path, dates: pd.DatetimeIndex, price: np.ndarray,
    plans: list[DayPlan], settlements: list[dict], start_day: int = 31,
) -> None:
    template = root / "00_problem/appendix/附件5/result2.xlsx"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, output_path)
    wb = load_workbook(output_path)

    ws = wb["计划购电量"]
    for k, day in enumerate(range(start_day, len(dates)), start=2):
        plan = plans[k - 2]
        for slot, value in enumerate(plan.grid, start=2):
            ws.cell(k, slot).value = round(float(value), 6)
        ws.cell(k, 146).value = round(float(plan.grid.sum()), 6)
        ws.cell(k, 147).value = round(float(np.dot(price, plan.grid)), 6)

    # The template uses ellipsis rows. Rebuild the two variable-length sheets.
    wb.remove(wb["充放电量"])
    battery_ws = wb.create_sheet("充放电量", 1)
    battery_ws.append(["日期", "时间段", "充电量", "放电量", "时刻", "储电量"])
    blocks = ["0:00-4:00", "4:00-8:00", "8:00-12:00", "12:00-16:00", "16:00-20:00", "20:00-24:00"]
    for k, day in enumerate(range(start_day, len(dates))):
        plan = plans[k]
        for b, label in enumerate(blocks):
            sl = slice(24 * b, 24 * (b + 1))
            battery_ws.append([
                dates[day].to_pydatetime() if b == 0 else None, label,
                round(float(plan.charge[sl].sum()), 6),
                round(float(plan.discharge[sl].sum()), 6),
                "0:00" if b == 0 else ("24:00" if b == 1 else None),
                round(SOC_INITIAL if b == 0 else float(plan.soc_end[-1]), 6) if b < 2 else None,
            ])

    wb.remove(wb["紧急购电量"])
    emergency_ws = wb.create_sheet("紧急购电量", 2)
    emergency_ws.append(["日期", "购电时间段", "购电量"])
    for k, day in enumerate(range(start_day, len(dates))):
        groups = _merge_emergency(settlements[k]["emergency"])
        if not groups:
            emergency_ws.append([dates[day].to_pydatetime(), None, 0.0])
        else:
            for g, (label, amount) in enumerate(groups):
                emergency_ws.append([dates[day].to_pydatetime() if g == 0 else None, label, round(amount, 6)])
    wb.save(output_path)


def validate_solution(
    comparison: pd.DataFrame, details: dict[str, dict], best_model: str,
    expected_days: int,
) -> dict:
    plans = details[best_model]["plans"]
    settlements = details[best_model]["settlements"]
    checks = {
        "evaluation_days": len(plans),
        "expected_days": expected_days,
        "all_lp_days_present": len(plans) == expected_days,
        "max_actual_balance_residual_kwh": max(x["max_balance_residual"] for x in settlements),
        "min_soc_kwh": min(float(p.soc_end.min()) for p in plans),
        "max_soc_kwh": max(float(p.soc_end.max()) for p in plans),
        "max_charge_kwh_per_interval": max(float(p.charge.max()) for p in plans),
        "max_discharge_kwh_per_interval": max(float(p.discharge.max()) for p in plans),
        "max_terminal_soc_error_kwh": max(abs(float(p.soc_end[-1]) - SOC_INITIAL) for p in plans),
        "negative_emergency_count": int(sum(np.sum(x["emergency"] < -TOL) for x in settlements)),
        "simultaneous_charge_discharge_count": int(sum(np.sum((p.charge > TOL) & (p.discharge > TOL)) for p in plans)),
        "selected_model_is_min_validation_cost": best_model == comparison.iloc[0]["model"],
    }
    checks["passed"] = bool(
        checks["all_lp_days_present"]
        and checks["max_actual_balance_residual_kwh"] <= TOL
        and checks["min_soc_kwh"] >= SOC_MIN - TOL
        and checks["max_soc_kwh"] <= SOC_MAX + TOL
        and checks["max_charge_kwh_per_interval"] <= ENERGY_MAX + TOL
        and checks["max_discharge_kwh_per_interval"] <= ENERGY_MAX + TOL
        and checks["max_terminal_soc_error_kwh"] <= TOL
        and checks["negative_emergency_count"] == 0
        and checks["simultaneous_charge_discharge_count"] == 0
        and checks["selected_model_is_min_validation_cost"]
    )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    out = (args.output_dir or root / "02_q2/outputs/baseline").resolve()
    out.mkdir(parents=True, exist_ok=True)

    dates, load, pv, price = read_inputs(root)
    net = load - pv
    forecasts = generate_causal_forecasts(net, dates)
    comparison, details = evaluate_models(forecasts, net, dates, price)
    best = str(comparison.iloc[0]["model"])
    checks = validate_solution(comparison, details, best, len(dates) - 31)
    if not checks["passed"]:
        raise AssertionError(json.dumps(checks, ensure_ascii=False, indent=2))

    comparison.to_csv(out / "model_comparison.csv", index=False, encoding="utf-8-sig")
    details[best]["daily"].to_csv(out / "best_model_daily_cost.csv", index=False, encoding="utf-8-sig")
    with open(out / "validation.json", "w", encoding="utf-8") as f:
        json.dump({"best_model": best, **checks}, f, ensure_ascii=False, indent=2, default=float)
    export_result2(root, out / "result2.xlsx", dates, price, details[best]["plans"], details[best]["settlements"])

    print(comparison.to_string(index=False))
    print("\nBEST_MODEL=", best)
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    print("OUTPUT_DIR=", out)


if __name__ == "__main__":
    main()
