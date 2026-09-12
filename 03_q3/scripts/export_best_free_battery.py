"""Re-run the winning free-battery policy and dump readable tables. Local only."""
from __future__ import annotations

import json
import sys
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

OUT = fb.OUTPUT_DIR
BEST_HORIZON = "rest_of_day"
BEST_RECOURSE = "greedy"
BEST_TV = float(rc.PRICE[:36].mean())  # night mean 0.4489...


def hour_blocks(values: np.ndarray) -> np.ndarray:
    return values.reshape(24, 6).sum(axis=1)


def main() -> None:
    result = fb.simulate_year(BEST_HORIZON, BEST_RECOURSE, BEST_TV)
    m = result["metrics"]
    dates = rc.REPORT_DAY_INDEX

    daily = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "soc_open_kwh": result["soc_open"],
            "soc_close_kwh": result["soc_close"],
            "plan_kwh": result["plan"].sum(axis=1),
            "final_kwh": result["adjusted"].sum(axis=1),
            "upward_kwh": result["upward"].sum(axis=1),
            "downward_kwh": result["downward"].sum(axis=1),
            "emergency_kwh": result["emergency"].sum(axis=1),
            "spill_kwh": result["spill"].sum(axis=1),
            "charge_kwh": result["charge"].sum(axis=1),
            "discharge_kwh": result["discharge"].sum(axis=1),
            "plan_cost_yuan": result["plan_cost"],
            "adjustment_cost_yuan": result["adjustment_cost"],
            "emergency_cost_yuan": result["emergency_cost"],
            "total_cost_yuan": result["total_cost"],
        }
    )
    daily.to_csv(OUT / "daily_eval.csv", index=False, encoding="utf-8-sig")

    monthly = daily.copy()
    monthly["month"] = pd.to_datetime(monthly["date"]).dt.strftime("%Y-%m")
    monthly_sum = monthly.groupby("month", as_index=False)["total_cost_yuan"].sum()
    v001_monthly = pd.read_csv(HERE / "versions" / "v001_four_quantile_grid_best" / "monthly_cost.csv")
    v001_monthly.columns = ["month", "v001_static", "v001"]
    merged = monthly_sum.merge(v001_monthly[["month", "v001"]], on="month", how="left")
    merged["saving_vs_v001"] = merged["v001"] - merged["total_cost_yuan"]
    merged.to_csv(OUT / "monthly_vs_v001.csv", index=False, encoding="utf-8-sig")

    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(len(merged))
    ax.bar(x - 0.18, merged["v001"], width=0.36, label="v001 (battery locked)")
    ax.bar(x + 0.18, merged["total_cost_yuan"], width=0.36, label="v002 (battery free)")
    ax.set_xticks(x)
    ax.set_xticklabels(merged["month"], rotation=45, ha="right")
    ax.set_ylabel("yuan")
    ax.set_title("Monthly purchase cost, 2025-02 to 2025-12")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "monthly_cost.png", dpi=120)
    plt.close(fig)

    report_rows = {
        date: int(np.flatnonzero(dates == pd.Timestamp(date))[0])
        for date in rc.REPORT_DATES
    }
    ten_min_rows = []
    hourly_rows = []
    for date, row in report_rows.items():
        day_idx = int(rc.EVAL_DAYS[row])
        plan = result["plan"][row]
        final = result["adjusted"][row]
        ch = result["charge"][row]
        dch = result["discharge"][row]
        soc = result["soc"][row]
        em = result["emergency"][row]
        sp = result["spill"][row]
        load = rc.LOAD_KWH[day_idx]
        pv = rc.PV_KWH[day_idx]
        net = rc.NET_KWH[day_idx]
        soc_before = np.empty_like(soc)
        soc_before[0] = result["soc_open"][row]
        soc_before[1:] = soc[:-1]
        for t, label in enumerate(rc.INTERVAL_LABELS):
            residual = float(net[t] - final[t])
            if residual >= 1e-9:
                action = "放电补缺口"
            elif residual <= -1e-9:
                action = "充电吃盈余"
            else:
                action = "不动"
            ten_min_rows.append(
                {
                    "date": date,
                    "interval": label,
                    "price_yuan_per_kwh": rc.PRICE[t],
                    "load_kwh": load[t],
                    "pv_kwh": pv[t],
                    "actual_net_kwh": net[t],
                    "planned_purchase_kwh": plan[t],
                    "final_purchase_kwh": final[t],
                    "charge_kwh": ch[t],
                    "discharge_kwh": dch[t],
                    "soc_before_kwh": soc_before[t],
                    "soc_after_kwh": soc[t],
                    "emergency_kwh": em[t],
                    "spill_kwh": sp[t],
                    "battery_action": action,
                }
            )
        for h in range(24):
            sl = slice(h * 6, (h + 1) * 6)
            hourly_rows.append(
                {
                    "date": date,
                    "hour": f"{h:02d}:00-{h + 1:02d}:00",
                    "price_yuan_per_kwh": float(rc.PRICE[sl].mean()),
                    "load_kwh": float(load[sl].sum()),
                    "pv_kwh": float(pv[sl].sum()),
                    "actual_net_kwh": float(net[sl].sum()),
                    "planned_purchase_kwh": float(plan[sl].sum()),
                    "final_purchase_kwh": float(final[sl].sum()),
                    "charge_kwh": float(ch[sl].sum()),
                    "discharge_kwh": float(dch[sl].sum()),
                    "soc_end_kwh": float(soc[sl][-1]),
                    "emergency_kwh": float(em[sl].sum()),
                    "spill_kwh": float(sp[sl].sum()),
                }
            )

    pd.DataFrame(ten_min_rows).to_csv(OUT / "paper_days_10min.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(hourly_rows).to_csv(OUT / "paper_days_hourly.csv", index=False, encoding="utf-8-sig")

    ch_all = result["charge"]
    dch_all = result["discharge"]
    idle = (ch_all < 1e-6) & (dch_all < 1e-6)
    charge_only = (ch_all >= 1e-6) & (dch_all < 1e-6)
    discharge_only = (dch_all >= 1e-6) & (ch_all < 1e-6)
    both = (ch_all >= 1e-6) & (dch_all >= 1e-6)
    n_slots = ch_all.size
    soc_open = result["soc_open"]
    stats = {
        "best": {
            "horizon": BEST_HORIZON,
            "recourse": BEST_RECOURSE,
            "terminal_value": BEST_TV,
        },
        "metrics": m,
        "slot_share": {
            "idle": float(idle.mean()),
            "charge": float(charge_only.mean()),
            "discharge": float(discharge_only.mean()),
            "both": float(both.mean()),
            "n_slots": int(n_slots),
        },
        "soc_open": {
            "mean": float(soc_open.mean()),
            "p10": float(np.quantile(soc_open, 0.10)),
            "p50": float(np.quantile(soc_open, 0.50)),
            "p90": float(np.quantile(soc_open, 0.90)),
            "min": float(soc_open.min()),
            "max": float(soc_open.max()),
        },
        "paper_days": {},
    }
    for date, row in report_rows.items():
        stats["paper_days"][date] = {
            "soc_open": float(result["soc_open"][row]),
            "soc_close": float(result["soc_close"][row]),
            "plan_kwh": float(result["plan"][row].sum()),
            "final_kwh": float(result["adjusted"][row].sum()),
            "charge_kwh": float(result["charge"][row].sum()),
            "discharge_kwh": float(result["discharge"][row].sum()),
            "emergency_kwh": float(result["emergency"][row].sum()),
            "spill_kwh": float(result["spill"][row].sum()),
            "plan_cost": float(result["plan_cost"][row]),
            "adjustment_cost": float(result["adjustment_cost"][row]),
            "emergency_cost": float(result["emergency_cost"][row]),
            "total_cost": float(result["total_cost"][row]),
            "charge_4h": [float(x) for x in fb.block_totals(result["charge"][row])],
            "discharge_4h": [float(x) for x in fb.block_totals(result["discharge"][row])],
        }

    (OUT / "best_details.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("Wrote extra tables. total_cost", m["total_cost"])


if __name__ == "__main__":
    main()
