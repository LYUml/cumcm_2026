"""Price-aware battery recourse on top of v002.

Purchase planning stays v002 (rest-of-day LP, terminal value = night mean).
After a block's purchase is locked, surplus still charges then spills.
Shortage no longer always dumps the battery: cheap slots can hold SOC for
later, more expensive locked slots (or take 5× emergency now).

Local only; do not push.
"""
from __future__ import annotations

import json
import sys
import time
from itertools import product
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
Q3_DIR = HERE.parent
sys.path.insert(0, str(HERE))
import run_corrected as rc  # noqa: E402
import run_free_battery as fb  # noqa: E402

OUT = Q3_DIR / "outputs" / "price_greedy"
OUT.mkdir(parents=True, exist_ok=True)

V002_COST = 13_521_409.707452236
TV = float(rc.PRICE[:36].mean())
Q0 = fb.Q0
Q_ADJ = fb.Q_ADJ
MEAN_P = float(rc.PRICE.mean())
SLOT_HOUR = np.floor(rc.SLOT_END_HOURS - 1e-9).astype(int)
VALLEY = (SLOT_HOUR < 6) | (SLOT_HOUR >= 22)


def remaining_slice(local_t: int, block_len: int, rest_len: int, scope: str, look_ahead: int) -> slice:
    """Future indices in the rest-of-day arrays, starting after the current slot."""
    start = local_t + 1
    if scope == "block":
        stop = block_len
    else:
        stop = rest_len
    if look_ahead and look_ahead > 0:
        stop = min(stop, local_t + 1 + int(look_ahead))
    return slice(start, max(start, stop))


def expensive_forecast_need(
    local_t: int,
    p_now: float,
    rest_price: np.ndarray,
    rest_forecast: np.ndarray,
    rest_purchase: np.ndarray,
    block_len: int,
    scope: str,
    look_ahead: int,
    cover_ratio: float,
) -> float:
    sl = remaining_slice(local_t, block_len, len(rest_price), scope, look_ahead)
    if sl.start >= sl.stop:
        return 0.0
    short = np.maximum(rest_forecast[sl] - rest_purchase[sl], 0.0)
    expensive = rest_price[sl] > p_now + 1e-9
    return float(short[expensive].sum() * cover_ratio / fb.ETA_D)


def discharge_floor(
    soc_now: float,
    local_t: int,
    p_now: float,
    rest_price: np.ndarray,
    rest_forecast: np.ndarray,
    rest_purchase: np.ndarray,
    block_len: int,
    policy: dict,
) -> float:
    """Lowest SOC allowed after this slot's discharge. soc_now → no discharge."""
    mode = policy["mode"]
    if mode == "always":
        return fb.SOC_MIN

    scope = policy["scope"]
    look_ahead = int(policy["look_ahead"])
    sl = remaining_slice(local_t, block_len, len(rest_price), scope, look_ahead)
    rem_max = float(rest_price[sl].max()) if sl.start < sl.stop else p_now
    need = expensive_forecast_need(
        local_t,
        p_now,
        rest_price,
        rest_forecast,
        rest_purchase,
        block_len,
        scope,
        look_ahead,
        1.0,
    )
    need_ok = (not policy["need_gate"]) or need > 1e-6

    if mode == "hold_vs_remaining":
        if need_ok and p_now + 1e-12 < float(policy["ratio"]) * rem_max:
            return soc_now
        return fb.SOC_MIN

    if mode == "hold_below":
        if p_now < float(policy["price_cut"]):
            return soc_now
        return fb.SOC_MIN

    if mode == "hold_valley":
        t_global = int(policy["_start"]) + local_t
        if VALLEY[t_global]:
            return soc_now
        return fb.SOC_MIN

    if mode == "reserve_valley":
        t_global = int(policy["_start"]) + local_t
        if VALLEY[t_global]:
            return min(fb.SOC_MAX, fb.SOC_MIN + float(policy["reserve_kwh"]))
        return fb.SOC_MIN

    if mode == "reserve_below_mean":
        if p_now < MEAN_P:
            return min(fb.SOC_MAX, fb.SOC_MIN + float(policy["reserve_kwh"]))
        return fb.SOC_MIN

    if mode == "forecast_floor":
        stored = expensive_forecast_need(
            local_t,
            p_now,
            rest_price,
            rest_forecast,
            rest_purchase,
            block_len,
            scope,
            look_ahead,
            float(policy["cover_ratio"]),
        )
        return float(np.clip(fb.SOC_MIN + stored, fb.SOC_MIN, fb.SOC_MAX))

    raise ValueError(mode)


def price_greedy_recourse(
    purchase: np.ndarray,
    actual_net: np.ndarray,
    opening_soc: float,
    rest_price: np.ndarray,
    rest_forecast: np.ndarray,
    rest_purchase: np.ndarray,
    policy: dict,
) -> dict[str, np.ndarray | float]:
    n = len(purchase)
    charge = np.zeros(n)
    discharge = np.zeros(n)
    emergency = np.zeros(n)
    spill = np.zeros(n)
    soc = np.zeros(n)
    soc_now = float(opening_soc)
    held = np.zeros(n)
    for t in range(n):
        residual = float(actual_net[t] - purchase[t])
        if residual >= 0.0:
            floor = discharge_floor(
                soc_now,
                t,
                float(rest_price[t]),
                rest_price,
                rest_forecast,
                rest_purchase,
                n,
                policy,
            )
            floor = min(soc_now, max(fb.SOC_MIN, floor))
            max_ac = min(fb.PMAX, max(0.0, (soc_now - floor) * fb.ETA_D))
            discharge[t] = min(residual, max_ac)
            emergency[t] = residual - discharge[t]
            if residual > 1e-9 and discharge[t] + 1e-9 < residual and floor > fb.SOC_MIN + 1e-9:
                held[t] = residual - discharge[t]
        else:
            surplus = -residual
            max_ch = min(fb.PMAX, max(0.0, (fb.SOC_MAX - soc_now) / fb.ETA_C))
            charge[t] = min(surplus, max_ch)
            spill[t] = surplus - charge[t]
        soc_now = soc_now + fb.ETA_C * charge[t] - discharge[t] / fb.ETA_D
        soc_now = min(fb.SOC_MAX, max(fb.SOC_MIN, soc_now))
        soc[t] = soc_now
    return {
        "charge": charge,
        "discharge": discharge,
        "emergency": emergency,
        "spill": spill,
        "soc": soc,
        "soc_close": soc_now,
        "held_kwh": float(held.sum()),
    }


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
    held = np.zeros(n_days)
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
        day_held = 0.0

        da = fb.solve_horizon(
            fb.target_net(day, 0, Q0),
            rc.PRICE,
            current_soc,
            baseline_purchase=None,
            terminal_value=TV,
        )
        day_plan[:] = da["purchase"]

        for block, issue in enumerate(rc.ISSUE_HOURS):
            start, end = rc.BLOCK_BOUNDS[block], rc.BLOCK_BOUNDS[block + 1]
            sl = slice(start, rc.INTERVALS_PER_DAY)
            if issue == 0:
                planned = da
                rest_forecast = fb.target_net(day, 0, Q0)
            else:
                rest_forecast = fb.target_net(day, issue, Q_ADJ[issue])
                planned = fb.solve_horizon(
                    rest_forecast,
                    rc.PRICE[sl],
                    current_soc,
                    baseline_purchase=day_plan[sl],
                    terminal_value=TV,
                )
            exec_purchase = planned["purchase"][: end - start]
            rest_purchase = planned["purchase"]
            rest_price = rc.PRICE[sl]
            local = dict(policy)
            local["_start"] = start
            rec = price_greedy_recourse(
                exec_purchase,
                rc.NET_KWH[day, start:end],
                current_soc,
                rest_price,
                rest_forecast,
                rest_purchase,
                local,
            )
            day_final[start:end] = exec_purchase
            day_ch[start:end] = rec["charge"]
            day_dch[start:end] = rec["discharge"]
            day_em[start:end] = rec["emergency"]
            day_sp[start:end] = rec["spill"]
            day_soc[start:end] = rec["soc"]
            day_held += float(rec["held_kwh"])
            current_soc = float(rec["soc_close"])

        plan[day] = day_plan
        final[day] = day_final
        charge[day] = day_ch
        discharge[day] = day_dch
        soc[day] = day_soc
        emergency[day] = day_em
        spill[day] = day_sp
        held[day] = day_held

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
            "held_kwh": float(held[eval_idx].sum()),
        },
    }


def blank(**overrides) -> dict:
    row = {
        "mode": "always",
        "scope": "block",
        "ratio": 1.0,
        "price_cut": 0.0,
        "reserve_kwh": 0.0,
        "cover_ratio": 0.0,
        "look_ahead": 0,
        "need_gate": False,
    }
    row.update(overrides)
    return row


def build_jobs() -> list[dict]:
    jobs = [blank(name="v002_baseline", mode="always")]
    for scope, ratio, need_gate in product(("block", "day"), (0.5, 0.75, 1.0), (False, True)):
        tag = f"hold_vs_{scope}_r{ratio:g}"
        if need_gate:
            tag += "_need"
        jobs.append(
            blank(
                name=tag,
                mode="hold_vs_remaining",
                scope=scope,
                ratio=ratio,
                need_gate=need_gate,
            )
        )
    for cut in (0.45, 0.55, 0.80, 1.00, 1.20):
        jobs.append(blank(name=f"hold_below_{cut:.2f}", mode="hold_below", price_cut=cut))
    jobs.append(blank(name="hold_valley_hours", mode="hold_valley"))
    for reserve in (800.0, 1600.0, 3200.0):
        jobs.append(
            blank(
                name=f"reserve_valley_{int(reserve)}",
                mode="reserve_valley",
                reserve_kwh=reserve,
            )
        )
        jobs.append(
            blank(
                name=f"reserve_below_mean_{int(reserve)}",
                mode="reserve_below_mean",
                reserve_kwh=reserve,
            )
        )
    for scope, cover in product(("block", "day"), (0.5, 1.0, 1.5)):
        jobs.append(
            blank(
                name=f"forecast_floor_{scope}_c{cover:g}",
                mode="forecast_floor",
                scope=scope,
                cover_ratio=cover,
            )
        )
    for ahead, ratio in product((12, 36), (0.75, 1.0)):
        jobs.append(
            blank(
                name=f"hold_ahead_{ahead}_r{ratio:g}",
                mode="hold_vs_remaining",
                scope="day",
                ratio=ratio,
                look_ahead=ahead,
            )
        )
    return jobs


def main() -> None:
    jobs = build_jobs()
    print(f"Price-greedy grid: {len(jobs)} combinations; tv={TV:.4f}; mean_p={MEAN_P:.4f}")
    print(f"v002 champion {V002_COST:,.2f}")
    rows = []
    best = None
    best_result = None
    t0 = time.perf_counter()
    for i, policy in enumerate(jobs, start=1):
        t_job = time.perf_counter()
        result = simulate_policy(policy)
        m = result["metrics"]
        row = {**policy, **m, "delta_vs_v002": m["total_cost"] - V002_COST}
        row.pop("_start", None)
        rows.append(row)
        print(
            f"[{i}/{len(jobs)}] {policy['name']:40s}  "
            f"cost={m['total_cost']:,.2f}  d={row['delta_vs_v002']:+,.0f}  "
            f"emerg={m['emergency_kwh']:,.0f}  held={m['held_kwh']:,.0f}  "
            f"({time.perf_counter() - t_job:.1f}s)"
        )
        if best is None or m["total_cost"] < best["total_cost"]:
            best = row
            best_result = result
        pd.DataFrame(rows).sort_values("total_cost").to_csv(
            OUT / "policy_grid.csv", index=False, encoding="utf-8-sig"
        )

    table = pd.DataFrame(rows).sort_values("total_cost")
    table.to_csv(OUT / "policy_grid.csv", index=False, encoding="utf-8-sig")
    print("\n===== BEST =====")
    show = [
        "name",
        "mode",
        "scope",
        "ratio",
        "price_cut",
        "reserve_kwh",
        "cover_ratio",
        "look_ahead",
        "need_gate",
        "total_cost",
        "emergency_kwh",
        "held_kwh",
        "delta_vs_v002",
    ]
    print(table[show].head(12).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
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
            "charge_kwh": best_result["charge"].sum(axis=1),
            "discharge_kwh": best_result["discharge"].sum(axis=1),
        }
    )
    daily.to_csv(OUT / "daily_eval.csv", index=False, encoding="utf-8-sig")

    best_clean = {
        k: (float(v) if isinstance(v, (np.floating, np.integer)) else bool(v) if isinstance(v, (np.bool_, bool)) else v)
        for k, v in best.items()
        if k != "_start"
    }
    summary = {
        "parent": "v002",
        "v002_cost_yuan": V002_COST,
        "n_policies": len(jobs),
        "elapsed_s": time.perf_counter() - t0,
        "terminal_value_kept": TV,
        "best": best_clean,
        "beats_v002": bool(best_clean["total_cost"] < V002_COST - 1e-6),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Elapsed", summary["elapsed_s"], "s")
    print("Best vs v002", best_clean["delta_vs_v002"])


if __name__ == "__main__":
    main()
