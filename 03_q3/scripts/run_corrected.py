
"""问题 3 重跑：组员思路 100% 复现，只改正计费规则。

组员原口径（错误）：计划量先按原价付清；少买再额外收 0.5 倍违约
  => 少买时付 p*计划 + 0.5p*退掉量；优化器因此从不主动少买。

本文件口径（按题意）：
  - 真正买走的电：当前电价 p
  - 计划里退掉、不供电的部分：收 50% 违约金
  - 超出计划多买的部分：1.5p
  少买时：p*最终购电 + 0.5p*退掉量 = p*计划 - 0.5p*退掉量
  所以调整阶段目标里，少买系数是 -0.5p（能退回一半计划费），而不是 +0.5p。

其余：负荷/光伏预报、80%/70% 残差分位、每天 SOC 6000、6 小时滚动、
电池按计划充放、全年 2/1–12/31、八种更新组合对照，全部保持组员原样。

不要 git push。结果只写在 Q3_new/outputs/。
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import time
import warnings
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 40)
pd.set_option("display.width", 180)
plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.25, "font.size": 9})


def display(obj) -> None:
    """Notebook 的 display，在脚本里改成打印。"""
    if hasattr(obj, "to_string"):
        print(obj.to_string())
    else:
        print(obj)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_DIR = ROOT / "附件"
if not DATA_DIR.exists():
    DATA_DIR = ROOT.parent / "附件"
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 组员原笔记本算出的全年总费用，只作对照，不是这次重跑
TEAMMATE_STATIC_COST = 14_935_980.76
TEAMMATE_BEST_COST = 14_893_895.27
TEAMMATE_BEST_LABEL = "06:00 + 12:00"


def workbook_shape(path: Path) -> tuple[int, list[tuple[int, int]]]:
    '''Return worksheet count and worksheet dimensions without relying on non-English filenames.'''
    workbook = load_workbook(path, read_only=True, data_only=False)
    dimensions = [(sheet.max_row, sheet.max_column) for sheet in workbook.worksheets]
    workbook.close()
    return len(dimensions), dimensions


def find_source_workbook(sheet_count: int, dimensions: list[tuple[int, int]]) -> Path:
    '''Locate one attachment by its unique workbook structure.'''
    matches = []
    for candidate in DATA_DIR.glob("*.xlsx"):
        if candidate.name.startswith("~$"):
            continue
        if candidate.stem.lower().startswith("result"):
            continue
        count, shape = workbook_shape(candidate)
        if count == sheet_count and shape == dimensions:
            matches.append(candidate)
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one workbook with shape {dimensions}, found {matches}")
    return matches[0].resolve()


PRICE_FILE = find_source_workbook(1, [(145, 4)])
HISTORY_FILE = find_source_workbook(2, [(366, 145), (366, 145)])
PV_FORECAST_FILE = find_source_workbook(1, [(1461, 26)])
TEMPLATE_FILE = (DATA_DIR / "附件5" / "result3.xlsx").resolve()
RESULT_FILE = OUTPUT_DIR / "result3.xlsx"

print("Price workbook:", PRICE_FILE.name)
print("Historical load and PV workbook:", HISTORY_FILE.name)
print("PV forecast workbook:", PV_FORECAST_FILE.name)
print("Result template:", TEMPLATE_FILE)

# ===== cell 4 =====
INTERVALS_PER_DAY = 144
INTERVAL_HOURS = 1.0 / 6.0
BATTERY_CAPACITY_KWH = 12_000.0
SOC_MIN_KWH = 1_200.0
SOC_MAX_KWH = 10_800.0
SOC_TARGET_KWH = 6_000.0
BATTERY_POWER_KW = 5_000.0
BATTERY_INTERVAL_LIMIT_KWH = BATTERY_POWER_KW * INTERVAL_HOURS
CHARGE_EFFICIENCY = 0.90
DISCHARGE_EFFICIENCY = 0.90
EMERGENCY_MULTIPLIER = 5.0

ISSUE_HOURS = (0, 6, 12, 18)
PLAN_RESIDUAL_QUANTILE = 0.75
ADJUSTMENT_RESIDUAL_QUANTILE = 0.85
ADJUSTMENT_QUANTILES_BY_HOUR = {6: 0.85, 12: 0.85, 18: 0.80}
RESIDUAL_WINDOW_DAYS = 30
MIN_FORECAST_DAY = 14
TIE_BREAK_COST = 1e-7

REPORT_DATES = ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")
REPORT_INTERVALS = (
    "10:00-10:10", "12:00-12:10", "14:00-14:10",
    "16:00-16:10", "18:00-18:10", "20:00-20:10",
)
FOUR_HOUR_LABELS = (
    "0:00-4:00", "4:00-8:00", "8:00-12:00",
    "12:00-16:00", "16:00-20:00", "20:00-24:00",
)

template_book = load_workbook(TEMPLATE_FILE, read_only=True, data_only=False)
PLAN_SHEET_NAME, ADJUSTMENT_SHEET_NAME, BATTERY_SHEET_NAME, EMERGENCY_SHEET_NAME = template_book.sheetnames
template_plan_sheet = template_book[PLAN_SHEET_NAME]
template_header = [template_plan_sheet.cell(1, column).value for column in range(1, 148)]
INTERVAL_LABELS = [str(value).strip() for value in template_header[1:145]]
REPORT_DAY_INDEX = pd.DatetimeIndex(
    [pd.Timestamp(template_plan_sheet.cell(row, 1).value).normalize() for row in range(2, 336)]
)
template_book.close()

LABEL_TO_INDEX = {label: index for index, label in enumerate(INTERVAL_LABELS)}
SLOT_END_HOURS = np.arange(1, INTERVALS_PER_DAY + 1, dtype=float) * INTERVAL_HOURS
ISSUE_STARTS = {
    hour: (0 if hour == 0 else int(np.flatnonzero(np.isclose(SLOT_END_HOURS, hour))[0]))
    for hour in ISSUE_HOURS
}
BLOCK_BOUNDS = [ISSUE_STARTS[0], ISSUE_STARTS[6], ISSUE_STARTS[12], ISSUE_STARTS[18], INTERVALS_PER_DAY]

print("Evaluation dates:", REPORT_DAY_INDEX[0].date(), "to", REPORT_DAY_INDEX[-1].date())
print("Decision block bounds:", BLOCK_BOUNDS)
print("First and last interval labels:", INTERVAL_LABELS[0], INTERVAL_LABELS[-1])

# ===== cell 6 =====
price_frame = pd.read_excel(PRICE_FILE)
PRICE = pd.to_numeric(price_frame.iloc[:, 1], errors="raise").to_numpy(float)

history_book = pd.ExcelFile(HISTORY_FILE)
load_frame = history_book.parse(history_book.sheet_names[0])
pv_frame = history_book.parse(history_book.sheet_names[1])

DATES = pd.DatetimeIndex(pd.to_datetime(load_frame.iloc[:, 0])).normalize()
LOAD_KW = load_frame.iloc[:, 1:].to_numpy(float)
PV_KW = pv_frame.iloc[:, 1:].to_numpy(float)
LOAD_KWH = LOAD_KW * INTERVAL_HOURS
PV_KWH = PV_KW * INTERVAL_HOURS
NET_KWH = LOAD_KWH - PV_KWH
DAY_OF_WEEK = DATES.dayofweek.to_numpy()
DATE_TO_DAY = {date: index for index, date in enumerate(DATES)}
EVAL_DAYS = np.array([DATE_TO_DAY[date] for date in REPORT_DAY_INDEX], dtype=int)

forecast_frame = pd.read_excel(PV_FORECAST_FILE)
forecast_dates = pd.to_datetime(forecast_frame.iloc[:, 0].replace("", np.nan).ffill()).dt.normalize()
forecast_issue_hours = (
    forecast_frame.iloc[:, 1].astype(str).str.extract(r"(\d+):", expand=False).astype(int)
)
forecast_values = forecast_frame.iloc[:, 2:26].apply(pd.to_numeric, errors="raise").to_numpy(float)

PV_HOURLY_FORECAST = np.full((len(DATES), len(ISSUE_HOURS), 24), np.nan)
issue_to_position = {hour: position for position, hour in enumerate(ISSUE_HOURS)}
for row in range(len(forecast_frame)):
    day = DATE_TO_DAY[pd.Timestamp(forecast_dates.iloc[row])]
    issue_position = issue_to_position[int(forecast_issue_hours.iloc[row])]
    PV_HOURLY_FORECAST[day, issue_position] = forecast_values[row]

validation = pd.Series(
    {
        "historical days": len(DATES),
        "intervals per day": LOAD_KW.shape[1],
        "evaluation days": len(EVAL_DAYS),
        "missing load values": int(np.isnan(LOAD_KW).sum()),
        "missing realized PV values": int(np.isnan(PV_KW).sum()),
        "missing hourly forecast values": int(np.isnan(PV_HOURLY_FORECAST).sum()),
        "minimum tariff (yuan/kWh)": PRICE.min(),
        "maximum tariff (yuan/kWh)": PRICE.max(),
        "usable battery energy (kWh)": SOC_MAX_KWH - SOC_MIN_KWH,
        "interval battery limit (kWh)": BATTERY_INTERVAL_LIMIT_KWH,
    },
    name="value",
)
display(validation.to_frame())

assert PRICE.shape == (INTERVALS_PER_DAY,)
assert LOAD_KW.shape == PV_KW.shape == (365, INTERVALS_PER_DAY)
assert np.isfinite(PV_HOURLY_FORECAST).all()
assert np.array_equal(EVAL_DAYS, np.arange(31, 365))
assert (LOAD_KW >= 0).all() and (PV_KW >= 0).all() and (PRICE > 0).all()
print("All source-data checks passed.")

# ===== cell 7 =====
def base_load_forecast(day: int) -> np.ndarray:
    '''Forecast a full daily load profile from information available before the day.'''
    same_weekday = np.flatnonzero(DAY_OF_WEEK[:day] == DAY_OF_WEEK[day])[-4:]
    if same_weekday.size == 0:
        history = np.arange(max(0, day - 7), day)
    else:
        history = same_weekday
    weights = np.arange(1, len(history) + 1, dtype=float)
    weights /= weights.sum()
    return np.average(LOAD_KW[history], axis=0, weights=weights)


def load_forecast_at_issue(day: int, issue_hour: int) -> np.ndarray:
    '''Return the load forecast over the remaining horizon at one issue time.'''
    start = ISSUE_STARTS[issue_hour]
    base = base_load_forecast(day)
    remaining = base[start:].copy()
    if issue_hour == 0:
        return remaining

    observed_end = start
    observed_start = max(0, observed_end - 12)
    observed_actual = LOAD_KW[day, observed_start:observed_end]
    observed_base = base[observed_start:observed_end]
    level_ratio = observed_actual.sum() / max(observed_base.sum(), 1e-9)
    level_ratio = float(np.clip(level_ratio, 0.80, 1.20))
    elapsed = SLOT_END_HOURS[start:] - issue_hour
    decay = np.exp(-elapsed / 6.0)
    return remaining * (1.0 + (level_ratio - 1.0) * decay)


def pv_forecast_at_issue(day: int, issue_hour: int) -> np.ndarray:
    '''Interpolate the 24 hourly PV forecasts onto the remaining 10-minute grid.'''
    start = ISSUE_STARTS[issue_hour]
    issue_position = issue_to_position[issue_hour]
    hourly = PV_HOURLY_FORECAST[day, issue_position]
    if issue_hour == 0:
        anchor = PV_KW[day - 1, -1] if day > 0 else 0.0
    else:
        anchor = PV_KW[day, start]
    node_hours = np.arange(0, 25, dtype=float)
    node_values = np.concatenate([[anchor], hourly])
    target_hours = SLOT_END_HOURS[start:] - issue_hour
    return np.clip(np.interp(target_hours, node_hours, node_values), 0.0, None)


FORECASTS_BY_ISSUE = {}
for issue_hour in ISSUE_HOURS:
    start = ISSUE_STARTS[issue_hour]
    horizon = INTERVALS_PER_DAY - start
    load_forecasts = np.full((len(DATES), horizon), np.nan)
    pv_forecasts = np.full((len(DATES), horizon), np.nan)
    for day in range(MIN_FORECAST_DAY, len(DATES)):
        load_forecasts[day] = load_forecast_at_issue(day, issue_hour)
        pv_forecasts[day] = pv_forecast_at_issue(day, issue_hour)
    FORECASTS_BY_ISSUE[issue_hour] = {
        "load_kw": load_forecasts,
        "pv_kw": pv_forecasts,
        "net_kwh": (load_forecasts - pv_forecasts) * INTERVAL_HOURS,
    }

print("Causal load and PV forecast arrays constructed for all four issue times.")

# ===== cell 9 =====
def residual_buffer(day: int, issue_hour: int, quantile: float) -> np.ndarray:
    '''Causal per-interval residual quantile, smoothed with a 7-point median.'''
    start = ISSUE_STARTS[issue_hour]
    history_start = max(MIN_FORECAST_DAY, day - RESIDUAL_WINDOW_DAYS)
    history_days = np.arange(history_start, day)
    historical_actual = NET_KWH[history_days, start:]
    historical_raw = FORECASTS_BY_ISSUE[issue_hour]["net_kwh"][history_days]
    residuals = historical_actual - historical_raw
    buffer = np.quantile(residuals, quantile, axis=0)
    return pd.Series(buffer).rolling(7, center=True, min_periods=1).median().to_numpy()


def corrected_net_forecast(day: int, issue_hour: int, quantile: float | None) -> np.ndarray:
    '''Add a causal rolling residual quantile to the raw net-load forecast.'''
    raw = FORECASTS_BY_ISSUE[issue_hour]["net_kwh"][day]
    if quantile is None:
        return raw.copy()
    return raw + residual_buffer(day, issue_hour, quantile)


forecast_quality_rows = []
for issue_hour in ISSUE_HOURS:
    start = ISSUE_STARTS[issue_hour]
    actual_load = LOAD_KW[EVAL_DAYS, start:]
    actual_pv = PV_KW[EVAL_DAYS, start:]
    predicted_load = FORECASTS_BY_ISSUE[issue_hour]["load_kw"][EVAL_DAYS]
    predicted_pv = FORECASTS_BY_ISSUE[issue_hour]["pv_kw"][EVAL_DAYS]
    forecast_quality_rows.append(
        {
            "issue time": f"{issue_hour:02d}:00",
            "remaining points": predicted_pv.shape[1],
            "load MAE (kW)": np.abs(predicted_load - actual_load).mean(),
            "PV MAE (kW)": np.abs(predicted_pv - actual_pv).mean(),
            "net-load MAE (kW)": np.abs((predicted_load - predicted_pv) - (actual_load - actual_pv)).mean(),
        }
    )

forecast_quality = pd.DataFrame(forecast_quality_rows).set_index("issue time")
display(forecast_quality.round(2))

block_comparison_rows = []
zero_forecast = FORECASTS_BY_ISSUE[0]["net_kwh"][EVAL_DAYS]
for block, issue_hour in enumerate(ISSUE_HOURS):
    start, end = BLOCK_BOUNDS[block], BLOCK_BOUNDS[block + 1]
    actual = NET_KWH[EVAL_DAYS, start:end]
    initial = zero_forecast[:, start:end]
    latest = FORECASTS_BY_ISSUE[issue_hour]["net_kwh"][EVAL_DAYS, : end - start]
    block_comparison_rows.append(
        {
            "execution block": f"{issue_hour:02d}:00 to {ISSUE_HOURS[block + 1]:02d}:00" if block < 3 else "18:00 to day end",
            "0:00 net MAE (kWh/interval)": np.abs(initial - actual).mean(),
            "latest net MAE (kWh/interval)": np.abs(latest - actual).mean(),
        }
    )

block_forecast_comparison = pd.DataFrame(block_comparison_rows).set_index("execution block")
block_forecast_comparison["MAE reduction (%)"] = 100.0 * (
    1.0
    - block_forecast_comparison["latest net MAE (kWh/interval)"]
    / block_forecast_comparison["0:00 net MAE (kWh/interval)"]
)
display(block_forecast_comparison.round(2))

# ===== cell 11 =====
def solve_initial_schedule(
    target_net_kwh: np.ndarray,
    price: np.ndarray,
    opening_soc: float,
    terminal_soc: float,
) -> dict[str, np.ndarray]:
    '''Solve the 00:00 purchase and battery schedule as a linear program.'''
    horizon = len(target_net_kwh)
    purchase = slice(0, horizon)
    charge = slice(horizon, 2 * horizon)
    discharge = slice(2 * horizon, 3 * horizon)
    spill = slice(3 * horizon, 4 * horizon)
    soc = slice(4 * horizon, 5 * horizon)
    variable_count = 5 * horizon

    objective = np.zeros(variable_count)
    objective[purchase] = price
    objective[charge] = TIE_BREAK_COST
    objective[discharge] = TIE_BREAK_COST
    objective[spill] = TIE_BREAK_COST

    equality = lil_matrix((2 * horizon + 1, variable_count))
    rhs = np.zeros(2 * horizon + 1)
    for interval in range(horizon):
        equality[interval, purchase.start + interval] = 1.0
        equality[interval, discharge.start + interval] = 1.0
        equality[interval, charge.start + interval] = -1.0
        equality[interval, spill.start + interval] = -1.0
        rhs[interval] = target_net_kwh[interval]

        row = horizon + interval
        equality[row, soc.start + interval] = 1.0
        equality[row, charge.start + interval] = -CHARGE_EFFICIENCY
        equality[row, discharge.start + interval] = 1.0 / DISCHARGE_EFFICIENCY
        if interval == 0:
            rhs[row] = opening_soc
        else:
            equality[row, soc.start + interval - 1] = -1.0

    equality[-1, soc.stop - 1] = 1.0
    rhs[-1] = terminal_soc

    bounds = (
        [(0.0, None)] * horizon
        + [(0.0, BATTERY_INTERVAL_LIMIT_KWH)] * horizon
        + [(0.0, BATTERY_INTERVAL_LIMIT_KWH)] * horizon
        + [(0.0, None)] * horizon
        + [(SOC_MIN_KWH, SOC_MAX_KWH)] * horizon
    )
    solution = linprog(
        objective,
        A_eq=equality.tocsr(),
        b_eq=rhs,
        bounds=bounds,
        method="highs-ds",
    )
    if not solution.success:
        raise RuntimeError(f"Initial schedule failed: {solution.message}")
    vector = solution.x
    return {
        "purchase": vector[purchase],
        "charge": vector[charge],
        "discharge": vector[discharge],
        "spill": vector[spill],
        "soc": vector[soc],
    }


def solve_adjusted_schedule(
    target_net_kwh: np.ndarray,
    baseline_purchase: np.ndarray,
    price: np.ndarray,
    opening_soc: float,
    terminal_soc: float,
) -> dict[str, np.ndarray]:
    '''Solve one rolling adjustment over the remaining daily horizon.'''
    horizon = len(target_net_kwh)
    purchase = slice(0, horizon)
    upward = slice(horizon, 2 * horizon)
    downward = slice(2 * horizon, 3 * horizon)
    charge = slice(3 * horizon, 4 * horizon)
    discharge = slice(4 * horizon, 5 * horizon)
    spill = slice(5 * horizon, 6 * horizon)
    soc = slice(6 * horizon, 7 * horizon)
    variable_count = 7 * horizon

    objective = np.zeros(variable_count)
    # 计费修正：相对「已付 p*计划」，多买再付 1.5p，少买退回 0.5p
    objective[upward] = 1.5 * price
    objective[downward] = -0.5 * price
    objective[charge] = TIE_BREAK_COST
    objective[discharge] = TIE_BREAK_COST
    objective[spill] = TIE_BREAK_COST

    equality = lil_matrix((3 * horizon + 1, variable_count))
    rhs = np.zeros(3 * horizon + 1)
    for interval in range(horizon):
        equality[interval, purchase.start + interval] = 1.0
        equality[interval, upward.start + interval] = -1.0
        equality[interval, downward.start + interval] = 1.0
        rhs[interval] = baseline_purchase[interval]

        balance_row = horizon + interval
        equality[balance_row, purchase.start + interval] = 1.0
        equality[balance_row, discharge.start + interval] = 1.0
        equality[balance_row, charge.start + interval] = -1.0
        equality[balance_row, spill.start + interval] = -1.0
        rhs[balance_row] = target_net_kwh[interval]

        storage_row = 2 * horizon + interval
        equality[storage_row, soc.start + interval] = 1.0
        equality[storage_row, charge.start + interval] = -CHARGE_EFFICIENCY
        equality[storage_row, discharge.start + interval] = 1.0 / DISCHARGE_EFFICIENCY
        if interval == 0:
            rhs[storage_row] = opening_soc
        else:
            equality[storage_row, soc.start + interval - 1] = -1.0

    equality[-1, soc.stop - 1] = 1.0
    rhs[-1] = terminal_soc

    bounds = (
        [(0.0, None)] * horizon
        + [(0.0, None)] * horizon
        + [(0.0, None)] * horizon
        + [(0.0, BATTERY_INTERVAL_LIMIT_KWH)] * horizon
        + [(0.0, BATTERY_INTERVAL_LIMIT_KWH)] * horizon
        + [(0.0, None)] * horizon
        + [(SOC_MIN_KWH, SOC_MAX_KWH)] * horizon
    )
    solution = linprog(
        objective,
        A_eq=equality.tocsr(),
        b_eq=rhs,
        bounds=bounds,
        method="highs-ds",
    )
    if not solution.success:
        raise RuntimeError(f"Adjusted schedule failed: {solution.message}")
    vector = solution.x
    return {
        "purchase": vector[purchase],
        "upward": vector[upward],
        "downward": vector[downward],
        "charge": vector[charge],
        "discharge": vector[discharge],
        "spill": vector[spill],
        "soc": vector[soc],
    }

# ===== cell 13 =====
def storage_trajectory(charge: np.ndarray, discharge: np.ndarray, opening_soc: float) -> np.ndarray:
    '''Reconstruct the interval-end storage trajectory.'''
    changes = CHARGE_EFFICIENCY * charge - discharge / DISCHARGE_EFFICIENCY
    return opening_soc + np.cumsum(changes)


def settle_schedule(
    plan_purchase: np.ndarray,
    final_purchase: np.ndarray,
    charge: np.ndarray,
    discharge: np.ndarray,
    actual_net_kwh: np.ndarray,
    price: np.ndarray,
) -> dict[str, np.ndarray | float]:
    '''Settle one realized day under the problem's three-part cost rule.'''
    shortage = actual_net_kwh - (final_purchase + discharge - charge)
    emergency = np.maximum(shortage, 0.0)
    spill = np.maximum(-shortage, 0.0)
    upward = np.maximum(final_purchase - plan_purchase, 0.0)
    downward = np.maximum(plan_purchase - final_purchase, 0.0)
    plan_cost = float(price @ plan_purchase)
    # 总购电费（不含紧急）= p*计划 + 1.5p*多买 - 0.5p*退掉
    # 即：买走的按 p，退掉的按 0.5p 违约，多买的按 1.5p
    adjustment_cost = float(price @ (1.5 * upward - 0.5 * downward))
    emergency_cost = float(EMERGENCY_MULTIPLIER * price @ emergency)
    return {
        "emergency": emergency,
        "spill": spill,
        "upward": upward,
        "downward": downward,
        "plan_cost": plan_cost,
        "adjustment_cost": adjustment_cost,
        "emergency_cost": emergency_cost,
        "total_cost": plan_cost + adjustment_cost + emergency_cost,
    }


def allocate_result_arrays() -> dict[str, np.ndarray]:
    day_count = len(EVAL_DAYS)
    return {
        "plan": np.zeros((day_count, INTERVALS_PER_DAY)),
        "adjusted": np.zeros((day_count, INTERVALS_PER_DAY)),
        "charge": np.zeros((day_count, INTERVALS_PER_DAY)),
        "discharge": np.zeros((day_count, INTERVALS_PER_DAY)),
        "soc": np.zeros((day_count, INTERVALS_PER_DAY)),
        "emergency": np.zeros((day_count, INTERVALS_PER_DAY)),
        "spill": np.zeros((day_count, INTERVALS_PER_DAY)),
        "upward": np.zeros((day_count, INTERVALS_PER_DAY)),
        "downward": np.zeros((day_count, INTERVALS_PER_DAY)),
        "plan_cost": np.zeros(day_count),
        "adjustment_cost": np.zeros(day_count),
        "emergency_cost": np.zeros(day_count),
        "total_cost": np.zeros(day_count),
        "soc_open": np.full(day_count, SOC_TARGET_KWH),
        "soc_close": np.zeros(day_count),
    }


def store_settlement(result: dict[str, np.ndarray], row: int, settlement: dict) -> None:
    for key in ("emergency", "spill", "upward", "downward"):
        result[key][row] = settlement[key]
    for key in ("plan_cost", "adjustment_cost", "emergency_cost", "total_cost"):
        result[key][row] = settlement[key]

# ===== cell 14 =====
def adjustment_quantile_at(
    adj_quantile: float | dict[int, float] | None,
    issue_hour: int,
) -> float | None:
    '''Resolve the residual quantile used at one intraday issue time.'''
    if adj_quantile is None:
        if issue_hour in ADJUSTMENT_QUANTILES_BY_HOUR:
            return ADJUSTMENT_QUANTILES_BY_HOUR[issue_hour]
        return ADJUSTMENT_RESIDUAL_QUANTILE
    if isinstance(adj_quantile, dict):
        if issue_hour not in adj_quantile:
            raise KeyError(f"No adjustment quantile for {issue_hour:02d}:00")
        return adj_quantile[issue_hour]
    return adj_quantile


def solve_one_day(
    day: int,
    plan_quantile: float | None = PLAN_RESIDUAL_QUANTILE,
    adj_quantile: float | dict[int, float] | None = None,
) -> tuple[dict, dict]:
    '''Solve both benchmark policies for one independent daily subproblem.'''
    plan_target = corrected_net_forecast(day, 0, plan_quantile)
    plan_solution = solve_initial_schedule(
        plan_target,
        PRICE,
        SOC_TARGET_KWH,
        SOC_TARGET_KWH,
    )
    plan_purchase = plan_solution["purchase"]
    static_settlement = settle_schedule(
        plan_purchase,
        plan_purchase,
        plan_solution["charge"],
        plan_solution["discharge"],
        NET_KWH[day],
        PRICE,
    )
    static_day = {
        "plan": plan_purchase,
        "adjusted": plan_purchase,
        "charge": plan_solution["charge"],
        "discharge": plan_solution["discharge"],
        "soc": plan_solution["soc"],
        "soc_close": float(plan_solution["soc"][-1]),
        **static_settlement,
    }

    final_purchase = plan_purchase.copy()
    final_charge = np.zeros(INTERVALS_PER_DAY)
    final_discharge = np.zeros(INTERVALS_PER_DAY)
    current_soc = SOC_TARGET_KWH

    for block, issue_hour in enumerate(ISSUE_HOURS):
        start, end = BLOCK_BOUNDS[block], BLOCK_BOUNDS[block + 1]
        block_length = end - start
        if issue_hour == 0:
            stage_solution = plan_solution
        else:
            adjusted_target = corrected_net_forecast(
                day,
                issue_hour,
                adjustment_quantile_at(adj_quantile, issue_hour),
            )[:block_length]
            stage_solution = solve_adjusted_schedule(
                adjusted_target,
                plan_purchase[start:end],
                PRICE[start:end],
                current_soc,
                float(plan_solution["soc"][end - 1]),
            )
        final_purchase[start:end] = stage_solution["purchase"][:block_length]
        final_charge[start:end] = stage_solution["charge"][:block_length]
        final_discharge[start:end] = stage_solution["discharge"][:block_length]
        current_soc = float(stage_solution["soc"][block_length - 1])

    final_soc = storage_trajectory(final_charge, final_discharge, SOC_TARGET_KWH)
    rolling_settlement = settle_schedule(
        plan_purchase,
        final_purchase,
        final_charge,
        final_discharge,
        NET_KWH[day],
        PRICE,
    )
    rolling_day = {
        "plan": plan_purchase,
        "adjusted": final_purchase,
        "charge": final_charge,
        "discharge": final_discharge,
        "soc": final_soc,
        "soc_close": float(final_soc[-1]),
        **rolling_settlement,
    }
    return static_day, rolling_day


def pack_daily_results(daily_results: list[tuple[dict, dict]]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    '''Stack per-day static / rolling dicts into year-long policy arrays.'''
    static_policy = allocate_result_arrays()
    rolling_policy = allocate_result_arrays()
    matrix_keys = ("plan", "adjusted", "charge", "discharge", "soc", "emergency", "spill", "upward", "downward")
    scalar_keys = ("plan_cost", "adjustment_cost", "emergency_cost", "total_cost", "soc_close")
    for row, (static_day, rolling_day) in enumerate(daily_results):
        for key in matrix_keys:
            static_policy[key][row] = static_day[key]
            rolling_policy[key][row] = rolling_day[key]
        for key in scalar_keys:
            static_policy[key][row] = static_day[key]
            rolling_policy[key][row] = rolling_day[key]
    return static_policy, rolling_policy


def run_backtest(
    plan_quantile: float | None = PLAN_RESIDUAL_QUANTILE,
    adj_quantile: float | dict[int, float] | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    '''Solve every evaluation day for one day-ahead quantile and intraday quantile(s).'''
    daily_results = [
        solve_one_day(int(day), plan_quantile, adj_quantile) for day in EVAL_DAYS
    ]
    return pack_daily_results(daily_results)


def policy_summary(result: dict[str, np.ndarray]) -> pd.Series:
    return pd.Series(
        {
            "planned energy (kWh)": result["plan"].sum(),
            "final purchased energy (kWh)": result["adjusted"].sum(),
            "upward adjustment (kWh)": result["upward"].sum(),
            "downward adjustment (kWh)": result["downward"].sum(),
            "emergency energy (kWh)": result["emergency"].sum(),
            "days with emergency purchase": int((result["emergency"].sum(axis=1) > 1e-6).sum()),
            "unused surplus (kWh)": result["spill"].sum(),
            "planned purchase cost (yuan)": result["plan_cost"].sum(),
            "adjustment cost (yuan)": result["adjustment_cost"].sum(),
            "emergency cost (yuan)": result["emergency_cost"].sum(),
            "total cost (yuan)": result["total_cost"].sum(),
        }
    )


def combine_update_subset(
    update_hours: tuple[int, ...],
    static_policy: dict[str, np.ndarray] | None = None,
    rolling_policy: dict[str, np.ndarray] | None = None,
) -> dict[str, np.ndarray]:
    '''Combine independently feasible six-hour update blocks into one policy.'''
    static_policy = STATIC_POLICY if static_policy is None else static_policy
    rolling_policy = ROLLING_POLICY if rolling_policy is None else rolling_policy
    result = allocate_result_arrays()
    result["plan"] = static_policy["plan"].copy()
    result["adjusted"] = static_policy["adjusted"].copy()
    result["charge"] = static_policy["charge"].copy()
    result["discharge"] = static_policy["discharge"].copy()

    for issue_hour in update_hours:
        block = ISSUE_HOURS.index(issue_hour)
        start, end = BLOCK_BOUNDS[block], BLOCK_BOUNDS[block + 1]
        for key in ("adjusted", "charge", "discharge"):
            result[key][:, start:end] = rolling_policy[key][:, start:end]

    result["soc"] = np.vstack(
        [storage_trajectory(result["charge"][row], result["discharge"][row], SOC_TARGET_KWH)
         for row in range(len(EVAL_DAYS))]
    )
    result["soc_close"] = result["soc"][:, -1]
    shortage = NET_KWH[EVAL_DAYS] - (
        result["adjusted"] + result["discharge"] - result["charge"]
    )
    result["emergency"] = np.maximum(shortage, 0.0)
    result["spill"] = np.maximum(-shortage, 0.0)
    result["upward"] = np.maximum(result["adjusted"] - result["plan"], 0.0)
    result["downward"] = np.maximum(result["plan"] - result["adjusted"], 0.0)
    result["plan_cost"] = static_policy["plan_cost"].copy()
    result["adjustment_cost"] = (
        PRICE[None, :] * (1.5 * result["upward"] - 0.5 * result["downward"])
    ).sum(axis=1)
    result["emergency_cost"] = (
        EMERGENCY_MULTIPLIER * PRICE[None, :] * result["emergency"]
    ).sum(axis=1)
    result["total_cost"] = (
        result["plan_cost"] + result["adjustment_cost"] + result["emergency_cost"]
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Q3 corrected-billing backtest.")
    parser.add_argument("--plan-q", type=float, default=None, help="00:00 residual quantile")
    parser.add_argument(
        "--adj-q",
        type=str,
        default=None,
        help="One quantile for all updates, or three values q6,q12,q18",
    )
    args = parser.parse_args()
    plan_q = PLAN_RESIDUAL_QUANTILE if args.plan_q is None else args.plan_q
    adj_q: float | dict[int, float] = ADJUSTMENT_QUANTILES_BY_HOUR
    if args.adj_q:
        parts = [float(item.strip()) for item in args.adj_q.split(",")]
        if len(parts) == 1:
            adj_q = parts[0]
        elif len(parts) == 3:
            adj_q = {6: parts[0], 12: parts[1], 18: parts[2]}
        else:
            raise SystemExit("--adj-q must be one number or three comma-separated numbers")
    print("Quantiles: 00:00 =", plan_q, "  updates =", adj_q)

    start_time = time.perf_counter()
    STATIC_POLICY, ROLLING_POLICY = run_backtest(plan_q, adj_q)
    elapsed = time.perf_counter() - start_time
    print(f"Full chronological backtest completed in {elapsed:.1f} seconds.")

    update_subsets = [
        subset
        for subset_size in range(4)
        for subset in combinations(ISSUE_HOURS[1:], subset_size)
    ]
    SUBSET_POLICIES = {subset: combine_update_subset(subset) for subset in update_subsets}


    def subset_label(subset: tuple[int, ...]) -> str:
        if not subset:
            return "00:00 only"
        return " + ".join(f"{hour:02d}:00" for hour in subset)


    comparison = pd.DataFrame(
        {subset_label(subset): policy_summary(policy) for subset, policy in SUBSET_POLICIES.items()}
    ).T
    static_total = comparison.loc["00:00 only", "total cost (yuan)"]
    comparison["saving vs static (yuan)"] = static_total - comparison["total cost (yuan)"]
    comparison["saving vs static (%)"] = 100.0 * comparison["saving vs static (yuan)"] / static_total
    comparison = comparison.sort_values("total cost (yuan)")
    display(comparison.round(2))

    BEST_UPDATE_SUBSET = min(
        SUBSET_POLICIES,
        key=lambda subset: float(SUBSET_POLICIES[subset]["total_cost"].sum()),
    )
    BEST_UPDATE_LABEL = subset_label(BEST_UPDATE_SUBSET)
    FINAL_POLICY = SUBSET_POLICIES[BEST_UPDATE_SUBSET]
    print("Lowest-cost update set:", BEST_UPDATE_LABEL)

    monthly = pd.DataFrame(
        {
            "00:00 plan only": STATIC_POLICY["total_cost"],
            f"selected updates ({BEST_UPDATE_LABEL})": FINAL_POLICY["total_cost"],
        },
        index=REPORT_DAY_INDEX,
    ).resample("ME").sum()
    monthly.index = monthly.index.strftime("%Y-%m")
    display(monthly.round(2))

    axis = monthly.plot(figsize=(11, 3.8), marker="o")
    axis.set_title("Monthly realized electricity cost")
    axis.set_ylabel("yuan")
    axis.set_xlabel("month")
    plt.xticks(rotation=45)
    plt.tight_layout()
    axis.figure.savefig(OUTPUT_DIR / "monthly_cost.png", dpi=120)
    plt.close(axis.figure)

    # ===== cell 16 =====
    def feasibility_report(result: dict[str, np.ndarray]) -> pd.Series:
        previous_soc = np.column_stack([result["soc_open"], result["soc"][:, :-1]])
        storage_error = result["soc"] - (
            previous_soc
            + CHARGE_EFFICIENCY * result["charge"]
            - result["discharge"] / DISCHARGE_EFFICIENCY
        )
        realized_balance = (
            result["adjusted"]
            + result["emergency"]
            + PV_KWH[EVAL_DAYS]
            + result["discharge"]
            - LOAD_KWH[EVAL_DAYS]
            - result["charge"]
            - result["spill"]
        )
        return pd.Series(
            {
                "maximum absolute energy-balance error (kWh)": np.abs(realized_balance).max(),
                "maximum absolute storage-transition error (kWh)": np.abs(storage_error).max(),
                "minimum SOC (kWh)": result["soc"].min(),
                "maximum SOC (kWh)": result["soc"].max(),
                "maximum charge power (kW)": result["charge"].max() / INTERVAL_HOURS,
                "maximum discharge power (kW)": result["discharge"].max() / INTERVAL_HOURS,
                "maximum absolute day-end SOC error (kWh)": np.abs(result["soc_close"] - SOC_TARGET_KWH).max(),
                "negative final-purchase entries": int((result["adjusted"] < -1e-8).sum()),
                "simultaneous charge-discharge intervals": int(
                    ((result["charge"] > 1e-6) & (result["discharge"] > 1e-6)).sum()
                ),
            },
            name="value",
        )


    checks = feasibility_report(FINAL_POLICY)
    display(checks.to_frame())

    assert checks["maximum absolute energy-balance error (kWh)"] < 1e-5
    assert checks["maximum absolute storage-transition error (kWh)"] < 1e-5
    assert checks["minimum SOC (kWh)"] >= SOC_MIN_KWH - 1e-5
    assert checks["maximum SOC (kWh)"] <= SOC_MAX_KWH + 1e-5
    assert checks["maximum charge power (kW)"] <= BATTERY_POWER_KW + 1e-5
    assert checks["maximum discharge power (kW)"] <= BATTERY_POWER_KW + 1e-5
    assert checks["maximum absolute day-end SOC error (kWh)"] < 1e-5
    assert checks["negative final-purchase entries"] == 0
    assert checks["simultaneous charge-discharge intervals"] == 0
    print("All physical and accounting checks passed.")

    # ===== cell 18 =====
    REPORT_ROWS = {
        date: int(np.flatnonzero(REPORT_DAY_INDEX == pd.Timestamp(date))[0])
        for date in REPORT_DATES
    }


    def block_totals(values: np.ndarray) -> np.ndarray:
        return values.reshape(6, 24).sum(axis=1)


    def split_interval_label(label: str) -> tuple[str, str]:
        start, end = str(label).split("-", 1)
        return start.strip(), end.strip()


    INTERVAL_START, INTERVAL_END = zip(*(split_interval_label(label) for label in INTERVAL_LABELS))


    def merge_emergency_windows(values: np.ndarray, tolerance: float = 1e-6) -> list[tuple[str, float]]:
        '''Merge consecutive positive emergency intervals into reporting windows.'''
        active = np.flatnonzero(values > tolerance)
        if active.size == 0:
            return []
        windows = []
        start = int(active[0])
        previous = int(active[0])
        for interval in active[1:]:
            interval = int(interval)
            if interval != previous + 1:
                label = f"{INTERVAL_START[start]}-{INTERVAL_END[previous]}"
                windows.append((label, float(values[start : previous + 1].sum())))
                start = interval
            previous = interval
        label = f"{INTERVAL_START[start]}-{INTERVAL_END[previous]}"
        windows.append((label, float(values[start : previous + 1].sum())))
        return windows


    table_1 = pd.DataFrame(index=list(REPORT_INTERVALS) + [
        "daily planned purchase (kWh)",
        "daily planned cost (yuan)",
        "daily final purchase (kWh)",
        "daily adjustment cost (yuan)",
        "daily emergency purchase (kWh)",
        "daily total cost (yuan)",
    ])
    table_2_charge = pd.DataFrame(index=FOUR_HOUR_LABELS)
    table_2_discharge = pd.DataFrame(index=FOUR_HOUR_LABELS)
    table_2_soc = pd.DataFrame(index=["SOC at 0:00 (kWh)", "SOC at 24:00 (kWh)"])
    table_3_rows = []

    for date, row in REPORT_ROWS.items():
        plan = FINAL_POLICY["plan"][row]
        table_1[date] = [plan[LABEL_TO_INDEX[label]] for label in REPORT_INTERVALS] + [
            plan.sum(),
            FINAL_POLICY["plan_cost"][row],
            FINAL_POLICY["adjusted"][row].sum(),
            FINAL_POLICY["adjustment_cost"][row],
            FINAL_POLICY["emergency"][row].sum(),
            FINAL_POLICY["total_cost"][row],
        ]
        table_2_charge[date] = block_totals(FINAL_POLICY["charge"][row])
        table_2_discharge[date] = block_totals(FINAL_POLICY["discharge"][row])
        table_2_soc[date] = [FINAL_POLICY["soc_open"][row], FINAL_POLICY["soc_close"][row]]
        windows = merge_emergency_windows(FINAL_POLICY["emergency"][row])
        if not windows:
            table_3_rows.append({"date": date, "window": "None", "purchase (kWh)": 0.0})
        else:
            for window, energy in windows:
                table_3_rows.append({"date": date, "window": window, "purchase (kWh)": energy})

    table_3 = pd.DataFrame(table_3_rows)

    print("Table 1 - purchase results on the four requested dates")
    display(table_1.round(2))
    print("Table 2a - four-hour charge energy")
    display(table_2_charge.round(2))
    print("Table 2b - four-hour discharge energy")
    display(table_2_discharge.round(2))
    print("Table 2c - boundary storage energy")
    display(table_2_soc.round(2))
    print("Table 3 - emergency-purchase windows")
    display(table_3.round(2))

    # ===== cell 19 =====
    sample_date = "2025-06-21"
    sample_row = REPORT_ROWS[sample_date]
    hours = SLOT_END_HOURS

    figure, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    axes[0].plot(hours, LOAD_KWH[EVAL_DAYS[sample_row]], label="realized load", linewidth=1.2)
    axes[0].plot(hours, PV_KWH[EVAL_DAYS[sample_row]], label="realized PV", linewidth=1.2)
    axes[0].plot(hours, FINAL_POLICY["plan"][sample_row], label="00:00 plan", linewidth=1.0)
    axes[0].plot(hours, FINAL_POLICY["adjusted"][sample_row], label="final purchase", linewidth=1.0)
    axes[0].bar(hours, FINAL_POLICY["emergency"][sample_row], width=0.14, label="emergency", color="tab:red")
    axes[0].set_ylabel("kWh per interval")
    axes[0].set_title(f"Rolling schedule on {sample_date}")
    axes[0].legend(ncol=5, fontsize=7)

    axes[1].bar(hours, FINAL_POLICY["charge"][sample_row], width=0.14, label="charge", color="tab:green")
    axes[1].bar(hours, -FINAL_POLICY["discharge"][sample_row], width=0.14, label="discharge", color="tab:orange")
    axes[1].set_ylabel("kWh per interval")
    axes[1].legend(fontsize=7)

    axes[2].plot(hours, FINAL_POLICY["soc"][sample_row], color="tab:purple", label="stored energy")
    axes[2].axhline(SOC_MIN_KWH, color="tab:red", linestyle="--", linewidth=0.8)
    axes[2].axhline(SOC_MAX_KWH, color="tab:red", linestyle="--", linewidth=0.8, label="SOC limits")
    axes[2].set_xlabel("hour")
    axes[2].set_ylabel("kWh")
    axes[2].legend(fontsize=7)

    for update_hour in ISSUE_HOURS[1:]:
        for axis in axes:
            axis.axvline(update_hour, color="grey", linestyle=":", linewidth=0.8)

    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "sample_2025-06-21.png", dpi=120)
    plt.close(figure)

    # ===== cell 21 =====
    def copy_cell_style(source, destination) -> None:
        if source.has_style:
            destination._style = copy.copy(source._style)
        if source.number_format:
            destination.number_format = source.number_format
        destination.alignment = copy.copy(source.alignment)
        destination.protection = copy.copy(source.protection)


    shutil.copy2(TEMPLATE_FILE, RESULT_FILE)
    result_book = load_workbook(RESULT_FILE)
    plan_sheet = result_book[PLAN_SHEET_NAME]
    adjustment_sheet = result_book[ADJUSTMENT_SHEET_NAME]
    battery_sheet = result_book[BATTERY_SHEET_NAME]
    emergency_sheet = result_book[EMERGENCY_SHEET_NAME]

    for row, date in enumerate(REPORT_DAY_INDEX):
        excel_row = row + 2
        assert pd.Timestamp(plan_sheet.cell(excel_row, 1).value).normalize() == date
        assert pd.Timestamp(adjustment_sheet.cell(excel_row, 1).value).normalize() == date

        for column, value in enumerate(FINAL_POLICY["plan"][row], start=2):
            plan_sheet.cell(excel_row, column).value = round(float(value), 4)
        plan_sheet.cell(excel_row, 146).value = round(float(FINAL_POLICY["plan"][row].sum()), 4)
        plan_sheet.cell(excel_row, 147).value = round(float(FINAL_POLICY["plan_cost"][row]), 4)

        for column, value in enumerate(FINAL_POLICY["adjusted"][row], start=2):
            adjustment_sheet.cell(excel_row, column).value = round(float(value), 4)
        adjustment_sheet.cell(excel_row, 146).value = round(float(FINAL_POLICY["adjusted"][row].sum()), 4)
        adjustment_sheet.cell(excel_row, 147).value = round(float(FINAL_POLICY["adjustment_cost"][row]), 4)

    battery_style_rows = [
        [copy.copy(battery_sheet.cell(row, column)._style) for column in range(1, 7)]
        for row in range(2, 8)
    ]
    if battery_sheet.max_row > 1:
        battery_sheet.delete_rows(2, battery_sheet.max_row - 1)

    for row, date in enumerate(REPORT_DAY_INDEX):
        charge_blocks = block_totals(FINAL_POLICY["charge"][row])
        discharge_blocks = block_totals(FINAL_POLICY["discharge"][row])
        first_row = 2 + row * 6
        for block, label in enumerate(FOUR_HOUR_LABELS):
            excel_row = first_row + block
            for column in range(1, 7):
                battery_sheet.cell(excel_row, column)._style = copy.copy(battery_style_rows[block][column - 1])
            if block == 0:
                battery_sheet.cell(excel_row, 1).value = date.to_pydatetime()
                battery_sheet.cell(excel_row, 5).value = "0:00"
                battery_sheet.cell(excel_row, 6).value = round(float(FINAL_POLICY["soc_open"][row]), 4)
            elif block == 1:
                battery_sheet.cell(excel_row, 5).value = "24:00"
                battery_sheet.cell(excel_row, 6).value = round(float(FINAL_POLICY["soc_close"][row]), 4)
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
    for row, date in enumerate(REPORT_DAY_INDEX):
        windows = merge_emergency_windows(FINAL_POLICY["emergency"][row])
        if not windows:
            windows = [("None", 0.0)]
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

    result_book.save(RESULT_FILE)
    result_book.close()
    print("Written:", RESULT_FILE)

    # ===== cell 22 =====
    check_book = load_workbook(RESULT_FILE, read_only=True, data_only=True)
    check_plan = check_book[PLAN_SHEET_NAME]
    check_adjustment = check_book[ADJUSTMENT_SHEET_NAME]
    check_battery = check_book[BATTERY_SHEET_NAME]
    check_emergency = check_book[EMERGENCY_SHEET_NAME]

    plan_matrix = np.array(
        [[cell.value for cell in row] for row in check_plan.iter_rows(min_row=2, max_row=335, min_col=2, max_col=145)],
        dtype=float,
    )
    adjustment_matrix = np.array(
        [[cell.value for cell in row] for row in check_adjustment.iter_rows(min_row=2, max_row=335, min_col=2, max_col=145)],
        dtype=float,
    )
    plan_totals = np.array(
        [row[0].value for row in check_plan.iter_rows(min_row=2, max_row=335, min_col=146, max_col=146)],
        dtype=float,
    )
    adjustment_totals = np.array(
        [row[0].value for row in check_adjustment.iter_rows(min_row=2, max_row=335, min_col=146, max_col=146)],
        dtype=float,
    )

    export_checks = pd.Series(
        {
            "plan matrix shape": plan_matrix.shape,
            "adjustment matrix shape": adjustment_matrix.shape,
            "missing plan cells": int(np.isnan(plan_matrix).sum()),
            "missing adjustment cells": int(np.isnan(adjustment_matrix).sum()),
            "maximum plan export difference (kWh)": np.abs(plan_matrix - FINAL_POLICY["plan"]).max(),
            "maximum adjustment export difference (kWh)": np.abs(adjustment_matrix - FINAL_POLICY["adjusted"]).max(),
            "maximum plan row-total error (kWh)": np.abs(plan_totals - plan_matrix.sum(axis=1)).max(),
            "maximum adjustment row-total error (kWh)": np.abs(adjustment_totals - adjustment_matrix.sum(axis=1)).max(),
            "battery data rows": check_battery.max_row - 1,
            "expected battery data rows": len(EVAL_DAYS) * 6,
            "emergency data rows": check_emergency.max_row - 1,
        },
        name="value",
    )
    display(export_checks.to_frame())

    assert export_checks["missing plan cells"] == 0
    assert export_checks["missing adjustment cells"] == 0
    assert export_checks["maximum plan export difference (kWh)"] < 1e-3
    assert export_checks["maximum adjustment export difference (kWh)"] < 1e-3
    assert export_checks["maximum plan row-total error (kWh)"] < 1e-2
    assert export_checks["maximum adjustment row-total error (kWh)"] < 1e-2
    assert export_checks["battery data rows"] == len(EVAL_DAYS) * 6
    check_book.close()
    print("result3.xlsx was reopened and verified successfully.")

    # ===== cell 24 =====
    static_cost = float(STATIC_POLICY["total_cost"].sum())
    selected_cost = float(FINAL_POLICY["total_cost"].sum())
    saving = static_cost - selected_cost
    saving_rate = 100.0 * saving / static_cost
    static_emergency = float(STATIC_POLICY["emergency"].sum())
    selected_emergency = float(FINAL_POLICY["emergency"].sum())

    if BEST_UPDATE_SUBSET:
        recommendation = f"Use intraday forecasts at {BEST_UPDATE_LABEL} for rolling adjustments."
        reason = "The reduction in emergency-purchase cost exceeds the added adjustment cost."
    else:
        recommendation = "Keep the 00:00 plan and do not use routine intraday adjustments under the stated fees."
        reason = "The adjustment penalties exceed the emergency-purchase savings."

    conclusion_text = f'''
    ### Executed conclusion

    - **Recommendation:** {recommendation}
    - **00:00-only total cost:** {static_cost:,.2f} yuan.
    - **Selected-policy total cost:** {selected_cost:,.2f} yuan.
    - **Saving from the selected updates:** {saving:,.2f} yuan ({saving_rate:.2f}%).
    - **Emergency energy:** {static_emergency:,.2f} kWh without updates versus {selected_emergency:,.2f} kWh with the selected updates.
    - **Economic explanation:** {reason}

    The exported `result3.xlsx` uses the lowest-cost update set evaluated above.
    '''
    print(conclusion_text)
    print(
        "对照组员原口径（计费未改正、决策也不同）："
        f"只信 0:00 {TEAMMATE_STATIC_COST:,.2f} 元，"
        f"其最优 {TEAMMATE_BEST_LABEL} {TEAMMATE_BEST_COST:,.2f} 元。"
    )
    print(f"本次只信 0:00 应与组员几乎相同（0:00 计划未改计费）：{static_cost:,.2f} 元。")

    comparison.to_csv(OUTPUT_DIR / "subset_comparison.csv", encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "monthly_cost.csv", encoding="utf-8-sig")
    table_1.to_csv(OUTPUT_DIR / "table1.csv", encoding="utf-8-sig")
    table_2_charge.to_csv(OUTPUT_DIR / "table2_charge.csv", encoding="utf-8-sig")
    table_2_discharge.to_csv(OUTPUT_DIR / "table2_discharge.csv", encoding="utf-8-sig")
    table_2_soc.to_csv(OUTPUT_DIR / "table2_soc.csv", encoding="utf-8-sig")
    table_3.to_csv(OUTPUT_DIR / "table3_emergency.csv", encoding="utf-8-sig")
    forecast_quality.to_csv(OUTPUT_DIR / "forecast_quality.csv", encoding="utf-8-sig")
    block_forecast_comparison.to_csv(OUTPUT_DIR / "block_forecast_mae.csv", encoding="utf-8-sig")
    summary = {
        "billing": "take_at_p_cancel_at_0.5p_extra_at_1.5p",
        "plan_quantile": plan_q,
        "adjustment_quantiles": adj_q if not isinstance(adj_q, dict) else {str(k): v for k, v in adj_q.items()},
        "static_cost_yuan": static_cost,
        "selected_cost_yuan": selected_cost,
        "selected_updates": BEST_UPDATE_LABEL,
        "saving_yuan": saving,
        "saving_pct": saving_rate,
        "static_emergency_kwh": static_emergency,
        "selected_emergency_kwh": selected_emergency,
        "teammate_static_cost_yuan": TEAMMATE_STATIC_COST,
        "teammate_best_cost_yuan": TEAMMATE_BEST_COST,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CSV/JSON written under", OUTPUT_DIR)
