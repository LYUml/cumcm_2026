"""Port Q2's nonanticipative scenario tree onto Q3 v002.

Purchase still commits only at 0/6/12/18 over the rest of the day.
Battery execution stays greedy. The day-ahead / update LP is replaced by
Q2-style residual scenarios with optional nodewise nonanticipativity on
charge/discharge. Local only; do not push.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

HERE = Path(__file__).resolve().parent
Q3_DIR = HERE.parent
sys.path.insert(0, str(HERE))
import run_corrected as rc  # noqa: E402
import run_free_battery as fb  # noqa: E402

OUT = Q3_DIR / "outputs" / "scenario_tree"
OUT.mkdir(parents=True, exist_ok=True)

V002_COST = 13_521_409.707452236
TV = float(rc.PRICE[:36].mean())
Q0 = fb.Q0
Q_ADJ = fb.Q_ADJ
EM = rc.EMERGENCY_MULTIPLIER
TIE = 1e-4


def two_cluster(values: np.ndarray, seed: int = 0) -> np.ndarray:
    """2-means without sklearn; all-equal rows stay in one cluster."""
    x = np.asarray(values, dtype=float)
    n = x.shape[0]
    if n <= 1 or np.allclose(x, x[0]):
        return np.zeros(n, dtype=int)
    rng = np.random.default_rng(seed)
    best_lab = np.zeros(n, dtype=int)
    best_in = np.inf
    for _ in range(8):
        pick = rng.choice(n, size=2, replace=False)
        c0, c1 = x[pick[0]].copy(), x[pick[1]].copy()
        lab = np.zeros(n, dtype=int)
        for _iter in range(25):
            d0 = np.einsum("ij,ij->i", x - c0, x - c0)
            d1 = np.einsum("ij,ij->i", x - c1, x - c1)
            new = (d1 < d0).astype(int)
            if np.array_equal(new, lab):
                break
            lab = new
            if lab.min() == lab.max():
                break
            c0 = x[lab == 0].mean(axis=0)
            c1 = x[lab == 1].mean(axis=0)
        cents = np.where(lab[:, None] == 0, c0, c1)
        inertia = float(np.einsum("ij,ij->", x - cents, x - cents))
        if inertia < best_in:
            best_in = inertia
            best_lab = lab.copy()
    if best_lab.min() == best_lab.max():
        score = x.mean(axis=1)
        best_lab = (score > np.median(score)).astype(int)
        if best_lab.min() == best_lab.max():
            best_lab = np.zeros(n, dtype=int)
    return best_lab


def hierarchical_tree_groups(scenarios: np.ndarray, start_index: int, stage_slots: int) -> np.ndarray:
    """Q2 nested binary tree, stages aligned to the civil-day 10-min index."""
    scenarios = np.asarray(scenarios, float)
    ns, horizon = scenarios.shape
    groups = np.zeros((ns, horizon), dtype=int)
    stage = (start_index + np.arange(horizon)) // int(stage_slots)
    stage_ids = np.unique(stage)
    partitions = [np.arange(ns)]
    next_id = 0
    for i, sid in enumerate(stage_ids):
        local = np.flatnonzero(stage == sid)
        sl = slice(int(local[0]), int(local[-1]) + 1)
        for members in partitions:
            groups[members, sl] = next_id
            next_id += 1
        if i == len(stage_ids) - 1:
            break
        children = []
        for members in partitions:
            if len(members) <= 1:
                children.append(members)
                continue
            labels = two_cluster(scenarios[members, sl], seed=0)
            for lab in (0, 1):
                sub = members[labels == lab]
                if sub.size:
                    children.append(sub)
        partitions = children
    return groups


def path_scenarios(day: int, issue_hour: int, center: np.ndarray, count: int, window: int) -> np.ndarray:
    """Current remaining-horizon forecast + causal historical residual paths."""
    start = rc.ISSUE_STARTS[issue_hour]
    raw = rc.FORECASTS_BY_ISSUE[issue_hour]["net_kwh"]
    lo = max(rc.MIN_FORECAST_DAY, day - int(window))
    candidates = np.arange(lo, day)
    candidates = candidates[np.isfinite(raw[candidates]).all(axis=1)]
    if candidates.size == 0:
        return center[None, :].copy()
    same = candidates[rc.DAY_OF_WEEK[candidates] == rc.DAY_OF_WEEK[day]]
    others = candidates[~np.isin(candidates, same)][::-1]
    chosen = np.concatenate([same[::-1], others])[:count]
    residuals = rc.NET_KWH[chosen, start:] - raw[chosen]
    return center[None, :] + residuals


def solve_scenario_horizon(
    scenarios: np.ndarray,
    price: np.ndarray,
    opening_soc: float,
    baseline_purchase: np.ndarray | None,
    terminal_value: float,
    lam: float,
    node_groups: np.ndarray | None,
    terminal_floor: float | None,
) -> np.ndarray:
    """Here-and-now purchase; scenario battery with optional nonanticipativity."""
    scenarios = np.asarray(scenarios, float)
    price = np.asarray(price, float)
    ns, horizon = scenarios.shape
    if price.shape != (horizon,):
        raise ValueError("price length must match remaining horizon")
    use_base = baseline_purchase is not None
    if use_base:
        g0, u0, v0 = 0, horizon, 2 * horizon
        c0 = 3 * horizon
    else:
        g0 = 0
        c0 = horizon
        u0 = v0 = None
    d0 = c0 + ns * horizon
    s0 = d0 + ns * horizon
    e0 = s0 + ns * horizon
    w0 = e0 + ns * horizon
    n_var = w0 + ns * horizon

    na_pairs = []
    if node_groups is not None:
        node_groups = np.asarray(node_groups)
        for t in range(horizon):
            for group in np.unique(node_groups[:, t]):
                members = np.flatnonzero(node_groups[:, t] == group)
                na_pairs.extend((t, int(members[0]), int(k)) for k in members[1:])

    n_base = horizon if use_base else 0
    n_eq = n_base + 2 * ns * horizon + 2 * len(na_pairs)
    equality = lil_matrix((n_eq, n_var))
    rhs = np.zeros(n_eq)
    row = 0
    if use_base:
        base = np.asarray(baseline_purchase, float)
        for t in range(horizon):
            equality[row, g0 + t] = 1.0
            equality[row, u0 + t] = -1.0
            equality[row, v0 + t] = 1.0
            rhs[row] = base[t]
            row += 1
    for k in range(ns):
        for t in range(horizon):
            equality[row, g0 + t] = 1.0
            equality[row, c0 + k * horizon + t] = -1.0
            equality[row, d0 + k * horizon + t] = 1.0
            equality[row, e0 + k * horizon + t] = 1.0
            equality[row, w0 + k * horizon + t] = -1.0
            rhs[row] = scenarios[k, t]
            row += 1
    for k in range(ns):
        for t in range(horizon):
            equality[row, s0 + k * horizon + t] = 1.0
            equality[row, c0 + k * horizon + t] = -fb.ETA_C
            equality[row, d0 + k * horizon + t] = 1.0 / fb.ETA_D
            if t == 0:
                rhs[row] = opening_soc
            else:
                equality[row, s0 + k * horizon + t - 1] = -1.0
            row += 1
    for t, ref, k in na_pairs:
        equality[row, c0 + k * horizon + t] = 1.0
        equality[row, c0 + ref * horizon + t] = -1.0
        row += 1
        equality[row, d0 + k * horizon + t] = 1.0
        equality[row, d0 + ref * horizon + t] = -1.0
        row += 1

    objective = np.zeros(n_var)
    if use_base:
        objective[u0:v0] = 1.5 * price
        objective[v0:c0] = -0.5 * price
    else:
        objective[g0:c0] = price
    weight = 1.0 / ns
    for k in range(ns):
        objective[c0 + k * horizon : c0 + (k + 1) * horizon] = TIE * weight
        objective[d0 + k * horizon : d0 + (k + 1) * horizon] = TIE * weight
        objective[e0 + k * horizon : e0 + (k + 1) * horizon] = (lam * EM * price) * weight
        objective[w0 + k * horizon : w0 + (k + 1) * horizon] = TIE * weight
        objective[s0 + (k + 1) * horizon - 1] -= terminal_value * weight

    bounds = []
    if use_base:
        bounds.extend([(0.0, None)] * (3 * horizon))
    else:
        bounds.extend([(0.0, None)] * horizon)
    bounds.extend([(0.0, fb.PMAX)] * (ns * horizon))
    bounds.extend([(0.0, fb.PMAX)] * (ns * horizon))
    bounds.extend([(fb.SOC_MIN, fb.SOC_MAX)] * (ns * horizon))
    bounds.extend([(0.0, None)] * (ns * horizon))
    bounds.extend([(0.0, None)] * (ns * horizon))

    a_ub = None
    b_ub = None
    if terminal_floor is not None:
        floor = float(np.clip(terminal_floor, fb.SOC_MIN, fb.SOC_MAX))
        a_ub = np.zeros((ns, n_var))
        b_ub = np.full(ns, -floor)
        for k in range(ns):
            a_ub[k, s0 + (k + 1) * horizon - 1] = -1.0

    solution = linprog(
        objective,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=equality.tocsr(),
        b_eq=rhs,
        bounds=bounds,
        method="highs",
    )
    if not solution.success:
        raise RuntimeError(solution.message)
    return solution.x[g0 : g0 + horizon]


def center_forecast(day: int, issue_hour: int, mode: str) -> np.ndarray:
    if mode == "buffered":
        q = Q0 if issue_hour == 0 else Q_ADJ[issue_hour]
        return fb.target_net(day, issue_hour, q)
    return rc.FORECASTS_BY_ISSUE[issue_hour]["net_kwh"][day].copy()


def plan_remaining(day: int, issue_hour: int, opening_soc: float, baseline, policy: dict) -> np.ndarray:
    start = rc.ISSUE_STARTS[issue_hour]
    price = rc.PRICE[start:]
    center = center_forecast(day, issue_hour, policy["center"])
    scenarios = path_scenarios(day, issue_hour, center, int(policy["n_scenarios"]), int(policy["window"]))
    groups = None
    if policy["tree"] and scenarios.shape[0] > 1:
        groups = hierarchical_tree_groups(scenarios, start, int(policy["stage_slots"]))
    floor = policy["floor"]
    try:
        return solve_scenario_horizon(
            scenarios,
            price,
            opening_soc,
            baseline,
            TV if policy["use_tv"] else 0.0,
            float(policy["lam"]),
            groups,
            None if floor is None else float(floor),
        )
    except RuntimeError:
        point = center if policy["center"] == "raw" else fb.target_net(
            day, issue_hour, Q0 if issue_hour == 0 else Q_ADJ[issue_hour]
        )
        fallback = fb.solve_horizon(
            point,
            price,
            opening_soc,
            baseline_purchase=baseline,
            terminal_value=TV if policy["use_tv"] else 0.0,
        )
        return fallback["purchase"]


def simulate_policy(policy: dict) -> dict:
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
    n_fail = 0

    for day in range(rc.MIN_FORECAST_DAY, n_days):
        soc_open[day] = current_soc
        day_plan = np.zeros(rc.INTERVALS_PER_DAY)
        day_final = np.zeros(rc.INTERVALS_PER_DAY)
        day_ch = np.zeros(rc.INTERVALS_PER_DAY)
        day_dch = np.zeros(rc.INTERVALS_PER_DAY)
        day_em = np.zeros(rc.INTERVALS_PER_DAY)
        day_sp = np.zeros(rc.INTERVALS_PER_DAY)
        day_soc = np.zeros(rc.INTERVALS_PER_DAY)

        remaining = plan_remaining(day, 0, current_soc, None, policy)
        day_plan[:] = remaining

        for block, issue in enumerate(rc.ISSUE_HOURS):
            start, end = rc.BLOCK_BOUNDS[block], rc.BLOCK_BOUNDS[block + 1]
            sl = slice(start, rc.INTERVALS_PER_DAY)
            if issue == 0:
                exec_purchase = remaining[: end - start]
            else:
                remaining = plan_remaining(day, issue, current_soc, day_plan[sl], policy)
                exec_purchase = remaining[: end - start]
            rec = fb.greedy_recourse(exec_purchase, rc.NET_KWH[day, start:end], current_soc)
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
    em_cost = (EM * price * em_e).sum(axis=1)
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
            "n_fail": n_fail,
        },
    }


def blank(**overrides) -> dict:
    row = {
        "n_scenarios": 12,
        "tree": True,
        "stage_slots": 24,
        "lam": 0.9,
        "center": "raw",
        "window": 56,
        "use_tv": True,
        "floor": None,
    }
    row.update(overrides)
    return row


def build_jobs() -> list[dict]:
    return [
        blank(name="v002_point_lp", n_scenarios=0),
        blank(name="q2tree_n12_s24_l0.9_raw"),
        blank(name="q2tree_n12_s24_l0.9_buffered", center="buffered"),
        blank(name="q2tree_n12_s36_l0.9_raw", stage_slots=36),
        blank(name="twostage_n12_l0.9_raw", tree=False),
        blank(name="q2tree_n12_s24_l0.7_raw", lam=0.7),
        blank(name="q2tree_n12_s24_l1.0_raw", lam=1.0),
        blank(name="q2tree_n8_s24_l0.9_raw", n_scenarios=8),
        blank(name="q2tree_n12_s24_l0.9_raw_floor3000", use_tv=False, floor=3000.0),
        blank(name="q2tree_n12_s24_l0.9_raw_win30", window=30),
    ]


def main() -> None:
    jobs = build_jobs()
    print(f"Scenario-tree grid: {len(jobs)} combinations; tv={TV:.4f}", flush=True)
    print(f"v002 champion {V002_COST:,.2f}", flush=True)
    t_probe = time.perf_counter()
    probe = path_scenarios(40, 0, center_forecast(40, 0, "raw"), 12, 56)
    groups = hierarchical_tree_groups(probe, 0, 24)
    solve_scenario_horizon(probe, rc.PRICE, 6000.0, None, TV, 0.9, groups, None)
    print(f"Probe 00:00 n=12 tree LP {time.perf_counter() - t_probe:.2f}s", flush=True)

    rows = []
    best = None
    best_result = None
    t0 = time.perf_counter()
    for i, policy in enumerate(jobs, start=1):
        t_job = time.perf_counter()
        if policy["n_scenarios"] == 0:
            result = fb.simulate_year("rest_of_day", "greedy", TV)
        else:
            result = simulate_policy(policy)
        m = result["metrics"]
        row = {**policy, **m, "delta_vs_v002": m["total_cost"] - V002_COST}
        rows.append(row)
        print(
            f"[{i}/{len(jobs)}] {policy['name']:40s}  "
            f"cost={m['total_cost']:,.2f}  d={row['delta_vs_v002']:+,.0f}  "
            f"emerg={m['emergency_kwh']:,.0f}  SOCopen={m['mean_soc_open']:.0f}  "
            f"({time.perf_counter() - t_job:.1f}s)",
            flush=True,
        )
        if best is None or m["total_cost"] < best["total_cost"]:
            best = row
            best_result = result
        pd.DataFrame(rows).sort_values("total_cost").to_csv(
            OUT / "policy_grid.csv", index=False, encoding="utf-8-sig"
        )

    table = pd.DataFrame(rows).sort_values("total_cost")
    table.to_csv(OUT / "policy_grid.csv", index=False, encoding="utf-8-sig")
    print("\n===== BEST =====", flush=True)
    show = [
        "name",
        "n_scenarios",
        "tree",
        "stage_slots",
        "lam",
        "center",
        "window",
        "use_tv",
        "floor",
        "total_cost",
        "emergency_kwh",
        "mean_soc_open",
        "delta_vs_v002",
    ]
    print(table[show].to_string(index=False, float_format=lambda x: f"{x:,.2f}"), flush=True)
    assert best_result is not None
    fb.OUTPUT_DIR = OUT
    fb.write_tables(best_result)
    fb.write_result3(best_result)
    fb.plot_paper_days(best_result)
    daily = pd.DataFrame(
        {
            "date": rc.REPORT_DAY_INDEX.strftime("%Y-%m-%d"),
            "soc_open_kwh": best_result["soc_open"],
            "soc_close_kwh": best_result["soc_close"],
            "total_cost_yuan": best_result["total_cost"],
            "emergency_kwh": best_result["emergency"].sum(axis=1),
        }
    )
    daily.to_csv(OUT / "daily_eval.csv", index=False, encoding="utf-8-sig")
    best_clean = {
        k: (None if v is None else float(v) if isinstance(v, (np.floating, np.integer)) else bool(v) if isinstance(v, (np.bool_, bool)) else v)
        for k, v in best.items()
    }
    summary = {
        "parent": "v002",
        "v002_cost_yuan": V002_COST,
        "n_policies": len(jobs),
        "elapsed_s": time.perf_counter() - t0,
        "best": best_clean,
        "beats_v002": bool(best_clean["total_cost"] < V002_COST - 1e-6),
        "note": "Q2 tree ported to Q3 receding 0/6/12/18 commits; greedy execution unchanged.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Elapsed", summary["elapsed_s"], "s", flush=True)
    print("Best vs v002", best_clean["delta_vs_v002"], flush=True)


if __name__ == "__main__":
    main()
