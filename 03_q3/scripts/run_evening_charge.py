"""Evening valley charging on top of v002.

User request: after 18:00 until midnight, pick the cheapest 10-min slots,
use a forecast of tomorrow's use, and charge the battery toward a target
(not necessarily full) so the next day's purchase has more room.

Everything else stays at v002: quantiles, 0/6/12/18 purchase updates,
rest-of-day LP, greedy execution, overnight SOC from 15 Jan, terminal
value = night mean price. Local only; do not push.
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
sys.path.insert(0, str(HERE))
import run_corrected as rc  # noqa: E402
import run_free_battery as fb  # noqa: E402

OUT = HERE / "outputs" / "evening_charge"
OUT.mkdir(parents=True, exist_ok=True)

V002_COST = 13_521_409.707452236
TV = float(rc.PRICE[: rc.ISSUE_STARTS[6]].mean())
Q0 = fb.Q0
Q_ADJ = fb.Q_ADJ
EVENING_START = rc.ISSUE_STARTS[18]
MORNING_START = rc.ISSUE_STARTS[6]
NOON = rc.ISSUE_STARTS[12]
SHORTFALL_PENALTY = 1.0  # 元/kWh below the midnight target (soft mode)


def evening_cheap_mask(n_cheapest: int) -> np.ndarray:
    """True on the N cheapest slots in 18:00–day end (37 slots)."""
    evening = np.arange(EVENING_START, rc.INTERVALS_PER_DAY)
    n = min(int(n_cheapest), evening.size)
    order = np.argsort(rc.PRICE[evening], kind="stable")
    mask = np.ones(rc.INTERVALS_PER_DAY, dtype=bool)
    if n < evening.size:
        mask[:] = True
        mask[EVENING_START:] = False
        mask[evening[order[:n]]] = True
    return mask


def same_weekday_days(day: int, weekday: int, k: int = 4) -> np.ndarray:
    past = np.flatnonzero(rc.DAY_OF_WEEK[:day] == weekday)
    if past.size == 0:
        fallback = np.arange(max(0, day - 7), day)
        return fallback
    return past[-k:]


def history_net_mean(day: int, tomorrow: int) -> np.ndarray:
    hist = same_weekday_days(day, int(rc.DAY_OF_WEEK[tomorrow]))
    if hist.size == 0:
        return np.zeros(rc.INTERVALS_PER_DAY)
    return rc.NET_KWH[hist].mean(axis=0)


def hybrid_tomorrow_net(day: int, tomorrow: int, issue_hour: int) -> np.ndarray:
    """Tomorrow's net: load from same-weekday history; PV from 18:00 24h forecast when available."""
    load_kw = rc.base_load_forecast(tomorrow)
    if issue_hour == 18:
        hourly = rc.PV_HOURLY_FORECAST[day, rc.issue_to_position[18]]
        anchor = float(rc.PV_KW[day, EVENING_START])
        node_hours = np.arange(0, 25, dtype=float)
        node_values = np.concatenate([[anchor], hourly])
        hours_after_18 = 6.0 + rc.SLOT_END_HOURS
        pv_kw = np.clip(np.interp(hours_after_18, node_hours, node_values), 0.0, None)
    else:
        hist = same_weekday_days(day, int(rc.DAY_OF_WEEK[tomorrow]))
        pv_kw = rc.PV_KW[hist].mean(axis=0) if hist.size else np.zeros(rc.INTERVALS_PER_DAY)
    return (load_kw - pv_kw) * rc.INTERVAL_HOURS


def tomorrow_need_kwh(day: int, issue_hour: int, need_kind: str) -> float:
    """Predicted energy tomorrow that overnight storage is meant to cover."""
    tomorrow = day + 1
    if tomorrow >= len(rc.DATES):
        return 0.0
    if need_kind == "hist_morning":
        net = history_net_mean(day, tomorrow)
        window = net[MORNING_START:NOON]
    elif need_kind == "hist_expensive":
        net = history_net_mean(day, tomorrow)
        window = net[rc.PRICE > float(rc.PRICE.mean())]
    elif need_kind == "hybrid_morning":
        net = hybrid_tomorrow_net(day, tomorrow, issue_hour)
        window = net[MORNING_START:NOON]
    else:
        raise ValueError(need_kind)
    return float(np.maximum(window, 0.0).sum())


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


def simulate_policy(policy: dict) -> dict:
    horizon = "rest_of_day"
    recourse = "greedy"
    terminal_value = TV
    n_days = len(rc.DATES)
    plan = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    final = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    charge = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    discharge = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    soc = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    emergency = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    spill = np.zeros((n_days, rc.INTERVALS_PER_DAY))
    soc_open = np.zeros(n_days)
    midnight_target = np.full(n_days, np.nan)
    current_soc = rc.SOC_TARGET_KWH
    n_cheap = int(policy["n_cheapest"])
    cheap_full = evening_cheap_mask(n_cheap)
    apply_18_only = policy["anchor"] == "h18_only"

    def planned_end_target(day: int, issue_hour: int) -> float | None:
        if policy["target_mode"] == "off":
            return None
        if apply_18_only and issue_hour != 18:
            return None
        if policy["target_mode"] == "fixed":
            return float(policy["fixed_kwh"])
        need = tomorrow_need_kwh(day, issue_hour, policy["need_kind"])
        return target_from_need(need, float(policy["cover_ratio"]))

    for day in range(rc.MIN_FORECAST_DAY, n_days):
        soc_open[day] = current_soc
        day_plan = np.zeros(rc.INTERVALS_PER_DAY)
        day_final = np.zeros(rc.INTERVALS_PER_DAY)
        day_ch = np.zeros(rc.INTERVALS_PER_DAY)
        day_dch = np.zeros(rc.INTERVALS_PER_DAY)
        day_em = np.zeros(rc.INTERVALS_PER_DAY)
        day_sp = np.zeros(rc.INTERVALS_PER_DAY)
        day_soc = np.zeros(rc.INTERVALS_PER_DAY)
        t0 = planned_end_target(day, 0)
        midnight_target[day] = np.nan if t0 is None else t0

        da = solve_or_relax(
            target=fb.target_net(day, 0, Q0),
            price=rc.PRICE,
            opening_soc=current_soc,
            baseline_purchase=None,
            terminal_value=terminal_value,
            end_soc_target=t0,
            end_soc_mode=policy["enforce"],
            shortfall_penalty=SHORTFALL_PENALTY,
            charge_allowed=None,
        )
        day_plan[:] = da["purchase"]

        for block, issue in enumerate(rc.ISSUE_HOURS):
            start, end = rc.BLOCK_BOUNDS[block], rc.BLOCK_BOUNDS[block + 1]
            sl = slice(start, rc.INTERVALS_PER_DAY)
            tgt = planned_end_target(day, issue)
            charge_allowed = None
            if issue == 18 and n_cheap < (rc.INTERVALS_PER_DAY - EVENING_START):
                charge_allowed = cheap_full[sl]
            if issue == 0:
                planned = da
            else:
                planned = solve_or_relax(
                    target=fb.target_net(day, issue, Q_ADJ[issue]),
                    price=rc.PRICE[sl],
                    opening_soc=current_soc,
                    baseline_purchase=day_plan[sl],
                    terminal_value=terminal_value,
                    end_soc_target=tgt,
                    end_soc_mode=policy["enforce"],
                    shortfall_penalty=SHORTFALL_PENALTY,
                    charge_allowed=charge_allowed,
                )
            exec_purchase = planned["purchase"][: end - start]
            actual = rc.NET_KWH[day, start:end]
            rec = fb.greedy_recourse(exec_purchase, actual, current_soc)
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
        "midnight_target": midnight_target[eval_idx],
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
            "mean_midnight_target": float(np.nanmean(midnight_target[eval_idx])),
        },
    }


def build_jobs() -> list[dict]:
    jobs = [
        {
            "name": "v002_baseline",
            "target_mode": "off",
            "need_kind": "",
            "cover_ratio": 0.0,
            "fixed_kwh": 0.0,
            "n_cheapest": 37,
            "enforce": "soft",
            "anchor": "h0_and_h18",
        }
    ]
    for fixed, n_cheap, enforce in product(
        (3000.0, 4000.0, 5000.0, 6000.0, 7500.0),
        (12, 24, 37),
        ("soft", "ge"),
    ):
        jobs.append(
            {
                "name": f"fixed_{int(fixed)}_n{n_cheap}_{enforce}",
                "target_mode": "fixed",
                "need_kind": "",
                "cover_ratio": 0.0,
                "fixed_kwh": fixed,
                "n_cheapest": n_cheap,
                "enforce": enforce,
                "anchor": "h0_and_h18",
            }
        )
    for need_kind, cover, n_cheap, enforce in product(
        ("hist_morning", "hist_expensive", "hybrid_morning"),
        (0.3, 0.5, 0.8, 1.0),
        (12, 24, 37),
        ("soft", "ge"),
    ):
        jobs.append(
            {
                "name": f"{need_kind}_c{cover}_n{n_cheap}_{enforce}",
                "target_mode": "forecast",
                "need_kind": need_kind,
                "cover_ratio": cover,
                "fixed_kwh": 0.0,
                "n_cheapest": n_cheap,
                "enforce": enforce,
                "anchor": "h0_and_h18",
            }
        )
    for cover, enforce in product((0.5, 1.0), ("soft", "ge")):
        jobs.append(
            {
                "name": f"h18only_hist_morning_c{cover}_n12_{enforce}",
                "target_mode": "forecast",
                "need_kind": "hist_morning",
                "cover_ratio": cover,
                "fixed_kwh": 0.0,
                "n_cheapest": 12,
                "enforce": enforce,
                "anchor": "h18_only",
            }
        )
    return jobs


def main() -> None:
    jobs = build_jobs()
    print(f"Evening-charge grid: {len(jobs)} combinations")
    print(f"v002 champion {V002_COST:,.2f}; terminal_value kept at {TV:.4f}")
    rows = []
    best = None
    best_result = None
    t0 = time.perf_counter()
    for i, policy in enumerate(jobs, start=1):
        t_job = time.perf_counter()
        result = simulate_policy(policy)
        m = result["metrics"]
        row = {
            **policy,
            **m,
            "delta_vs_v002": m["total_cost"] - V002_COST,
        }
        rows.append(row)
        print(
            f"[{i}/{len(jobs)}] {policy['name']:42s}  "
            f"cost={m['total_cost']:,.2f}  d={row['delta_vs_v002']:+,.0f}  "
            f"SOCopen={m['mean_soc_open']:.0f}  tgt={m['mean_midnight_target']:.0f}  "
            f"({time.perf_counter() - t_job:.1f}s)"
        )
        if best is None or m["total_cost"] < best["total_cost"]:
            best = row
            best_result = result
    table = pd.DataFrame(rows).sort_values("total_cost")
    table.to_csv(OUT / "policy_grid.csv", index=False, encoding="utf-8-sig")
    print("\n===== BEST =====")
    show = [
        "name",
        "target_mode",
        "need_kind",
        "cover_ratio",
        "fixed_kwh",
        "n_cheapest",
        "enforce",
        "anchor",
        "total_cost",
        "mean_soc_open",
        "mean_midnight_target",
        "emergency_kwh",
        "delta_vs_v002",
    ]
    print(table[show].head(12).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    assert best_result is not None
    fb.OUTPUT_DIR = OUT
    fb.write_tables(best_result)
    fb.write_result3(best_result)
    fb.plot_paper_days(best_result)

    dates = rc.REPORT_DAY_INDEX
    daily = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "soc_open_kwh": best_result["soc_open"],
            "soc_close_kwh": best_result["soc_close"],
            "midnight_target_kwh": best_result["midnight_target"],
            "plan_kwh": best_result["plan"].sum(axis=1),
            "final_kwh": best_result["adjusted"].sum(axis=1),
            "emergency_kwh": best_result["emergency"].sum(axis=1),
            "spill_kwh": best_result["spill"].sum(axis=1),
            "charge_kwh": best_result["charge"].sum(axis=1),
            "discharge_kwh": best_result["discharge"].sum(axis=1),
            "total_cost_yuan": best_result["total_cost"],
        }
    )
    daily.to_csv(OUT / "daily_eval.csv", index=False, encoding="utf-8-sig")
    monthly = daily.copy()
    monthly["month"] = pd.to_datetime(monthly["date"]).dt.strftime("%Y-%m")
    monthly.groupby("month", as_index=False)["total_cost_yuan"].sum().to_csv(
        OUT / "monthly_cost.csv", index=False, encoding="utf-8-sig"
    )

    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(11)
    v002_m = pd.read_csv(HERE / "versions" / "v002_free_battery_rest_greedy" / "monthly_cost.csv")
    v002_vals = v002_m.iloc[:, -1].to_numpy(float)
    v003_m = monthly.groupby("month")["total_cost_yuan"].sum().to_numpy(float)
    ax.bar(x - 0.18, v002_vals, width=0.36, label="v002")
    ax.bar(x + 0.18, v003_m, width=0.36, label="evening-charge best")
    ax.set_xticks(x)
    ax.set_xticklabels(
        ["2025-02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
    )
    ax.set_ylabel("yuan")
    ax.set_title("Monthly cost: v002 vs evening-charge best")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "monthly_cost.png", dpi=120)
    plt.close(fig)

    summary = {
        "parent": "v002",
        "v002_cost_yuan": V002_COST,
        "n_policies": len(jobs),
        "elapsed_s": time.perf_counter() - t0,
        "new_parameters": {
            "evening_window": "18:00 to day-end (37 slots; last label is 0:00-0:10 next day)",
            "n_cheapest": "how many lowest-price evening slots may be used to charge toward the target at 18:00",
            "target_mode": "off | fixed | forecast",
            "fixed_kwh": "midnight SOC target when target_mode=fixed",
            "need_kind": "hist_morning | hist_expensive | hybrid_morning: how tomorrow's energy need is guessed",
            "cover_ratio": "what fraction of that need to pre-store in the battery (after 0.9 discharge efficiency)",
            "enforce": "soft = pay 1 yuan/kWh for missing the target; ge = SOC_end >= target (relax to soft if infeasible)",
            "anchor": "h0_and_h18 = put the target in every remaining-horizon LP; h18_only = only at 18:00 (extra buy at 1.5p)",
            "shortfall_penalty": SHORTFALL_PENALTY,
            "terminal_value_kept": TV,
        },
        "best": {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in best.items() if k != "name" or True},
        "beats_v002": bool(best["total_cost"] < V002_COST - 1e-6),
    }
    # json cannot serialize numpy
    best_clean = {}
    for k, v in best.items():
        if isinstance(v, (np.floating, np.integer)):
            best_clean[k] = float(v)
        else:
            best_clean[k] = v
    summary["best"] = best_clean
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Elapsed", summary["elapsed_s"], "s")
    print("Best vs v002", best_clean["delta_vs_v002"])


if __name__ == "__main__":
    main()
