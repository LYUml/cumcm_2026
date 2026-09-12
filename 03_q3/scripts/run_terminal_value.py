"""Dense terminal-value sweep on top of v002.

Planning, greedy execution, buffers stay v002. Only the salvage price on
remaining-horizon end SOC changes. Families:

1. One number for 0/6/12/18 (dense grid + named economic anchors).
2. Local refine around the 1D best.
3. Day-ahead TV vs intraday-update TV (two numbers).
4. 18:00 TV different from 0/6/12 (midnight is only ~6 h away).

Local only; do not push.
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

HERE = Path(__file__).resolve().parent
Q3_DIR = HERE.parent
sys.path.insert(0, str(HERE))
import run_corrected as rc  # noqa: E402
import run_free_battery as fb  # noqa: E402

OUT = Q3_DIR / "outputs" / "terminal_value"
OUT.mkdir(parents=True, exist_ok=True)

V002_COST = 13_521_409.707452236
V002_TV = float(rc.PRICE[:36].mean())
ETA = fb.ETA_C
SLOT_HOUR = np.floor(rc.SLOT_END_HOURS - 1e-9).astype(int)


def unique_sorted(values) -> list[float]:
    return sorted({round(float(v), 6) for v in values})


def named_anchors() -> dict[str, float]:
    night36 = float(rc.PRICE[:36].mean())
    night35 = float(rc.PRICE[: rc.ISSUE_STARTS[6]].mean())
    valley_eve = float(rc.PRICE[SLOT_HOUR >= 22].mean())
    mean_p = float(rc.PRICE.mean())
    peak = float(rc.PRICE.max())
    min_p = float(rc.PRICE.min())
    med = float(np.median(rc.PRICE))
    return {
        "zero": 0.0,
        "min_tariff": min_p,
        "half_night36": 0.5 * night36,
        "eta_night36": ETA * night36,
        "night35": night35,
        "v002_night36": night36,
        "valley_22_24": valley_eve,
        "first_slot": float(rc.PRICE[0]),
        "last_slot": float(rc.PRICE[-1]),
        "median_tariff": med,
        "half_mean": 0.5 * mean_p,
        "eta_mean": ETA * mean_p,
        "mean_tariff": mean_p,
        "half_peak": 0.5 * peak,
        "eta_peak": ETA * peak,
        "roundtrip_peak": ETA * ETA * peak,
        "peak_tariff": peak,
    }


def scalar_grid() -> list[float]:
    anchors = list(named_anchors().values())
    coarse_low = np.arange(0.0, 0.36, 0.05)
    band_a = np.arange(0.36, 0.42, 0.01)
    band_b = np.arange(0.42, 0.505, 0.005)
    band_c = np.arange(0.51, 0.575, 0.01)
    coarse_high = [0.58, 0.60, 0.62, 0.66, 0.70, 0.77, 0.90, 1.00, 1.20, 1.40]
    return unique_sorted(list(anchors) + list(coarse_low) + list(band_a) + list(band_b) + list(band_c) + coarse_high)


def tv_key(tv0: float, tv6: float, tv12: float, tv18: float) -> tuple[float, float, float, float]:
    return (round(tv0, 6), round(tv6, 6), round(tv12, 6), round(tv18, 6))


def run_one(tv0: float, tv6: float, tv12: float, tv18: float) -> dict:
    if tv0 == tv6 == tv12 == tv18:
        return fb.simulate_year("rest_of_day", "greedy", float(tv0))
    return fb.simulate_year(
        "rest_of_day",
        "greedy",
        {0: float(tv0), 6: float(tv6), 12: float(tv12), 18: float(tv18)},
    )


def main() -> None:
    anchors = named_anchors()
    print("Named terminal-value anchors (yuan/kWh):")
    for name, value in anchors.items():
        print(f"  {name:16s} {value:.6f}")
    print(f"v002 champion {V002_COST:,.2f}  tv={V002_TV:.6f}")

    jobs: list[dict] = []
    for tv in scalar_grid():
        label = next((name for name, value in anchors.items() if abs(value - tv) < 1e-9), None)
        name = f"scalar_{tv:.6f}" if label is None else f"anchor_{label}"
        jobs.append(
            {
                "name": name,
                "family": "scalar",
                "tv0": tv,
                "tv6": tv,
                "tv12": tv,
                "tv18": tv,
            }
        )

    cache: dict[tuple[float, float, float, float], dict] = {}
    rows = []
    best = None
    best_result = None
    t0 = time.perf_counter()

    def consume(job: dict, total_hint: str) -> None:
        nonlocal best, best_result
        key = tv_key(job["tv0"], job["tv6"], job["tv12"], job["tv18"])
        t_job = time.perf_counter()
        if key in cache:
            result = cache[key]
            reused = True
        else:
            result = run_one(*key)
            cache[key] = result
            reused = False
        m = result["metrics"]
        row = {
            **job,
            **m,
            "delta_vs_v002": m["total_cost"] - V002_COST,
        }
        rows.append(row)
        tag = "reuse" if reused else f"{time.perf_counter() - t_job:.1f}s"
        print(
            f"[{total_hint}] {job['name']:32s}  "
            f"cost={m['total_cost']:,.2f}  d={row['delta_vs_v002']:+,.0f}  "
            f"SOCopen={m['mean_soc_open']:.0f}  emerg={m['emergency_kwh']:,.0f}  ({tag})"
        )
        if best is None or m["total_cost"] < best["total_cost"] - 1e-8:
            best = row
            best_result = result
        pd.DataFrame(rows).sort_values("total_cost").to_csv(
            OUT / "policy_grid.csv", index=False, encoding="utf-8-sig"
        )

    n_scalar = len(jobs)
    print(f"\nPhase 1: scalar grid, {n_scalar} values")
    for i, job in enumerate(jobs, start=1):
        consume(job, f"{i}/{n_scalar}")

    assert best is not None
    best_tv = float(best["tv0"])
    refine = unique_sorted(np.arange(best_tv - 0.02, best_tv + 0.0200001, 0.002))
    refine = [tv for tv in refine if 0.0 <= tv <= 1.4]
    print(f"\nPhase 2: refine around {best_tv:.6f}, {len(refine)} values")
    for i, tv in enumerate(refine, start=1):
        consume(
            {
                "name": f"refine_{tv:.6f}",
                "family": "refine",
                "tv0": tv,
                "tv6": tv,
                "tv12": tv,
                "tv18": tv,
            },
            f"R{i}/{len(refine)}",
        )

    assert best is not None
    best_tv = float(best["tv0"]) if best["family"] in {"scalar", "refine"} else best_tv
    split_vals = unique_sorted(
        [
            max(0.0, best_tv - 0.03),
            best_tv,
            V002_TV,
            min(1.4, best_tv + 0.03),
            0.50,
        ]
    )
    split_jobs = []
    for tv_da in split_vals:
        for tv_upd in split_vals:
            if abs(tv_da - tv_upd) < 1e-12:
                continue
            split_jobs.append(
                {
                    "name": f"split_da{tv_da:.3f}_upd{tv_upd:.3f}",
                    "family": "split_da_upd",
                    "tv0": tv_da,
                    "tv6": tv_upd,
                    "tv12": tv_upd,
                    "tv18": tv_upd,
                }
            )
    print(f"\nPhase 3: day-ahead vs update TV, {len(split_jobs)} values")
    for i, job in enumerate(split_jobs, start=1):
        consume(job, f"S{i}/{len(split_jobs)}")

    eve_vals = unique_sorted(
        [
            max(0.0, best_tv - 0.05),
            best_tv,
            V002_TV,
            min(1.4, best_tv + 0.05),
            0.55,
        ]
    )
    eve_jobs = []
    for tv_early in (best_tv, V002_TV):
        for tv18 in eve_vals:
            if abs(tv_early - tv18) < 1e-12:
                continue
            eve_jobs.append(
                {
                    "name": f"eve_early{tv_early:.3f}_h18_{tv18:.3f}",
                    "family": "split_h18",
                    "tv0": tv_early,
                    "tv6": tv_early,
                    "tv12": tv_early,
                    "tv18": tv18,
                }
            )
    print(f"\nPhase 4: 18:00 TV different, {len(eve_jobs)} values")
    for i, job in enumerate(eve_jobs, start=1):
        consume(job, f"E{i}/{len(eve_jobs)}")

    table = pd.DataFrame(rows).sort_values("total_cost")
    table.to_csv(OUT / "policy_grid.csv", index=False, encoding="utf-8-sig")
    print("\n===== BEST =====")
    show = [
        "name",
        "family",
        "tv0",
        "tv6",
        "tv12",
        "tv18",
        "total_cost",
        "mean_soc_open",
        "emergency_kwh",
        "delta_vs_v002",
    ]
    print(table[show].head(15).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
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

    def jsonable(row: dict) -> dict:
        out = {}
        for key, value in row.items():
            if isinstance(value, (np.floating, np.integer)):
                out[key] = float(value)
            elif isinstance(value, (np.bool_, bool)):
                out[key] = bool(value)
            else:
                out[key] = value
        return out

    summary = {
        "parent": "v002",
        "v002_cost_yuan": V002_COST,
        "v002_tv": V002_TV,
        "anchors": {k: float(v) for k, v in anchors.items()},
        "n_evaluations": len(rows),
        "n_unique_lp_runs": len(cache),
        "elapsed_s": time.perf_counter() - t0,
        "best": jsonable(best),
        "beats_v002": bool(best["total_cost"] < V002_COST - 1e-6),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Elapsed", summary["elapsed_s"], "s")
    print("Unique LP runs", summary["n_unique_lp_runs"])
    print("Best vs v002", best["delta_vs_v002"])


if __name__ == "__main__":
    main()
