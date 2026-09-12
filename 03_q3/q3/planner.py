"""线性规划：在一段未来时段里，决定买多少电、电池怎么充放。

每个 10 分钟格要决定：
  g   向外网买电的功率 (kW)
  ch  充电功率 (kW)
  dis 放电功率 (kW)
  w   光伏用不完、电池也存不下时丢掉的功率（弃光）
  em  紧急购电功率（计划阶段一般会是 0，因为普通购电更便宜）

功率平衡（每个格都要成立）：
  光伏 + 放电 + 普通购电 + 紧急购电 = 负荷 + 充电 + 弃光

电池：
  E_end = E_start + η * ch * dt - dis * dt / η
  电量夹在 1200～10800 kWh，充放功率不超过 5000 kW
"""

from __future__ import annotations

import numpy as np
from pulp import (
    PULP_CBC_CMD,
    LpMinimize,
    LpProblem,
    LpStatus,
    LpVariable,
    lpSum,
    value,
)

from q3.config import (
    CUT_MULT,
    DT_HOUR,
    E_HIGH,
    E_MIN,
    EMERGENCY_MULT,
    ETA,
    EXTRA_MULT,
    N_SLOTS,
    P_MAX,
)


def plan_slots(
    price: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    e_start: float,
    t_start: int = 0,
    t_end: int = N_SLOTS,
    g_ref: np.ndarray | None = None,
) -> dict:
    """对 [t_start, t_end) 做优化。

    g_ref is None：这是 0:00 的日前计划，目标 = 普通购电费。
    g_ref 给定：这是调整，多买按 1.5 倍、少买按 50% 违约，相对 0:00 计划结算。
    """
    prob = LpProblem("microgrid_plan", LpMinimize)
    idx = range(t_start, t_end)

    g = {t: LpVariable(f"g_{t}", lowBound=0) for t in idx}
    ch = {t: LpVariable(f"ch_{t}", lowBound=0, upBound=P_MAX) for t in idx}
    dis = {t: LpVariable(f"dis_{t}", lowBound=0, upBound=P_MAX) for t in idx}
    w = {t: LpVariable(f"w_{t}", lowBound=0) for t in idx}
    em = {t: LpVariable(f"em_{t}", lowBound=0) for t in idx}
    e = {t: LpVariable(f"e_{t}", lowBound=E_MIN, upBound=E_HIGH) for t in idx}

    over = under = None
    if g_ref is not None:
        over = {t: LpVariable(f"over_{t}", lowBound=0) for t in idx}
        under = {t: LpVariable(f"under_{t}", lowBound=0) for t in idx}
        for t in idx:
            # 调整后购电 = 原计划 + 多买 - 少买
            prob += g[t] == float(g_ref[t]) + over[t] - under[t]

    e_prev = e_start
    for t in idx:
        # 功率平衡
        prob += (
            float(pv[t]) + dis[t] + g[t] + em[t]
            == float(load[t]) + ch[t] + w[t]
        )
        # 电池状态
        prob += e[t] == e_prev + ETA * ch[t] * DT_HOUR - dis[t] * DT_HOUR / ETA
        e_prev = e[t]

    costs = []
    for t in idx:
        p = float(price[t])
        if g_ref is None:
            costs.append(p * g[t] * DT_HOUR)
        else:
            # 相对原计划：少买退回 50%（等于留下 50% 违约），多买按 1.5 倍
            costs.append(
                p * float(g_ref[t]) * DT_HOUR
                + EXTRA_MULT * p * over[t] * DT_HOUR
                - CUT_MULT * p * under[t] * DT_HOUR
            )
        costs.append(EMERGENCY_MULT * p * em[t] * DT_HOUR)
    prob += lpSum(costs)

    solver = PULP_CBC_CMD(msg=False, timeLimit=20)
    status = prob.solve(solver)
    if LpStatus[status] != "Optimal":
        raise RuntimeError(f"优化失败：{LpStatus[status]}")

    g_out = np.zeros(N_SLOTS)
    ch_out = np.zeros(N_SLOTS)
    dis_out = np.zeros(N_SLOTS)
    w_out = np.zeros(N_SLOTS)
    em_out = np.zeros(N_SLOTS)
    e_out = np.zeros(N_SLOTS)
    for t in idx:
        g_out[t] = value(g[t]) or 0.0
        ch_out[t] = value(ch[t]) or 0.0
        dis_out[t] = value(dis[t]) or 0.0
        w_out[t] = value(w[t]) or 0.0
        em_out[t] = value(em[t]) or 0.0
        e_out[t] = value(e[t]) or 0.0

    e_end = e_out[t_end - 1]
    return {
        "g": g_out,
        "ch": ch_out,
        "dis": dis_out,
        "waste": w_out,
        "emergency": em_out,
        "soc": e_out,
        "e_end": e_end,
        "obj": float(value(prob.objective) or 0.0),
    }
