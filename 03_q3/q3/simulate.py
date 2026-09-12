"""计划购电量已经锁定后，用「这一格真实的负荷、光伏」操作电池。

这一步不再改普通购电：买多了也按计划付钱，买少了不够就紧急购电（5 倍）。
电池还是可以在这一格里充或放，规则是贪心、好写进论文：
- 真实净需求 = 负荷 - 光伏 - 计划购电
- 净需求 > 0：先放电，还不够就紧急买
- 净需求 < 0：先充电，还多就弃光
"""

from __future__ import annotations

import numpy as np

from q3.config import DT_HOUR, E_HIGH, E_MIN, ETA, N_SLOTS, P_MAX


def simulate_actual(
    load: np.ndarray,
    pv: np.ndarray,
    g_commit: np.ndarray,
    e_start: float,
    t_start: int = 0,
    t_end: int = N_SLOTS,
) -> dict:
    ch = np.zeros(N_SLOTS)
    dis = np.zeros(N_SLOTS)
    em = np.zeros(N_SLOTS)
    waste = np.zeros(N_SLOTS)
    soc = np.zeros(N_SLOTS)
    e = e_start

    for t in range(t_start, t_end):
        residual = float(load[t] - pv[t] - g_commit[t])
        if residual > 1e-9:
            # 还缺电：放电上限同时受功率、剩余电量限制
            # 放出 P 持续 dt，电池少 P*dt/η，且电量不能低于 E_MIN
            p_soc = max(0.0, (e - E_MIN) * ETA / DT_HOUR)
            p_dis = min(P_MAX, p_soc, residual)
            dis[t] = p_dis
            still = residual - p_dis
            em[t] = max(0.0, still)
            e = e - p_dis * DT_HOUR / ETA
        else:
            surplus = -residual
            # 充电：充 P 持续 dt，电池多 η*P*dt，且不能超过 E_HIGH
            p_soc = max(0.0, (E_HIGH - e) / (ETA * DT_HOUR))
            p_ch = min(P_MAX, p_soc, surplus)
            ch[t] = p_ch
            waste[t] = max(0.0, surplus - p_ch)
            e = e + ETA * p_ch * DT_HOUR
        e = min(max(e, E_MIN), E_HIGH)
        soc[t] = e

    return {
        "ch": ch,
        "dis": dis,
        "emergency": em,
        "waste": waste,
        "soc": soc,
        "e_end": e,
    }
