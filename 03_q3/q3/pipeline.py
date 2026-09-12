"""把一天按时间顺序串起来：0:00 计划 → 分段真实运行 → 到预报点再决定调不调。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from q3.config import CUT_MULT, DT_HOUR, EXTRA_MULT, ISSUE_HOURS, N_SLOTS
from q3.data import DayPack, slot_index_at_hour
from q3.planner import plan_slots
from q3.simulate import simulate_actual


@dataclass
class DayResult:
    date: str
    g_plan: np.ndarray          # 0:00 计划购电功率 kW
    g_adj: np.ndarray           # 最终执行的购电功率（含调整）
    ch: np.ndarray
    dis: np.ndarray
    emergency: np.ndarray
    waste: np.ndarray
    soc: np.ndarray             # 每格结束时的储电量
    e_start: float
    e_end: float
    cost_plan: float            # 按 0:00 计划量 × 电价
    cost_adjust: float          # 调整违约/溢价（相对 0:00 计划）
    cost_emergency: float
    cost_total: float
    adjusted_at: tuple[int, ...]


def _merge_arrays(base: dict, piece: dict, t_start: int, t_end: int) -> None:
    for key in ("ch", "dis", "emergency", "waste", "soc"):
        base[key][t_start:t_end] = piece[key][t_start:t_end]


def run_one_day(
    day: DayPack,
    e_start: float,
    adjust_hours: tuple[int, ...] = (6, 12),
) -> DayResult:
    """默认在 6:00、12:00 用新预报调整剩余时段；18:00 不调（当天几乎没光伏了）。"""
    T = N_SLOTS
    g_plan = plan_slots(
        price=day.price,
        load=day.load_forecast,
        pv=day.pv_forecast[0],
        e_start=e_start,
        t_start=0,
        t_end=T,
        g_ref=None,
    )["g"]

    g_commit = g_plan.copy()
    actual = {
        "ch": np.zeros(T),
        "dis": np.zeros(T),
        "emergency": np.zeros(T),
        "waste": np.zeros(T),
        "soc": np.zeros(T),
    }

    cursor = 0
    e_now = e_start
    used_adjust = []

    # 按 6/12/18 切开一天：先把上一段用真实数据跑完，再决定要不要改后面的计划
    checkpoints = [h for h in ISSUE_HOURS if h > 0] + [24]
    for hour in checkpoints:
        t_cut = T if hour == 24 else slot_index_at_hour(hour)
        if t_cut > cursor:
            piece = simulate_actual(
                day.load_actual, day.pv_actual, g_commit, e_now, cursor, t_cut
            )
            _merge_arrays(actual, piece, cursor, t_cut)
            e_now = piece["e_end"]
            cursor = t_cut

        if hour in adjust_hours:
            used_adjust.append(hour)
            replanned = plan_slots(
                price=day.price,
                load=day.load_forecast,  # 负荷仍用 0:00 那份（没有新的负荷预报）
                pv=day.pv_forecast[hour],
                e_start=e_now,
                t_start=t_cut,
                t_end=T,
                g_ref=g_plan,
            )
            g_commit[t_cut:] = replanned["g"][t_cut:]

    g_adj = g_commit
    cost_plan, cost_adjust, cost_em, cost_total = compute_costs(
        day.price, g_plan, g_adj, actual["emergency"]
    )
    return DayResult(
        date=str(day.date.date()),
        g_plan=g_plan,
        g_adj=g_adj,
        ch=actual["ch"],
        dis=actual["dis"],
        emergency=actual["emergency"],
        waste=actual["waste"],
        soc=actual["soc"],
        e_start=e_start,
        e_end=e_now,
        cost_plan=cost_plan,
        cost_adjust=cost_adjust,
        cost_emergency=cost_em,
        cost_total=cost_total,
        adjusted_at=tuple(used_adjust),
    )


def compute_costs(
    price: np.ndarray,
    g_plan: np.ndarray,
    g_adj: np.ndarray,
    emergency: np.ndarray,
) -> tuple[float, float, float, float]:
    """费用拆成三块，方便写论文。

    普通计划费：0:00 计划量 × 电价。
    调整费：少买的差额 × 50% 电价（违约）+ 多买的差额 × 1.5 倍电价
            再减去「少买时本来计划费里已经算进去、实际没买」的那部分，
            使得 调整后实际购电费 = 计划费 + 调整费。

    更直白的等价写法（对每一格）：
      若 adj <= plan：付 电价*(adj + 0.5*(plan-adj))
      若 adj >  plan：付 电价*(plan + 1.5*(adj-plan))
      另外紧急购电：5 * 电价 * emerg
    """
    dt = DT_HOUR
    over = np.maximum(g_adj - g_plan, 0.0)
    under = np.maximum(g_plan - g_adj, 0.0)
    # 计划费（按 0:00 报出的量）
    cost_plan = float(np.sum(price * g_plan * dt))
    # 调整相关：多买加 1.5 倍；少买相当于只退回 50%，即计划费里要留下 50% 违约
    # 总购电（不含紧急）= 计划费 + 1.5*p*over*dt - 0.5*p*under*dt
    cost_adjust = float(np.sum(price * (EXTRA_MULT * over - CUT_MULT * under) * dt))
    cost_em = float(np.sum(price * 5.0 * emergency * dt))
    cost_total = cost_plan + cost_adjust + cost_em
    return cost_plan, cost_adjust, cost_em, cost_total


def energy_kwh(power_kw: np.ndarray, t0: int = 0, t1: int = N_SLOTS) -> float:
    return float(np.sum(power_kw[t0:t1]) * DT_HOUR)
