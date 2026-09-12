"""Unlock the three battery locks on top of v001 forecasts/buffers.

Locks removed:
1. Daily SOC need not return to 6000.
2. Block-end SOC is not pinned to the 00:00 plan.
3. After purchase is locked, battery follows actual net-load each 10-min slot
   (greedy recourse), not the planned charge/discharge.

Purchase contracts still change only at 0/6/12/18. Local only; do not push.
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
import time
from itertools import product
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, hstack, lil_matrix

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_corrected as rc  # noqa: E402

OUTPUT_DIR = HERE / "outputs" / "free_battery"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
V001_COST = 14_438_642.683144223
PMAX = rc.BATTERY_INTERVAL_LIMIT_KWH
ETA_C = rc.CHARGE_EFFICIENCY
ETA_D = rc.DISCHARGE_EFFICIENCY
SOC_MIN = rc.SOC_MIN_KWH
SOC_MAX = rc.SOC_MAX_KWH
TIE = rc.TIE_BREAK_COST
Q0 = 0.75
Q_ADJ = {6: 0.85, 12: 0.85, 18: 0.80}


def target_net(day: int, issue_hour: int, quantile: float) -> np.ndarray:
    if day <= rc.MIN_FORECAST_DAY:
        return rc.FORECASTS_BY_ISSUE[issue_hour]["net_kwh"][day].copy()
    return rc.corrected_net_forecast(day, issue_hour, quantile)


def solve_horizon(
    target: np.ndarray,
    price: np.ndarray,
    opening_soc: float,
    baseline_purchase: np.ndarray | None = None,
    terminal_value: float = 0.0,
    end_soc_target: float | None = None,
    end_soc_mode: str = "soft",
    shortfall_penalty: float = 1.0,
    charge_allowed: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Remaining-horizon purchase + battery LP.

    Optional midnight SOC target (soft shortfall penalty, or SOC >= target).
    charge_allowed: per-slot mask; False forbids planned charging in that slot.
    Defaults keep the original v002 behaviour.
    """
    horizon = len(target)
    if baseline_purchase is None:
        purchase = slice(0, horizon)
        charge = slice(horizon, 2 * horizon)
        discharge = slice(2 * horizon, 3 * horizon)
        spill = slice(3 * horizon, 4 * horizon)
        soc = slice(4 * horizon, 5 * horizon)
        n_var = 5 * horizon
        objective = np.zeros(n_var)
        objective[purchase] = price
        n_eq = 2 * horizon
        equality = lil_matrix((n_eq, n_var))
        rhs = np.zeros(n_eq)
        for t in range(horizon):
            equality[t, purchase.start + t] = 1.0
            equality[t, discharge.start + t] = 1.0
            equality[t, charge.start + t] = -1.0
            equality[t, spill.start + t] = -1.0
            rhs[t] = target[t]
            row = horizon + t
            equality[row, soc.start + t] = 1.0
            equality[row, charge.start + t] = -ETA_C
            equality[row, discharge.start + t] = 1.0 / ETA_D
            if t == 0:
                rhs[row] = opening_soc
            else:
                equality[row, soc.start + t - 1] = -1.0
        bounds = (
            [(0.0, None)] * horizon
            + [(0.0, PMAX)] * horizon
            + [(0.0, PMAX)] * horizon
            + [(0.0, None)] * horizon
            + [(SOC_MIN, SOC_MAX)] * horizon
        )
    else:
        purchase = slice(0, horizon)
        upward = slice(horizon, 2 * horizon)
        downward = slice(2 * horizon, 3 * horizon)
        charge = slice(3 * horizon, 4 * horizon)
        discharge = slice(4 * horizon, 5 * horizon)
        spill = slice(5 * horizon, 6 * horizon)
        soc = slice(6 * horizon, 7 * horizon)
        n_var = 7 * horizon
        objective = np.zeros(n_var)
        objective[upward] = 1.5 * price
        objective[downward] = -0.5 * price
        n_eq = 3 * horizon
        equality = lil_matrix((n_eq, n_var))
        rhs = np.zeros(n_eq)
        for t in range(horizon):
            equality[t, purchase.start + t] = 1.0
            equality[t, upward.start + t] = -1.0
            equality[t, downward.start + t] = 1.0
            rhs[t] = baseline_purchase[t]
            br = horizon + t
            equality[br, purchase.start + t] = 1.0
            equality[br, discharge.start + t] = 1.0
            equality[br, charge.start + t] = -1.0
            equality[br, spill.start + t] = -1.0
            rhs[br] = target[t]
            sr = 2 * horizon + t
            equality[sr, soc.start + t] = 1.0
            equality[sr, charge.start + t] = -ETA_C
            equality[sr, discharge.start + t] = 1.0 / ETA_D
            if t == 0:
                rhs[sr] = opening_soc
            else:
                equality[sr, soc.start + t - 1] = -1.0
        bounds = (
            [(0.0, None)] * horizon
            + [(0.0, None)] * horizon
            + [(0.0, None)] * horizon
            + [(0.0, PMAX)] * horizon
            + [(0.0, PMAX)] * horizon
            + [(0.0, None)] * horizon
            + [(SOC_MIN, SOC_MAX)] * horizon
        )

    objective[charge] = TIE
    objective[discharge] = TIE
    objective[spill] = TIE
    objective[soc.stop - 1] -= terminal_value

    bounds = list(bounds)
    if charge_allowed is not None:
        allowed = np.asarray(charge_allowed, dtype=bool)
        if allowed.shape != (horizon,):
            raise ValueError("charge_allowed length must match the horizon")
        for t in range(horizon):
            if not allowed[t]:
                bounds[charge.start + t] = (0.0, 0.0)

    eq = equality.tocsr()
    a_ub = None
    b_ub = None
    clipped_target = None
    if end_soc_target is not None:
        clipped_target = float(np.clip(end_soc_target, SOC_MIN, SOC_MAX))
        mode = end_soc_mode
        if mode == "soft":
            eq = hstack([eq, csr_matrix((n_eq, 1))])
            objective = np.append(objective, float(shortfall_penalty))
            bounds.append((0.0, None))
            a_ub = np.zeros((1, n_var + 1))
            a_ub[0, soc.stop - 1] = -1.0
            a_ub[0, -1] = -1.0
            b_ub = np.array([-clipped_target])
        elif mode == "ge":
            a_ub = np.zeros((1, n_var))
            a_ub[0, soc.stop - 1] = -1.0
            b_ub = np.array([-clipped_target])
        elif mode == "eq":
            from scipy.sparse import vstack

            extra = lil_matrix((1, n_var))
            extra[0, soc.stop - 1] = 1.0
            eq = vstack([eq.tocsr(), extra.tocsr()])
            rhs = np.append(rhs, clipped_target)
        else:
            raise ValueError(f"Unknown end_soc_mode: {mode}")

    solution = linprog(
        objective,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=eq,
        b_eq=rhs,
        bounds=bounds,
        method="highs-ds",
    )
    if not solution.success:
        raise RuntimeError(solution.message)
    x = solution.x
    out = {
        "purchase": x[purchase],
        "charge": x[charge],
        "discharge": x[discharge],
        "spill": x[spill],
        "soc": x[soc],
    }
    if baseline_purchase is not None:
        out["upward"] = x[upward]
        out["downward"] = x[downward]
    if clipped_target is not None:
        out["end_soc_target"] = np.array([clipped_target])
    return out


def greedy_recourse(
    purchase: np.ndarray,
    actual_net: np.ndarray,
    opening_soc: float,
) -> dict[str, np.ndarray | float]:
    n = len(purchase)
    charge = np.zeros(n)
    discharge = np.zeros(n)
    emergency = np.zeros(n)
    spill = np.zeros(n)
    soc = np.zeros(n)
    soc_now = float(opening_soc)
    for t in range(n):
        residual = float(actual_net[t] - purchase[t])
        if residual >= 0.0:
            max_ac = min(PMAX, max(0.0, (soc_now - SOC_MIN) * ETA_D))
            discharge[t] = min(residual, max_ac)
            emergency[t] = residual - discharge[t]
        else:
            surplus = -residual
            max_ch = min(PMAX, max(0.0, (SOC_MAX - soc_now) / ETA_C))
            charge[t] = min(surplus, max_ch)
            spill[t] = surplus - charge[t]
        soc_now = soc_now + ETA_C * charge[t] - discharge[t] / ETA_D
        soc_now = min(SOC_MAX, max(SOC_MIN, soc_now))
        soc[t] = soc_now
    return {
        "charge": charge,
        "discharge": discharge,
        "emergency": emergency,
        "spill": spill,
        "soc": soc,
        "soc_close": soc_now,
    }


def follow_plan_recourse(
    purchase: np.ndarray,
    plan_charge: np.ndarray,
    plan_discharge: np.ndarray,
    actual_net: np.ndarray,
    opening_soc: float,
) -> dict[str, np.ndarray | float]:
    """Keep planned charge/discharge; clip only if SOC bounds would break."""
    n = len(purchase)
    charge = np.zeros(n)
    discharge = np.zeros(n)
    emergency = np.zeros(n)
    spill = np.zeros(n)
    soc = np.zeros(n)
    soc_now = float(opening_soc)
    for t in range(n):
        ch = float(plan_charge[t])
        dch = float(plan_discharge[t])
        if ch > 1e-9 and dch > 1e-9:
            dch = 0.0
        max_ch = min(PMAX, max(0.0, (SOC_MAX - soc_now) / ETA_C))
        max_dch = min(PMAX, max(0.0, (soc_now - SOC_MIN) * ETA_D))
        ch = min(max(ch, 0.0), max_ch)
        dch = min(max(dch, 0.0), max_dch)
        charge[t] = ch
        discharge[t] = dch
        imbalance = float(actual_net[t] - (purchase[t] + dch - ch))
        emergency[t] = max(imbalance, 0.0)
        spill[t] = max(-imbalance, 0.0)
        soc_now = soc_now + ETA_C * ch - dch / ETA_D
        soc_now = min(SOC_MAX, max(SOC_MIN, soc_now))
        soc[t] = soc_now
    return {
        "charge": charge,
        "discharge": discharge,
        "emergency": emergency,
        "spill": spill,
        "soc": soc,
        "soc_close": soc_now,
    }


def simulate_year(
    horizon: str,
    recourse: str,
    terminal_value: float,
    update_hours: tuple[int, ...] = (6, 12, 18),
) -> dict:
    n_days = len(rc.DATES)
    plan = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    final = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    charge = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    discharge = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    soc = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    emergency = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    spill = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    soc_open = np.zeros(n_days)
    current_soc = rc.SOC_TARGET_KWH

    for day in range(rc.MIN_FORECAST_DAY, n_days):
        soc_open[day] = current_soc
        day_plan = np.zeros(rc.INTERVALS_PER_DAY)
        day_final = np.zeros(rc.INTERVALS_PER_DAY)
        day_ch = np.zeros(rc.INTERVALS_PER_DAY)
        day_dch = np.zeros(rc.INTERVALS_PER_DAY)
        day_em = np.zeros(rc.INTERVALS_PER_DAY)
        day_sp = np.zeros(rc.INTERVALS_PER_DAY)
        day_soc = np.zeros(rc.INTERVALS_PER_DAY)

        da = solve_horizon(
            target_net(day, 0, Q0),
            rc.PRICE,
            current_soc,
            baseline_purchase=None,
            terminal_value=terminal_value,
        )
        day_plan[:] = da["purchase"]

        for block, issue in enumerate(rc.ISSUE_HOURS):
            start, end = rc.BLOCK_BOUNDS[block], rc.BLOCK_BOUNDS[block + 1]
            if issue == 0 or issue in update_hours:
                if horizon == "rest_of_day":
                    sl = slice(start, rc.INTERVALS_PER_DAY)
                    if issue == 0:
                        planned = da
                    else:
                        planned = solve_horizon(
                            target_net(day, issue, Q_ADJ[issue]),
                            rc.PRICE[sl],
                            current_soc,
                            baseline_purchase=day_plan[sl],
                            terminal_value=terminal_value,
                        )
                    exec_purchase = planned["purchase"][: end - start]
                    exec_ch = planned["charge"][: end - start]
                    exec_dch = planned["discharge"][: end - start]
                else:
                    sl = slice(start, end)
                    if issue == 0:
                        exec_purchase = da["purchase"][start:end]
                        exec_ch = da["charge"][start:end]
                        exec_dch = da["discharge"][start:end]
                    else:
                        planned = solve_horizon(
                            target_net(day, issue, Q_ADJ[issue])[: end - start],
                            rc.PRICE[sl],
                            current_soc,
                            baseline_purchase=day_plan[sl],
                            terminal_value=terminal_value,
                        )
                        exec_purchase = planned["purchase"]
                        exec_ch = planned["charge"]
                        exec_dch = planned["discharge"]
            else:
                exec_purchase = day_plan[start:end]
                exec_ch = np.zeros(end - start)
                exec_dch = np.zeros(end - start)

            actual = rc.NET_KWH[day, start:end]
            if recourse == "greedy":
                rec = greedy_recourse(exec_purchase, actual, current_soc)
            else:
                rec = follow_plan_recourse(exec_purchase, exec_ch, exec_dch, actual, current_soc)

            day_final[start:end] = exec_purchase
            day_ch[start:end] = rec["charge"]
            day_dch[start:end] = rec["discharge"]
            day_em[start:end] = rec["emergency"]
            day_sp[start:end] = rec["spill"]
            day_soc[start:end] = rec["soc"]
            current_soc = float(rec["soc_close"])

        plan[day] = day_plan
        final[day] = day_final
        charge[day] = day_ch
        discharge[day] = day_dch
        soc[day] = day_soc
        emergency[day] = day_em
        spill[day] = day_sp

    eval_idx = rc.EVAL_DAYS
    plan_e = plan[eval_idx]
    final_e = final[eval_idx]
    em_e = emergency[eval_idx]
    up = np.maximum(final_e - plan_e, 0.0)
    down = np.maximum(plan_e - final_e, 0.0)
    price = rc.PRICE[None, :]
    plan_cost = (price * plan_e).sum(axis=1)
    adj_cost = (price * (1.5 * up - 0.5 * down)).sum(axis=1)
    em_cost = (rc.EMERGENCY_MULTIPLIER * price * em_e).sum(axis=1)
    total = plan_cost + adj_cost + em_cost
    return {
        "plan": plan_e,
        "adjusted": final_e,
        "charge": charge[eval_idx],
        "discharge": discharge[eval_idx],
        "soc": soc[eval_idx],
        "emergency": em_e,
        "spill": spill[eval_idx],
        "upward": up,
        "downward": down,
        "plan_cost": plan_cost,
        "adjustment_cost": adj_cost,
        "emergency_cost": em_cost,
        "total_cost": total,
        "soc_open": soc_open[eval_idx],
        "soc_close": soc[eval_idx, -1],
        "full_soc_open": soc_open,
        "metrics": {
            "total_cost": float(total.sum()),
            "plan_cost": float(plan_cost.sum()),
            "adjustment_cost": float(adj_cost.sum()),
            "emergency_cost": float(em_cost.sum()),
            "plan_kwh": float(plan_e.sum()),
            "final_kwh": float(final_e.sum()),
            "upward_kwh": float(up.sum()),
            "downward_kwh": float(down.sum()),
            "emergency_kwh": float(em_e.sum()),
            "spill_kwh": float(spill[eval_idx].sum()),
            "mean_soc": float(soc[eval_idx].mean()),
            "min_soc": float(soc[eval_idx].min()),
            "max_soc": float(soc[eval_idx].max()),
            "mean_soc_open": float(soc_open[eval_idx].mean()),
            "mean_soc_close": float(soc[eval_idx, -1].mean()),
            "charge_kwh": float(charge[eval_idx].sum()),
            "discharge_kwh": float(discharge[eval_idx].sum()),
        },
    }


def policy_label(horizon: str, recourse: str, tv: float) -> str:
    return f"{horizon}|{recourse}|tv={tv:.4f}"


def block_totals(values: np.ndarray) -> np.ndarray:
    return values.reshape(6, 24).sum(axis=1)


def split_interval_label(label: str) -> tuple[str, str]:
    start, end = str(label).split("-", 1)
    return start.strip(), end.strip()


def merge_emergency_windows(values: np.ndarray, tolerance: float = 1e-6) -> list[tuple[str, float]]:
    interval_start, interval_end = zip(*(split_interval_label(lab) for lab in rc.INTERVAL_LABELS))
    active = np.flatnonzero(values > tolerance)
    if active.size == 0:
        return []
    windows = []
    start = int(active[0])
    previous = int(active[0])
    for interval in active[1:]:
        interval = int(interval)
        if interval != previous + 1:
            windows.append(
                (f"{interval_start[start]}-{interval_end[previous]}", float(values[start : previous + 1].sum()))
            )
            start = interval
        previous = interval
    windows.append((f"{interval_start[start]}-{interval_end[previous]}", float(values[start : previous + 1].sum())))
    return windows


def write_tables(result: dict) -> None:
    report_rows = {
        date: int(np.flatnonzero(rc.REPORT_DAY_INDEX == pd.Timestamp(date))[0])
        for date in rc.REPORT_DATES
    }
    table_1 = pd.DataFrame(
        index=list(rc.REPORT_INTERVALS)
        + [
            "daily planned purchase (kWh)",
            "daily planned cost (yuan)",
            "daily final purchase (kWh)",
            "daily adjustment cost (yuan)",
            "daily emergency purchase (kWh)",
            "daily total cost (yuan)",
        ]
    )
    table_2_charge = pd.DataFrame(index=rc.FOUR_HOUR_LABELS)
    table_2_discharge = pd.DataFrame(index=rc.FOUR_HOUR_LABELS)
    table_2_soc = pd.DataFrame(index=["SOC at 0:00 (kWh)", "SOC at 24:00 (kWh)"])
    table_3_rows = []
    for date, row in report_rows.items():
        plan = result["plan"][row]
        table_1[date] = [plan[rc.LABEL_TO_INDEX[label]] for label in rc.REPORT_INTERVALS] + [
            plan.sum(),
            result["plan_cost"][row],
            result["adjusted"][row].sum(),
            result["adjustment_cost"][row],
            result["emergency"][row].sum(),
            result["total_cost"][row],
        ]
        table_2_charge[date] = block_totals(result["charge"][row])
        table_2_discharge[date] = block_totals(result["discharge"][row])
        table_2_soc[date] = [result["soc_open"][row], result["soc_close"][row]]
        windows = merge_emergency_windows(result["emergency"][row])
        if not windows:
            table_3_rows.append({"date": date, "window": "None", "purchase (kWh)": 0.0})
        else:
            for window, energy in windows:
                table_3_rows.append({"date": date, "window": window, "purchase (kWh)": energy})
    table_1.to_csv(OUTPUT_DIR / "table1.csv", encoding="utf-8-sig")
    table_2_charge.to_csv(OUTPUT_DIR / "table2_charge.csv", encoding="utf-8-sig")
    table_2_discharge.to_csv(OUTPUT_DIR / "table2_discharge.csv", encoding="utf-8-sig")
    table_2_soc.to_csv(OUTPUT_DIR / "table2_soc.csv", encoding="utf-8-sig")
    pd.DataFrame(table_3_rows).to_csv(OUTPUT_DIR / "table3_emergency.csv", encoding="utf-8-sig")
    monthly = pd.DataFrame(
        {"free-battery policy": result["total_cost"]},
        index=rc.REPORT_DAY_INDEX,
    ).resample("ME").sum()
    monthly.index = monthly.index.strftime("%Y-%m")
    monthly.to_csv(OUTPUT_DIR / "monthly_cost.csv", encoding="utf-8-sig")


def write_result3(result: dict) -> None:
    template = rc.TEMPLATE_FILE
    dest = OUTPUT_DIR / "result3.xlsx"
    shutil.copy2(template, dest)
    book = load_workbook(dest)
    plan_sheet = book[rc.PLAN_SHEET_NAME]
    adjustment_sheet = book[rc.ADJUSTMENT_SHEET_NAME]
    battery_sheet = book[rc.BATTERY_SHEET_NAME]
    emergency_sheet = book[rc.EMERGENCY_SHEET_NAME]
    for row, date in enumerate(rc.REPORT_DAY_INDEX):
        excel_row = row + 2
        for column, value in enumerate(result["plan"][row], start=2):
            plan_sheet.cell(excel_row, column).value = round(float(value), 4)
        plan_sheet.cell(excel_row, 146).value = round(float(result["plan"][row].sum()), 4)
        plan_sheet.cell(excel_row, 147).value = round(float(result["plan_cost"][row]), 4)
        for column, value in enumerate(result["adjusted"][row], start=2):
            adjustment_sheet.cell(excel_row, column).value = round(float(value), 4)
        adjustment_sheet.cell(excel_row, 146).value = round(float(result["adjusted"][row].sum()), 4)
        adjustment_sheet.cell(excel_row, 147).value = round(float(result["adjustment_cost"][row]), 4)
    battery_style_rows = [
        [copy.copy(battery_sheet.cell(row, column)._style) for column in range(1, 7)]
        for row in range(2, 8)
    ]
    if battery_sheet.max_row > 1:
        battery_sheet.delete_rows(2, battery_sheet.max_row - 1)
    for row, date in enumerate(rc.REPORT_DAY_INDEX):
        charge_blocks = block_totals(result["charge"][row])
        discharge_blocks = block_totals(result["discharge"][row])
        first_row = 2 + row * 6
        for block, label in enumerate(rc.FOUR_HOUR_LABELS):
            excel_row = first_row + block
            for column in range(1, 7):
                battery_sheet.cell(excel_row, column)._style = copy.copy(battery_style_rows[block][column - 1])
            if block == 0:
                battery_sheet.cell(excel_row, 1).value = date.to_pydatetime()
                battery_sheet.cell(excel_row, 5).value = "0:00"
                battery_sheet.cell(excel_row, 6).value = round(float(result["soc_open"][row]), 4)
            elif block == 1:
                battery_sheet.cell(excel_row, 5).value = "24:00"
                battery_sheet.cell(excel_row, 6).value = round(float(result["soc_close"][row]), 4)
            battery_sheet.cell(excel_row, 2).value = label
            battery_sheet.cell(excel_row, 3).value = round(float(charge_blocks[block]), 4)
            battery_sheet.cell(excel_row, 4).value = round(float(discharge_blocks[block]), 4)
    emergency_style_rows = [
        [copy.copy(emergency_sheet.cell(row, column)._style) for column in range(1, 4)]
        for row in (2, 3, 4)
    ]
    if emergency_sheet.max_row > 1:
        emergency_sheet.delete_rows(2, emergency_sheet.max_row - 1)
    excel_row = 2
    for row, date in enumerate(rc.REPORT_DAY_INDEX):
        windows = merge_emergency_windows(result["emergency"][row]) or [("None", 0.0)]
        for window_index, (window, energy) in enumerate(windows):
            if len(windows) == 1:
                style_index = 0
            elif window_index == 0:
                style_index = 0
            elif window_index == len(windows) - 1:
                style_index = 2
            else:
                style_index = 1
            for column in range(1, 4):
                emergency_sheet.cell(excel_row, column)._style = copy.copy(emergency_style_rows[style_index][column - 1])
            if window_index == 0:
                emergency_sheet.cell(excel_row, 1).value = date.to_pydatetime()
            emergency_sheet.cell(excel_row, 2).value = window
            emergency_sheet.cell(excel_row, 3).value = round(float(energy), 4)
            excel_row += 1
    book.save(dest)
    book.close()
    print("Written", dest)


def plot_paper_days(result: dict) -> None:
    hours = rc.SLOT_END_HOURS
    report_rows = {
        date: int(np.flatnonzero(rc.REPORT_DAY_INDEX == pd.Timestamp(date))[0])
        for date in rc.REPORT_DATES
    }
    figure, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
    for ax, date in zip(axes.ravel(), rc.REPORT_DATES):
        row = report_rows[date]
        ax.plot(hours, result["soc"][row], color="tab:purple", lw=1.2)
        ax.axhline(SOC_MIN, color="tab:red", ls="--", lw=0.7)
        ax.axhline(SOC_MAX, color="tab:red", ls="--", lw=0.7)
        ax.axhline(6000, color="grey", ls=":", lw=0.7)
        ax.set_title(date)
        ax.set_ylabel("SOC (kWh)")
        ax.set_xlabel("hour")
    figure.suptitle("Executed battery SOC on the four paper days (free-battery policy)")
    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "paper_days_soc.png", dpi=120)
    plt.close(figure)

    date = "2025-06-21"
    row = report_rows[date]
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    axes[0].plot(hours, rc.LOAD_KWH[rc.EVAL_DAYS[row]], label="load", lw=1.1)
    axes[0].plot(hours, rc.PV_KWH[rc.EVAL_DAYS[row]], label="PV", lw=1.1)
    axes[0].plot(hours, result["plan"][row], label="00:00 plan", lw=1.0)
    axes[0].plot(hours, result["adjusted"][row], label="final purchase", lw=1.0)
    axes[0].bar(hours, result["emergency"][row], width=0.14, color="tab:red", label="emergency")
    axes[0].set_ylabel("kWh / 10 min")
    axes[0].set_title(f"Free-battery execution on {date}")
    axes[0].legend(ncol=5, fontsize=7)
    axes[1].bar(hours, result["charge"][row], width=0.14, color="tab:green", label="charge")
    axes[1].bar(hours, -result["discharge"][row], width=0.14, color="tab:orange", label="discharge")
    axes[1].set_ylabel("kWh / 10 min")
    axes[1].legend(fontsize=7)
    axes[2].plot(hours, result["soc"][row], color="tab:purple")
    axes[2].axhline(SOC_MIN, color="tab:red", ls="--", lw=0.8)
    axes[2].axhline(SOC_MAX, color="tab:red", ls="--", lw=0.8)
    axes[2].set_ylabel("SOC kWh")
    axes[2].set_xlabel("hour")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "sample_2025-06-21.png", dpi=120)
    plt.close(fig)


def main() -> None:
    mean_p = float(rc.PRICE.mean())
    night_p = float(rc.PRICE[:36].mean())
    peak_p = float(rc.PRICE.max())
    salvage_grid = sorted(
        {
            0.0,
            0.25 * mean_p,
            0.5 * mean_p,
            0.75 * mean_p,
            1.0 * mean_p,
            1.25 * mean_p,
            0.5 * night_p,
            1.0 * night_p,
            0.5 * peak_p,
        }
    )
    jobs = list(product(("rest_of_day", "block"), ("greedy", "planned"), salvage_grid))
    print(f"Policy grid: {len(jobs)} combinations")
    print(f"mean price={mean_p:.4f} night={night_p:.4f} peak={peak_p:.4f}")
    rows = []
    best = None
    best_result = None
    t0 = time.perf_counter()
    for i, (horizon, recourse, tv) in enumerate(jobs, start=1):
        t_job = time.perf_counter()
        result = simulate_year(horizon, recourse, tv)
        m = result["metrics"]
        row = {
            "horizon": horizon,
            "recourse": recourse,
            "terminal_value": tv,
            **m,
            "delta_vs_v001": m["total_cost"] - V001_COST,
        }
        rows.append(row)
        print(
            f"[{i}/{len(jobs)}] {horizon:13s} {recourse:8s} tv={tv:.4f}  "
            f"cost={m['total_cost']:,.2f}  emerg={m['emergency_kwh']:,.0f}  "
            f"SOC={m['mean_soc']:.0f}  ({time.perf_counter() - t_job:.1f}s)"
        )
        if best is None or m["total_cost"] < best["total_cost"]:
            best = row
            best_result = result
    table = pd.DataFrame(rows).sort_values("total_cost")
    table.to_csv(OUTPUT_DIR / "policy_grid.csv", index=False, encoding="utf-8-sig")
    print("\n===== BEST =====")
    print(table.head(8).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    assert best_result is not None
    write_tables(best_result)
    write_result3(best_result)
    plot_paper_days(best_result)
    summary = {
        "parent": "v001",
        "v001_cost_yuan": V001_COST,
        "best": best,
        "elapsed_s": time.perf_counter() - t0,
        "n_policies": len(jobs),
        "quantiles": {"q00": Q0, "q_adj": Q_ADJ},
        "note": "Purchase still updates only at 0/6/12/18. Battery SOC carries overnight; issue-time LP covers remaining day or next block with no SOC pin; intra-block battery is greedy on actual or follows the LP schedule.",
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Elapsed", summary["elapsed_s"], "s")
    print("Best vs v001", best["delta_vs_v001"])


if __name__ == "__main__":
    main()
