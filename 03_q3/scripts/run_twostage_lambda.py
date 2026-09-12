"""Two-stage λ sweep on the v007 scheme.

Everything else frozen: 12 residual paths, raw center, 56-day window,
rest-of-day commits at 0/6/12/18, greedy execution, night-mean terminal
value. Only the planning shortage weight λ changes.

Local only; do not push.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_free_battery as fb  # noqa: E402
import run_scenario_tree as st  # noqa: E402

OUT = HERE.parent / "outputs" / "twostage_lambda"
OUT.mkdir(parents=True, exist_ok=True)

V007_COST = 13_164_261.157320466
V007_LAM = 0.9
COARSE = [0.50, 0.60, 0.70, 0.80, 0.90, 1.00, 1.10, 1.20]


def job_for(lam: float) -> dict:
    return st.blank(
        name=f"twostage_n12_l{lam:.2f}_raw",
        tree=False,
        lam=float(lam),
    )


def run_one(lam: float) -> dict:
    policy = job_for(lam)
    t_job = time.perf_counter()
    result = st.simulate_policy(policy)
    m = result["metrics"]
    row = {
        **policy,
        **m,
        "delta_vs_v007": m["total_cost"] - V007_COST,
        "elapsed_s": time.perf_counter() - t_job,
    }
    return row, result


def extra_lams(done: set[float], best_lam: float) -> list[float]:
    out: list[float] = []
    rounded = [round(x, 2) for x in COARSE]
    if abs(best_lam - min(rounded)) < 1e-9:
        out.extend([0.30, 0.40])
    elif abs(best_lam - max(rounded)) < 1e-9:
        out.extend([1.30, 1.40, 1.50])
    else:
        for step in (0.05, -0.05):
            cand = round(best_lam + step, 2)
            if 0.20 <= cand <= 1.60:
                out.append(cand)
    return [x for x in out if all(abs(x - y) > 1e-9 for y in done)]


def write_grid(rows: list[dict]) -> pd.DataFrame:
    table = pd.DataFrame(rows).sort_values("total_cost")
    table.to_csv(OUT / "policy_grid.csv", index=False, encoding="utf-8-sig")
    return table


def main() -> None:
    print(f"Two-stage λ sweep; parent v007 {V007_COST:,.2f} at λ={V007_LAM}", flush=True)
    print(f"Coarse grid: {COARSE}", flush=True)
    rows: list[dict] = []
    results: dict[float, dict] = {}
    t0 = time.perf_counter()
    queue = list(COARSE)
    seen: set[float] = set()
    refined = False
    i = 0
    while queue:
        lam = queue.pop(0)
        key = round(lam, 2)
        if any(abs(key - s) < 1e-9 for s in seen):
            continue
        seen.add(key)
        i += 1
        row, result = run_one(key)
        rows.append(row)
        results[key] = result
        write_grid(rows)
        print(
            f"[{i}] λ={key:.2f}  cost={row['total_cost']:,.2f}  "
            f"d_v007={row['delta_vs_v007']:+,.0f}  "
            f"emerg={row['emergency_kwh']:,.0f}  "
            f"plan={row['plan_kwh']:,.0f}  "
            f"adj={row['adjustment_cost']:,.0f}  "
            f"({row['elapsed_s']:.1f}s)",
            flush=True,
        )
        if not queue and not refined:
            best_so_far = min(rows, key=lambda r: r["total_cost"])
            more = extra_lams(seen, float(best_so_far["lam"]))
            if more:
                print(f"Refine around λ={best_so_far['lam']:.2f}: {more}", flush=True)
                queue.extend(more)
            refined = True

    table = write_grid(rows)
    best = min(rows, key=lambda r: r["total_cost"])
    best_lam = round(float(best["lam"]), 2)
    best_result = results[best_lam]
    print("\n===== TWO-STAGE λ GRID =====", flush=True)
    show = [
        "name",
        "lam",
        "total_cost",
        "plan_cost",
        "adjustment_cost",
        "emergency_cost",
        "emergency_kwh",
        "mean_soc_open",
        "delta_vs_v007",
    ]
    print(table[show].to_string(index=False, float_format=lambda x: f"{x:,.2f}"), flush=True)

    fb.OUTPUT_DIR = OUT
    fb.write_tables(best_result)
    fb.write_result3(best_result)
    fb.plot_paper_days(best_result)
    daily = pd.DataFrame(
        {
            "date": st.rc.REPORT_DAY_INDEX.strftime("%Y-%m-%d"),
            "soc_open_kwh": best_result["soc_open"],
            "soc_close_kwh": best_result["soc_close"],
            "total_cost_yuan": best_result["total_cost"],
            "emergency_kwh": best_result["emergency"].sum(axis=1),
        }
    )
    daily.to_csv(OUT / "daily_eval.csv", index=False, encoding="utf-8-sig")
    beats = bool(best["total_cost"] < V007_COST - 50.0)
    summary = {
        "parent": "v007",
        "v007_cost_yuan": V007_COST,
        "v007_lam": V007_LAM,
        "n_policies": len(rows),
        "elapsed_s": time.perf_counter() - t0,
        "coarse": COARSE,
        "evaluated": sorted(seen),
        "best_lam": best_lam,
        "best_cost_yuan": float(best["total_cost"]),
        "delta_vs_v007": float(best["delta_vs_v007"]),
        "beats_v007": beats,
        "best": {
            k: (None if v is None else float(v) if isinstance(v, (np.floating, np.integer, float, int)) else bool(v) if isinstance(v, (np.bool_, bool)) else v)
            for k, v in best.items()
        },
        "note": "Two-stage only; λ is the planning shortage weight on 5p. Settlement stays 5p.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Elapsed", summary["elapsed_s"], "s", flush=True)
    print(
        f"Best λ={best_lam:.2f}  cost={best['total_cost']:,.2f}  "
        f"vs v007 {best['delta_vs_v007']:+,.2f}  beats={beats}",
        flush=True,
    )


if __name__ == "__main__":
    main()
