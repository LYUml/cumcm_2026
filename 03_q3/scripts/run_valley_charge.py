"""True-valley charging on top of v002.

Window is 22:00 through next-day 06:00 (not 18:00–24:00). Planned extra
charging in 18:00–22:00 (peak) is forbidden. A SOC target may sit at 06:00
and/or midnight. Everything else stays at v002. Local only; do not push.
"""
from __future__ import annotations

import json
import sys
import time
from itertools import product
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
Q3_DIR = HERE.parent
sys.path.insert(0, str(HERE))
import run_corrected as rc  # noqa: E402
import run_free_battery as fb  # noqa: E402

OUT = Q3_DIR / "outputs" / "valley_charge"
OUT.mkdir(parents=True, exist_ok=True)

V002_COST = 13_521_409.707452236
TV = float(rc.PRICE[:36].mean())
Q0 = fb.Q0
Q_ADJ = fb.Q_ADJ
MORNING_START = rc.ISSUE_STARTS[6]
NOON = rc.ISSUE_STARTS[12]
SOC6_INDEX = MORNING_START - 1  # SOC at civil 6:00
SHORTFALL_PENALTY = 1.0
SLOT_HOUR = np.floor(rc.SLOT_END_HOURS - 1e-9).astype(int)
VALLEY = (SLOT_HOUR < 6) | (SLOT_HOUR >= 22)
PEAK_EVENING = (SLOT_HOUR >= 18) & (SLOT_HOUR < 22)
N_VALLEY = int(VALLEY.sum())


def valley_charge_mask(n_cheapest: int, remaining_start: int) -> np.ndarray:
    """Allow daytime + valley; forbid 18:00–22:00; optionally keep only N cheapest remaining valley slots."""
    mask = np.ones(rc.INTERVALS_PER_DAY, dtype=bool)
    mask[PEAK_EVENING] = False
    remaining_valley = np.flatnonzero(VALLEY & (np.arange(rc.INTERVALS_PER_DAY) >= remaining_start))
    n = min(int(n_cheapest), remaining_valley.size)
    if 0 < n < remaining_valley.size:
        order = remaining_valley[np.argsort(rc.PRICE[remaining_valley], kind="stable")]
        keep = set(order[:n].tolist())
        for t in remaining_valley:
            if t not in keep:
                mask[t] = False
    return mask


def same_weekday_days(day: int, weekday: int, k: int = 4) -> np.ndarray:
    past = np.flatnonzero(rc.DAY_OF_WEEK[:day] == weekday)
    if past.size == 0:
        return np.arange(max(0, day - 7), day)
    return past[-k:]


def history_net_mean(day: int, target_day: int) -> np.ndarray:
    hist = same_weekday_days(day, int(rc.DAY_OF_WEEK[target_day]))
    if hist.size == 0:
        return np.zeros(rc.INTERVALS_PER_DAY)
    return rc.NET_KWH[hist].mean(axis=0)


def hybrid_net(day: int, target_day: int, issue_hour: int) -> np.ndarray:
    if target_day >= len(rc.DATES):
        return np.zeros(rc.INTERVALS_PER_DAY)
    load_kw = rc.base_load_forecast(target_day)
    if issue_hour == 0 and target_day == day:
        return rc.FORECASTS_BY_ISSUE[0]["net_kwh"][day].copy()
    if issue_hour == 18 and target_day == day + 1:
        hourly = rc.PV_HOURLY_FORECAST[day, rc.issue_to_position[18]]
        anchor = float(rc.PV_KW[day, rc.ISSUE_STARTS[18]])
        node_hours = np.arange(0, 25, dtype=float)
        node_values = np.concatenate([[anchor], hourly])
        hours_after_18 = 6.0 + rc.SLOT_END_HOURS
        pv_kw = np.clip(np.interp(hours_after_18, node_hours, node_values), 0.0, None)
        return (load_kw - pv_kw) * rc.INTERVAL_HOURS
    hist = same_weekday_days(day, int(rc.DAY_OF_WEEK[target_day]))
    pv_kw = rc.PV_KW[hist].mean(axis=0) if hist.size else np.zeros(rc.INTERVALS_PER_DAY)
    return (load_kw - pv_kw) * rc.INTERVAL_HOURS


def morning_need_kwh(day: int, target_day: int, issue_hour: int, need_kind: str) -> float:
    if target_day >= len(rc.DATES):
        return 0.0
    if need_kind == "hist_morning":
        net = history_net_mean(day, target_day)
    elif need_kind == "hybrid_morning":
        net = hybrid_net(day, target_day, issue_hour)
    elif need_kind == "hist_expensive":
        net = history_net_mean(day, target_day)
        return float(np.maximum(net[rc.PRICE > float(rc.PRICE.mean())], 0.0).sum())
    else:
        raise ValueError(need_kind)
    return float(np.maximum(net[MORNING_START:NOON], 0.0).sum())


def target_from_need(need_kwh: float, cover_ratio: float) -> float:
    extra = cover_ratio * need_kwh / fb.ETA_D
    return float(np.clip(fb.SOC_MIN + extra, fb.SOC_MIN, fb.SOC_MAX))


def solve_or_relax(**kwargs):
    mode = kwargs.get("end_soc_mode", "soft")
    try:
        return fb.solve_horizon(**kwargs)
    except RuntimeError:
        if mode == "ge" and kwargs.get("end_soc_target") is not None:
            kwargs = dict(kwargs)
            kwargs["end_soc_mode"] = "soft"
            return fb.solve_horizon(**kwargs)
        raise


def planned_target(policy: dict, day: int, issue_hour: int) -> tuple[float | None, int | None]:
    """Return (soc_target, local_index_in_remaining_horizon)."""
    mode = policy["target_mode"]
    if mode == "off":
        return None, None
    waypoint = policy["waypoint"]
    start = rc.ISSUE_STARTS[issue_hour]
    if mode == "mask_only":
        return None, None
    if mode == "fixed":
        tgt = float(policy["fixed_kwh"])
    else:
        if waypoint == "six" and issue_hour == 0:
            target_day = day
        else:
            target_day = day + 1
        need = morning_need_kwh(day, target_day, issue_hour, policy["need_kind"])
        tgt = target_from_need(need, float(policy["cover_ratio"]))
    if waypoint == "six" and issue_hour == 0:
        return tgt, SOC6_INDEX - start
    if waypoint == "six" and issue_hour in (6, 12):
        return None, None
    return tgt, None


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
    soc6_target = np.full(n_days, np.nan)
    current_soc = rc.SOC_TARGET_KWH
    n_cheap = int(policy["n_cheapest"])
    use_mask = policy["target_mode"] != "off"

    for day in range(rc.MIN_FORECAST_DAY, n_days):
        soc_open[day] = current_soc
        day_plan = np.zeros(rc.INTERVALS_PER_DAY)
        day_final = np.zeros(rc.INTERVALS_PER_DAY)
        day_ch = np.zeros(rc.INTERVALS_PER_DAY)
        day_dch = np.zeros(rc.INTERVALS_PER_DAY)
        day_em = np.zeros(rc.INTERVALS_PER_DAY)
        day_sp = np.zeros(rc.INTERVALS_PER_DAY)
        day_soc = np.zeros(rc.INTERVALS_PER_DAY)
        t0, idx0 = planned_target(policy, day, 0)
        soc6_target[day] = np.nan if t0 is None else t0
        mask0 = None
        if use_mask:
            mask0 = valley_charge_mask(n_cheap if policy["waypoint"] != "six" else N_VALLEY, 0)

        da = solve_or_relax(
            target=fb.target_net(day, 0, Q0),
            price=rc.PRICE,
            opening_soc=current_soc,
            baseline_purchase=None,
            terminal_value=TV,
            end_soc_target=t0,
            end_soc_mode=policy["enforce"],
            shortfall_penalty=SHORTFALL_PENALTY,
            charge_allowed=mask0,
            soc_target_index=idx0,
        )
        day_plan[:] = da["purchase"]

        for block, issue in enumerate(rc.ISSUE_HOURS):
            start, end = rc.BLOCK_BOUNDS[block], rc.BLOCK_BOUNDS[block + 1]
            sl = slice(start, rc.INTERVALS_PER_DAY)
            tgt, idx = planned_target(policy, day, issue)
            charge_allowed = None
            if use_mask:
                full = valley_charge_mask(n_cheap if issue == 18 else N_VALLEY, start)
                charge_allowed = full[sl]
            if issue == 0:
                planned = da
            else:
                planned = solve_or_relax(
                    target=fb.target_net(day, issue, Q_ADJ[issue]),
                    price=rc.PRICE[sl],
                    opening_soc=current_soc,
                    baseline_purchase=day_plan[sl],
                    terminal_value=TV,
                    end_soc_target=tgt,
                    end_soc_mode=policy["enforce"],
                    shortfall_penalty=SHORTFALL_PENALTY,
                    charge_allowed=charge_allowed,
                    soc_target_index=idx,
                )
            exec_purchase = planned["purchase"][: end - start]
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
        "soc6_target": soc6_target[eval_idx],
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
            "mean_soc6_target": None
            if np.isnan(np.nanmean(soc6_target[eval_idx]))
            else float(np.nanmean(soc6_target[eval_idx])),
        },
    }


def build_jobs() -> list[dict]:
    jobs = [
        {
            "name": "v002_baseline",
            "target_mode": "off",
            "waypoint": "midnight",
            "need_kind": "",
            "cover_ratio": 0.0,
            "fixed_kwh": 0.0,
            "n_cheapest": N_VALLEY,
            "enforce": "soft",
        },
        {
            "name": "mask_only_forbid_18_22",
            "target_mode": "mask_only",
            "waypoint": "midnight",
            "need_kind": "",
            "cover_ratio": 0.0,
            "fixed_kwh": 0.0,
            "n_cheapest": N_VALLEY,
            "enforce": "soft",
        },
    ]
    for waypoint, fixed, n_cheap, enforce in product(
        ("midnight", "six"),
        (3000.0, 4000.0, 5000.0),
        (12, N_VALLEY),
        ("soft", "ge"),
    ):
        jobs.append(
            {
                "name": f"{waypoint}_fixed{int(fixed)}_n{n_cheap}_{enforce}",
                "target_mode": "fixed",
                "waypoint": waypoint,
                "need_kind": "",
                "cover_ratio": 0.0,
                "fixed_kwh": fixed,
                "n_cheapest": n_cheap,
                "enforce": enforce,
            }
        )
    for waypoint, need_kind, cover, n_cheap, enforce in product(
        ("midnight", "six"),
        ("hist_morning", "hybrid_morning"),
        (0.3, 0.5, 0.8),
        (12, N_VALLEY),
        ("soft", "ge"),
    ):
        jobs.append(
            {
                "name": f"{waypoint}_{need_kind}_c{cover}_n{n_cheap}_{enforce}",
                "target_mode": "forecast",
                "waypoint": waypoint,
                "need_kind": need_kind,
                "cover_ratio": cover,
                "fixed_kwh": 0.0,
                "n_cheapest": n_cheap,
                "enforce": enforce,
            }
        )
    return jobs


def main() -> None:
    jobs = build_jobs()
    print(f"True-valley grid: {len(jobs)} combinations; valley slots={N_VALLEY}; tv={TV:.4f}")
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
        rows.append(row)
        print(
            f"[{i}/{len(jobs)}] {policy['name']:48s}  "
            f"cost={m['total_cost']:,.2f}  d={row['delta_vs_v002']:+,.0f}  "
            f"SOCopen={m['mean_soc_open']:.0f}  ({time.perf_counter() - t_job:.1f}s)"
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
        "target_mode",
        "waypoint",
        "need_kind",
        "cover_ratio",
        "fixed_kwh",
        "n_cheapest",
        "enforce",
        "total_cost",
        "mean_soc_open",
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

    best_clean = {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v) for k, v in best.items()}
    summary = {
        "parent": "v002",
        "v002_cost_yuan": V002_COST,
        "n_policies": len(jobs),
        "elapsed_s": time.perf_counter() - t0,
        "valley_slots": N_VALLEY,
        "terminal_value_kept": TV,
        "window": "22:00 to next-day 06:00; planned charge forbidden 18:00–22:00",
        "best": best_clean,
        "beats_v002": bool(best_clean["total_cost"] < V002_COST - 1e-6),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Elapsed", summary["elapsed_s"], "s")
    print("Best vs v002", best_clean["delta_vs_v002"])


if __name__ == "__main__":
    main()
