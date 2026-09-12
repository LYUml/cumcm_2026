"""Four independent residual quantiles: 00:00, 06:00, 12:00, 18:00.

Grid 50%–95% in 5% steps (10^4 = 10,000 combinations). Day-ahead and the
three 6-hour blocks are solved once per needed (q0, q_issue) pair, then
stitched, because block-end SOC is pinned to the 00:00 plan.

Do not git push.
"""
from __future__ import annotations

import json
import sys
import time
from itertools import combinations, product
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_corrected as rc  # noqa: E402

OUTPUT_DIR = HERE / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

QUANTILES = [round(0.50 + 0.05 * i, 2) for i in range(10)]
N_Q = len(QUANTILES)
N_DAYS = len(rc.EVAL_DAYS)
N_T = rc.INTERVALS_PER_DAY
ADJ_HOURS = (6, 12, 18)
UPDATE_SUBSETS = [
    subset
    for size in range(4)
    for subset in combinations(ADJ_HOURS, size)
]
CHAMPION_YUAN = 14_669_597.26287158


def q_index(value: float) -> int:
    return QUANTILES.index(round(float(value), 2))


def subset_label(subset: tuple[int, ...]) -> str:
    if not subset:
        return "00:00 only"
    return " + ".join(f"{hour:02d}:00" for hour in subset)


def cache_day_ahead() -> dict[str, np.ndarray]:
    purchase = np.zeros((N_Q, N_DAYS, N_T))
    charge = np.zeros((N_Q, N_DAYS, N_T))
    discharge = np.zeros((N_Q, N_DAYS, N_T))
    open_soc = np.zeros((N_Q, N_DAYS, 4))
    pin_soc = np.zeros((N_Q, N_DAYS, 4))
    t0 = time.perf_counter()
    for iq, q0 in enumerate(QUANTILES):
        for iday, day in enumerate(rc.EVAL_DAYS):
            day = int(day)
            solution = rc.solve_initial_schedule(
                rc.corrected_net_forecast(day, 0, q0),
                rc.PRICE,
                rc.SOC_TARGET_KWH,
                rc.SOC_TARGET_KWH,
            )
            purchase[iq, iday] = solution["purchase"]
            charge[iq, iday] = solution["charge"]
            discharge[iq, iday] = solution["discharge"]
            for block in range(4):
                start, end = rc.BLOCK_BOUNDS[block], rc.BLOCK_BOUNDS[block + 1]
                pin_soc[iq, iday, block] = float(solution["soc"][end - 1])
                open_soc[iq, iday, block] = (
                    rc.SOC_TARGET_KWH if start == 0 else float(solution["soc"][start - 1])
                )
        print(f"  day-ahead q={q0:.2f}  ({iq + 1}/{N_Q})  {time.perf_counter() - t0:.1f}s")
    return {
        "purchase": purchase,
        "charge": charge,
        "discharge": discharge,
        "open_soc": open_soc,
        "pin_soc": pin_soc,
    }


def cache_adjustment(issue_hour: int, day_ahead: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    block = rc.ISSUE_HOURS.index(issue_hour)
    start, end = rc.BLOCK_BOUNDS[block], rc.BLOCK_BOUNDS[block + 1]
    length = end - start
    purchase = np.zeros((N_Q, N_Q, N_DAYS, length))
    charge = np.zeros((N_Q, N_Q, N_DAYS, length))
    discharge = np.zeros((N_Q, N_Q, N_DAYS, length))
    t0 = time.perf_counter()
    jobs = N_Q * N_Q
    done = 0
    for iq0, q0 in enumerate(QUANTILES):
        for iq_adj, q_adj in enumerate(QUANTILES):
            for iday, day in enumerate(rc.EVAL_DAYS):
                day = int(day)
                target = rc.corrected_net_forecast(day, issue_hour, q_adj)[:length]
                solution = rc.solve_adjusted_schedule(
                    target,
                    day_ahead["purchase"][iq0, iday, start:end],
                    rc.PRICE[start:end],
                    float(day_ahead["open_soc"][iq0, iday, block]),
                    float(day_ahead["pin_soc"][iq0, iday, block]),
                )
                purchase[iq0, iq_adj, iday] = solution["purchase"][:length]
                charge[iq0, iq_adj, iday] = solution["charge"][:length]
                discharge[iq0, iq_adj, iday] = solution["discharge"][:length]
            done += 1
            if done % 10 == 0 or done == jobs:
                print(
                    f"  {issue_hour:02d}:00  {done}/{jobs} "
                    f"last q0={q0:.2f} q={q_adj:.2f}  {time.perf_counter() - t0:.1f}s"
                )
    return {"purchase": purchase, "charge": charge, "discharge": discharge}


def settle_combo(
    day_ahead: dict[str, np.ndarray],
    adj_cache: dict[int, dict[str, np.ndarray]],
    iq0: int,
    iq_by_hour: dict[int, int],
    subset: tuple[int, ...],
) -> dict[str, float]:
    purchase = day_ahead["purchase"][iq0].copy()
    charge = day_ahead["charge"][iq0].copy()
    discharge = day_ahead["discharge"][iq0].copy()
    for hour in subset:
        block = rc.ISSUE_HOURS.index(hour)
        start, end = rc.BLOCK_BOUNDS[block], rc.BLOCK_BOUNDS[block + 1]
        iq_adj = iq_by_hour[hour]
        purchase[:, start:end] = adj_cache[hour]["purchase"][iq0, iq_adj]
        charge[:, start:end] = adj_cache[hour]["charge"][iq0, iq_adj]
        discharge[:, start:end] = adj_cache[hour]["discharge"][iq0, iq_adj]
    plan = day_ahead["purchase"][iq0]
    actual = rc.NET_KWH[rc.EVAL_DAYS]
    shortage = actual - (purchase + discharge - charge)
    emergency = np.maximum(shortage, 0.0)
    spill = np.maximum(-shortage, 0.0)
    upward = np.maximum(purchase - plan, 0.0)
    downward = np.maximum(plan - purchase, 0.0)
    price = rc.PRICE[None, :]
    plan_cost = float((price * plan).sum())
    adjustment_cost = float((price * (1.5 * upward - 0.5 * downward)).sum())
    emergency_cost = float((rc.EMERGENCY_MULTIPLIER * price * emergency).sum())
    return {
        "total_cost": plan_cost + adjustment_cost + emergency_cost,
        "plan_cost": plan_cost,
        "adjustment_cost": adjustment_cost,
        "emergency_cost": emergency_cost,
        "plan_kwh": float(plan.sum()),
        "final_kwh": float(purchase.sum()),
        "upward_kwh": float(upward.sum()),
        "downward_kwh": float(downward.sum()),
        "emergency_kwh": float(emergency.sum()),
        "spill_kwh": float(spill.sum()),
    }


def main() -> None:
    print("Quantile grid:", QUANTILES)
    print(f"Combinations: {N_Q ** 4}  (four independent issue times)")
    print("Caching 00:00 plans...")
    t_all = time.perf_counter()
    day_ahead = cache_day_ahead()
    adj_cache = {}
    for hour in ADJ_HOURS:
        print(f"Caching {hour:02d}:00 adjustments...")
        adj_cache[hour] = cache_adjustment(hour, day_ahead)

    print("Stitching all combinations...")
    t_st = time.perf_counter()
    rows = []
    best_all3 = None
    best_any = None
    for iq0, iq6, iq12, iq18 in product(range(N_Q), repeat=4):
        iq_by_hour = {6: iq6, 12: iq12, 18: iq18}
        for subset in UPDATE_SUBSETS:
            metrics = settle_combo(day_ahead, adj_cache, iq0, iq_by_hour, subset)
            row = {
                "q00": QUANTILES[iq0],
                "q06": QUANTILES[iq6],
                "q12": QUANTILES[iq12],
                "q18": QUANTILES[iq18],
                "updates": subset_label(subset),
                **metrics,
                "delta_vs_v000": metrics["total_cost"] - CHAMPION_YUAN,
            }
            rows.append(row)
            if best_any is None or metrics["total_cost"] < best_any["total_cost"]:
                best_any = row
            if subset == (6, 12, 18) and (
                best_all3 is None or metrics["total_cost"] < best_all3["total_cost"]
            ):
                best_all3 = row
    print(f"Stitch done in {time.perf_counter() - t_st:.1f}s")

    table = pd.DataFrame(rows)
    # Full 80k-row table is large; keep ranked 6+12+18 plus overall top.
    all3 = table[table["updates"] == "06:00 + 12:00 + 18:00"].sort_values("total_cost")
    top_any = table.sort_values("total_cost").head(50)
    all3.head(50).to_csv(OUTPUT_DIR / "four_quantile_top50_all_updates.csv", index=False)
    top_any.to_csv(OUTPUT_DIR / "four_quantile_top50_any_subset.csv", index=False)
    all3.to_csv(OUTPUT_DIR / "four_quantile_all_updates.csv", index=False)

    best_path = OUTPUT_DIR / "four_quantile_best.json"
    payload = {
        "grid": QUANTILES,
        "n_combinations_quantiles": N_Q ** 4,
        "n_rows_with_subsets": len(table),
        "elapsed_s": time.perf_counter() - t_all,
        "v000_champion_yuan": CHAMPION_YUAN,
        "best_all_three_updates": best_all3,
        "best_any_subset": best_any,
        "best_6_plus_12": table[table["updates"] == "06:00 + 12:00"]
        .sort_values("total_cost")
        .iloc[0]
        .to_dict(),
        "v000_point_in_grid": table[
            (table["q00"] == 0.80)
            & (table["q06"] == 0.70)
            & (table["q12"] == 0.70)
            & (table["updates"] == "06:00 + 12:00")
        ]
        .sort_values("total_cost")
        .iloc[0]
        .to_dict()
        if ((table["q00"] == 0.80) & (table["q06"] == 0.70) & (table["q12"] == 0.70)).any()
        else None,
    }
    best_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== BEST using 6+12+18 (all four buffers act) =====")
    print(json.dumps(best_all3, ensure_ascii=False, indent=2, default=float))
    print("\n===== BEST any update subset =====")
    print(json.dumps(best_any, ensure_ascii=False, indent=2, default=float))
    print("\n===== BEST 6+12 only =====")
    print(json.dumps(payload["best_6_plus_12"], ensure_ascii=False, indent=2, default=float))
    print(f"\nElapsed {payload['elapsed_s']:.1f}s  wrote {best_path}")


if __name__ == "__main__":
    main()
