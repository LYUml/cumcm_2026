"""Causal price-model comparison for Q4-2.

Every candidate is evaluated with the same Q2 net-load scenarios, four-hour
scenario tree, physical feedback controller, chronology, and realized-price
settlement.  The oracle knows the realized daily price and is a lower-bound
benchmark, not an implementable policy.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import lil_matrix
from sklearn.linear_model import ElasticNetCV, RidgeCV
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02_q2/src"))
sys.path.insert(0, str(ROOT / "02_q2/scripts"))

from q2_model import (  # noqa: E402
    DT_HOURS, ENERGY_MAX, ETA_CHARGE, ETA_DISCHARGE,
    SOC_INITIAL, SOC_MAX, SOC_MIN, read_inputs,
)
from q2_near_optimal import (  # noqa: E402
    execute_feedback, hierarchical_tree_groups, split_residual_scenarios,
)
from q2_availability import complete_residual_candidates  # noqa: E402
from run_final import warmup, one_interval  # noqa: E402

OUT = ROOT / "04_q4/outputs/q4_2_comparison"
START_DAY = 31
NS = 12
STAGE = 24
FLOOR = 3000.0
PLANNING_PENALTY = 4.5
EPS = 1e-4


def read_prices() -> np.ndarray:
    frame = pd.read_excel(ROOT / "00_problem/appendix/附件4.xlsx")
    values = frame.iloc[:, 1:].apply(pd.to_numeric, errors="raise").to_numpy(float)
    if values.shape != (365, 144) or np.isnan(values).any() or (values < 0).any():
        raise ValueError(f"Unexpected Attachment 4 price matrix: {values.shape}")
    return values


def price_features(price: np.ndarray, day: int, dates: pd.DatetimeIndex) -> np.ndarray:
    """Pooled slot-level ARX features available at midnight of ``day``."""
    slots = np.arange(144)
    angle = 2 * np.pi * slots / 144
    weekday = np.zeros((144, 7))
    weekday[:, dates[day].dayofweek] = 1.0
    return np.column_stack([
        price[day - 1], price[day - 2], price[day - 7],
        np.full(144, price[day - 1].mean()),
        np.full(144, price[day - 7].mean()),
        np.sin(angle), np.cos(angle), np.sin(2 * angle), np.cos(2 * angle),
        weekday,
    ])


def fit_arx(price: np.ndarray, dates: pd.DatetimeIndex, day: int, kind: str):
    start = max(7, day - 90)
    days = np.arange(start, day)
    x = np.vstack([price_features(price, int(j), dates) for j in days])
    y = np.concatenate([price[j] for j in days])
    scaler = StandardScaler().fit(x)
    xs = scaler.transform(x)
    # Day-blocked expanding folds; validation is always later than training.
    folds = []
    if len(days) >= 12:
        for frac in (0.55, 0.70, 0.85):
            cut = max(3, int(len(days) * frac))
            stop = min(len(days), cut + max(1, len(days) // 10))
            train = np.arange(cut * 144)
            valid = np.arange(cut * 144, stop * 144)
            if len(valid):
                folds.append((train, valid))
    if not folds:
        folds = [(np.arange(max(144, len(y) - 144)), np.arange(max(144, len(y) - 144), len(y)))]
    if kind == "ridge_arx":
        model = RidgeCV(alphas=np.logspace(-3, 3, 13), cv=folds)
    elif kind == "elastic_net_arx":
        model = ElasticNetCV(
            l1_ratio=[0.05, 0.2, 0.5, 0.8, 1.0],
            alphas=np.logspace(-5, -1, 12), cv=folds,
            max_iter=10000, n_jobs=-1,
        )
    else:
        raise ValueError(kind)
    model.fit(xs, y)
    return scaler, model


def generate_price_forecasts(price: np.ndarray, dates: pd.DatetimeIndex):
    names = ("seasonal_naive_7d", "weekday_mean_4w", "ridge_arx", "elastic_net_arx")
    forecasts = {name: np.full_like(price, np.nan) for name in names}
    diagnostics = {name: [] for name in names}
    fitted = {}
    for day in range(7, len(price)):
        forecasts["seasonal_naive_7d"][day] = price[day - 7]
        available = [day - lag for lag in (7, 14, 21, 28) if day - lag >= 0]
        forecasts["weekday_mean_4w"][day] = price[available].mean(axis=0)
        for kind in ("ridge_arx", "elastic_net_arx"):
            # With very little January history, use the transparent weekly baseline.
            if day < 21:
                forecasts[kind][day] = price[day - 7]
                continue
            if kind not in fitted or day % 7 == 0:
                fitted[kind] = fit_arx(price, dates, day, kind)
            scaler, model = fitted[kind]
            forecasts[kind][day] = np.maximum(
                model.predict(scaler.transform(price_features(price, day, dates))), 0.0
            )
            diagnostics[kind].append({
                "day": str(dates[day].date()),
                "regularization": float(getattr(model, "alpha_", np.nan)),
                "l1_ratio": float(getattr(model, "l1_ratio_", np.nan)),
            })
    return forecasts, diagnostics


def chosen_history(day: int, count: int = NS) -> np.ndarray:
    candidates = complete_residual_candidates(day, 56)
    matching = candidates[(day - candidates) % 7 == 0]
    remaining = candidates[~np.isin(candidates, matching)][::-1]
    return np.concatenate([matching[::-1], remaining])[:count]


def price_scenarios(price: np.ndarray, forecast: np.ndarray, day: int) -> np.ndarray:
    chosen = chosen_history(day)
    residuals = np.asarray([price[j] - forecast[j] for j in chosen])
    if np.isnan(residuals).any():
        raise RuntimeError(f"Unavailable historical price residual on day {day}")
    return np.maximum(forecast[day][None, :] + residuals, 0.0)


def solve_joint_plan(net_scenarios_kw: np.ndarray, price_paths: np.ndarray,
                     initial_soc: float, terminal_floor: float = FLOOR,
                     planning_penalty: float = PLANNING_PENALTY,
                     tree_signal: str = "net") -> np.ndarray:
    """Q2 adaptive LP with paired net-load and price scenario paths."""
    net_scenarios_kw = np.asarray(net_scenarios_kw, float)
    price_paths = np.asarray(price_paths, float)
    ns, nt = net_scenarios_kw.shape
    if price_paths.shape != (ns, nt):
        raise ValueError("Net-load and price scenarios must be paired")
    g0 = 0
    c0 = nt
    d0 = c0 + ns * nt
    s0 = d0 + ns * nt
    e0 = s0 + ns * nt
    w0 = e0 + ns * nt
    nv = w0 + ns * nt
    obj = np.zeros(nv)
    obj[g0:c0] = price_paths.mean(axis=0)
    for k in range(ns):
        obj[c0 + k*nt:c0 + (k+1)*nt] = EPS / ns
        obj[d0 + k*nt:d0 + (k+1)*nt] = EPS / ns
        obj[e0 + k*nt:e0 + (k+1)*nt] = planning_penalty * price_paths[k] / ns

    if tree_signal == "net":
        signal = net_scenarios_kw
    elif tree_signal == "joint":
        # Standardization prevents the kW scale from overwhelming price when
        # clustering the observed history at each four-hour branch.
        net_scale = np.maximum(np.std(net_scenarios_kw, axis=0), 1e-6)
        price_scale = np.maximum(np.std(price_paths, axis=0), 1e-6)
        signal = np.concatenate([
            (net_scenarios_kw - net_scenarios_kw.mean(axis=0)) / net_scale,
            (price_paths - price_paths.mean(axis=0)) / price_scale,
        ], axis=1)
        # Interleave the two 144-slot signals so each 4-hour tree stage sees
        # the matching net-load and price history.
        signal = signal.reshape(ns, 2, nt).transpose(0, 2, 1).reshape(ns, 2*nt)
    else:
        raise ValueError(tree_signal)
    tree_stage = STAGE if tree_signal == "net" else 2 * STAGE
    groups_raw = hierarchical_tree_groups(signal, tree_stage)
    groups = groups_raw if tree_signal == "net" else groups_raw[:, ::2]
    pairs = []
    for t in range(nt):
        for group in np.unique(groups[:, t]):
            members = np.flatnonzero(groups[:, t] == group)
            pairs.extend((t, int(members[0]), int(k)) for k in members[1:])
    base_rows = 2 * ns * nt
    aeq = lil_matrix((base_rows + 2 * len(pairs), nv))
    beq = np.zeros(base_rows + 2 * len(pairs))
    for k in range(ns):
        for t in range(nt):
            row = k*nt + t
            aeq[row, g0+t] = 1
            aeq[row, c0+k*nt+t] = -1
            aeq[row, d0+k*nt+t] = 1
            aeq[row, e0+k*nt+t] = 1
            aeq[row, w0+k*nt+t] = -1
            beq[row] = net_scenarios_kw[k, t] * DT_HOURS
            row = ns*nt + k*nt + t
            aeq[row, s0+k*nt+t] = 1
            aeq[row, c0+k*nt+t] = -ETA_CHARGE
            aeq[row, d0+k*nt+t] = 1 / ETA_DISCHARGE
            if t:
                aeq[row, s0+k*nt+t-1] = -1
            else:
                beq[row] = initial_soc
    for q, (t, ref, k) in enumerate(pairs):
        row = base_rows + 2*q
        aeq[row, c0+k*nt+t] = 1
        aeq[row, c0+ref*nt+t] = -1
        aeq[row+1, d0+k*nt+t] = 1
        aeq[row+1, d0+ref*nt+t] = -1
    bounds = (
        [(0, None)] * nt
        + [(0, ENERGY_MAX)] * (ns*nt)
        + [(0, ENERGY_MAX)] * (ns*nt)
        + [(SOC_MIN, SOC_MAX)] * (ns*nt)
        + [(0, None)] * (ns*nt)
        + [(0, None)] * (ns*nt)
    )
    aub = lil_matrix((ns, nv))
    bub = np.full(ns, -terminal_floor)
    for k in range(ns):
        aub[k, s0+(k+1)*nt-1] = -1
    result = linprog(obj, A_ub=aub.tocsr(), b_ub=bub,
                     A_eq=aeq.tocsr(), b_eq=beq, bounds=bounds, method="highs")
    if not result.success:
        raise RuntimeError(result.message)
    return result.x[g0:c0]


def run_policy(name: str, forecast: np.ndarray, prices: np.ndarray,
               dates: pd.DatetimeIndex, load: np.ndarray, pv: np.ndarray,
               net: np.ndarray, oracle: bool = False,
               price_mode: str = "joint", terminal_floor: float = FLOOR,
               planning_penalty: float = PLANNING_PENALTY,
               tree_signal: str = "net"):
    soc_midnight, pending = warmup(net)
    rows, grids, traces = [], [], []
    prior_flow = None
    tic = time.perf_counter()
    for day in range(START_DAY, 365):
        net_paths = split_residual_scenarios(load[:day], pv[:day], day, NS)
        if oracle:
            p_paths = np.repeat(prices[day][None, :], NS, axis=0)
        elif price_mode == "point":
            p_paths = np.repeat(forecast[day][None, :], NS, axis=0)
        elif price_mode == "joint":
            p_paths = price_scenarios(prices, forecast, day)
        else:
            raise ValueError(price_mode)
        grid = solve_joint_plan(net_paths, p_paths, soc_midnight,
                                terminal_floor=terminal_floor,
                                planning_penalty=planning_penalty,
                                tree_signal=tree_signal)
        soc_after_pending, pflow = one_interval(*pending, soc_midnight)
        if prior_flow is None:
            prior_flow = pflow.copy()
        soc_end, flow143 = execute_feedback(grid[:143], net[day, :143], soc_after_pending)
        pending = (grid[143], net[day, 143])
        traces.append([flow143, None])
        if len(traces) > 1:
            traces[-2][1] = pflow
        rows.append([prices[day] @ grid, np.nan, np.nan, np.nan, soc_midnight, soc_end])
        grids.append(grid)
        soc_midnight = soc_end
        if (day - START_DAY + 1) % 50 == 0:
            print(f"{name}: {day-START_DAY+1}/334 days", flush=True)
    _, lastflow = one_interval(*pending, soc_midnight)
    traces[-1][1] = lastflow
    traces = np.asarray([np.vstack(x) for x in traces])
    rows = np.asarray(rows, float)
    grids = np.asarray(grids)
    for i, day in enumerate(range(START_DAY, 365)):
        emergency_cost = float((5 * prices[day]) @ traces[i, :, 4])
        rows[i, 1:4] = emergency_cost, rows[i, 0] + emergency_cost, traces[i, :, 4].sum()
    return rows, grids, traces, prior_flow, time.perf_counter() - tic


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dates, load, pv, _ = read_inputs(ROOT)
    net = load - pv
    prices = read_prices()
    forecasts, model_diagnostics = generate_price_forecasts(prices, dates)

    forecast_rows = []
    for name, pred in forecasts.items():
        error = pred[START_DAY:] - prices[START_DAY:]
        # Spearman-like rank agreement computed as Pearson correlation of ranks.
        rank_corr = []
        for actual, estimate in zip(prices[START_DAY:], pred[START_DAY:]):
            ar = pd.Series(actual).rank().to_numpy()
            er = pd.Series(estimate).rank().to_numpy()
            rank_corr.append(np.corrcoef(ar, er)[0, 1])
        forecast_rows.append({
            "model": name,
            "mae_yuan_per_kwh": float(np.abs(error).mean()),
            "rmse_yuan_per_kwh": float(np.sqrt(np.mean(error**2))),
            "daily_rank_correlation": float(np.nanmean(rank_corr)),
        })
    forecast_table = pd.DataFrame(forecast_rows).sort_values("mae_yuan_per_kwh")
    forecast_table.to_csv(OUT / "price_forecast_comparison.csv", index=False)
    (OUT / "model_diagnostics.json").write_text(
        json.dumps(model_diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(forecast_table.to_string(index=False), flush=True)

    policy_rows = []
    for name in list(forecasts) + ["perfect_price_oracle"]:
        rows, grids, traces, prior_flow, seconds = run_policy(
            name, forecasts.get(name, forecasts["seasonal_naive_7d"]), prices,
            dates, load, pv, net, oracle=name == "perfect_price_oracle",
        )
        balance = grids + traces[:, :, 3] + traces[:, :, 4] - net[START_DAY:] * DT_HOURS \
            - traces[:, :, 2] - traces[:, :, 5]
        record = {
            "model": name,
            "planned_yuan": float(rows[:, 0].sum()),
            "emergency_yuan": float(rows[:, 1].sum()),
            "total_yuan": float(rows[:, 2].sum()),
            "emergency_kwh": float(rows[:, 3].sum()),
            "seconds": seconds,
            "max_balance_error_kwh": float(np.abs(balance).max()),
            "min_soc_kwh": float(traces[:, :, 1].min()),
            "max_soc_kwh": float(traces[:, :, 1].max()),
            "simultaneous_charge_discharge": int(np.sum(
                (traces[:, :, 2] > 1e-7) & (traces[:, :, 3] > 1e-7)
            )),
        }
        policy_rows.append(record)
        np.savez_compressed(OUT / f"policy_{name}.npz", rows=rows, grid=grids,
                            trace=traces, dates=np.asarray(dates[START_DAY:].astype(str)))
        print(json.dumps(record, ensure_ascii=False), flush=True)
    policy_table = pd.DataFrame(policy_rows).sort_values("total_yuan")
    policy_table.to_csv(OUT / "policy_cost_comparison.csv", index=False)
    feasible = policy_table[policy_table.model != "perfect_price_oracle"].iloc[0]
    oracle = policy_table[policy_table.model == "perfect_price_oracle"].iloc[0]
    conclusion = {
        "selected_model": feasible.model,
        "selection_rule": "lowest realized Q4-2 total cost among causal price models",
        "selected_total_yuan": float(feasible.total_yuan),
        "oracle_total_yuan": float(oracle.total_yuan),
        "price_information_regret_yuan": float(feasible.total_yuan - oracle.total_yuan),
        "evaluation_dates": [str(dates[START_DAY].date()), str(dates[-1].date())],
        "warning": "Model selection uses the supplied evaluation year and is not an independent holdout claim.",
    }
    (OUT / "conclusion.json").write_text(
        json.dumps(conclusion, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(policy_table.to_string(index=False), flush=True)
    print(json.dumps(conclusion, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
