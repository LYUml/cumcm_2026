"""读附件 1/2/3，拼出「某一天做计划时手里有什么」。

约定：
- 一天 144 个 10 分钟格，顺序与附件 2 的列完全一致。
- 第 0 格对应模板里的 0:10-0:20，最后一格是 0:00-0:10+1。
- 附件 3「预报 k 小时」= 发布时刻往前数 k 个整点的光伏功率（kW）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta

import numpy as np
import pandas as pd

from q3.config import ATTACH, DT_HOUR, ISSUE_HOURS, N_SLOTS


def _time_label(col) -> str:
    if isinstance(col, time):
        return f"{col.hour:02d}:{col.minute:02d}"
    text = str(col).strip()
    if text in {"0:00+1", "00:00+1"}:
        return "24:00"
    if text.endswith("+1"):
        return "24:00"
    return text


def _hour_of_slot(t: int) -> float:
    """第 t 格起点距当天 0:00 多少小时。t=0 → 0:10，t=143 → 24:00。"""
    return (10 + 10 * t) / 60.0


@dataclass(frozen=True)
class DayPack:
    """一天建模要用的全部曲线。数组长度都是 144。"""

    date: pd.Timestamp
    slot_labels: list[str]
    price: np.ndarray
    load_actual: np.ndarray
    pv_actual: np.ndarray
    load_forecast: np.ndarray
    pv_forecast: dict[int, np.ndarray]  # 发布时刻 0/6/12/18 → 144 格预报


class DataHub:
    def __init__(self) -> None:
        att1 = pd.read_excel(ATTACH / "附件1.xlsx")
        self.price = att1["电价"].to_numpy(dtype=float)
        self.typical_load = att1["小区负载"].to_numpy(dtype=float)
        self.typical_pv = att1["光伏发电预测功率"].to_numpy(dtype=float)
        if len(self.price) != N_SLOTS:
            raise ValueError(f"附件 1 应为 {N_SLOTS} 行，实际 {len(self.price)}")

        load = pd.read_excel(ATTACH / "附件2.xlsx", sheet_name="小区负载")
        pv = pd.read_excel(ATTACH / "附件2.xlsx", sheet_name="光伏发电实际功率")
        self.slot_labels = [_time_label(c) for c in load.columns[1:]]
        self.dates = pd.to_datetime(load.iloc[:, 0]).dt.normalize()
        self.load = pd.DataFrame(
            load.iloc[:, 1:].to_numpy(dtype=float),
            index=self.dates,
        )
        self.pv = pd.DataFrame(
            pv.iloc[:, 1:].to_numpy(dtype=float),
            index=self.dates,
        )

        fc = pd.read_excel(ATTACH / "附件3.xlsx")
        fc["日期"] = pd.to_datetime(fc["日期"].ffill())
        self.forecasts: dict[tuple[pd.Timestamp, int], np.ndarray] = {}
        hour_map = {"0:00": 0, "6:00": 6, "12:00": 12, "18:00": 18}
        for _, row in fc.iterrows():
            issue = hour_map[str(row["预报时刻"]).strip()]
            hourly = np.array(
                [row[f"预报{k}小时"] for k in range(1, 25)],
                dtype=float,
            )
            self.forecasts[(pd.Timestamp(row["日期"]).normalize(), issue)] = hourly

        self.slot_labels_interval = self._interval_labels()

    def _interval_labels(self) -> list[str]:
        """与 result3 模板一致：0:10-0:20, ..., 0:00-0:10+1。"""
        labels = []
        for t in range(N_SLOTS):
            start = 10 + 10 * t  # 距 0:00 的分钟
            end = start + 10
            labels.append(f"{self._mm(start)}-{self._mm(end)}")
        return labels

    @staticmethod
    def _mm(minutes: int) -> str:
        if minutes >= 24 * 60:
            extra = minutes - 24 * 60
            h, m = divmod(extra, 60)
            return f"{h}:{m:02d}+1"
        h, m = divmod(minutes, 60)
        return f"{h}:{m:02d}"

    def load_forecast(self, date: pd.Timestamp) -> np.ndarray:
        """负荷没有官方预报：用上周同一天的真实曲线；没有则用附件 1 年均值。"""
        prev = date - timedelta(days=7)
        if prev in self.load.index:
            return self.load.loc[prev].to_numpy(dtype=float)
        return self.typical_load.copy()

    def pv_forecast_10min(self, date: pd.Timestamp, issue_hour: int) -> np.ndarray:
        hourly = self.forecasts[(date, issue_hour)]
        xs = []
        ys = []
        if issue_hour == 0:
            xs.append(0.0)
            ys.append(0.0)
        for k in range(1, 25):
            xs.append(float(issue_hour + k))
            ys.append(float(hourly[k - 1]))
        mids = np.array([_hour_of_slot(t) + DT_HOUR / 2 for t in range(N_SLOTS)])
        out = np.interp(mids, xs, ys)
        return np.clip(out, 0.0, None)

    def day(self, date: str | pd.Timestamp) -> DayPack:
        date = pd.Timestamp(date).normalize()
        if date not in self.load.index:
            raise KeyError(f"附件 2 没有 {date.date()}")
        pv_fc = {h: self.pv_forecast_10min(date, h) for h in ISSUE_HOURS}
        return DayPack(
            date=date,
            slot_labels=self.slot_labels_interval,
            price=self.price,
            load_actual=self.load.loc[date].to_numpy(dtype=float),
            pv_actual=self.pv.loc[date].to_numpy(dtype=float),
            load_forecast=self.load_forecast(date),
            pv_forecast=pv_fc,
        )

    def all_dates(self) -> list[pd.Timestamp]:
        return list(self.dates)


def slot_index_at_hour(hour: int) -> int:
    """hour=6 → 从 6:00-6:10 这一格开始（含）。"""
    if hour == 0:
        return 0
    return (hour * 60 - 10) // 10


if __name__ == "__main__":
    hub = DataHub()
    d = hub.day("2025-03-20")
    print("日期", d.date.date())
    print("格数", len(d.price), "第一格", d.slot_labels[0], "最后一格", d.slot_labels[-1])
    print("电价 min/max", d.price.min(), d.price.max())
    print("负荷预报/实际 日电量 kWh", d.load_forecast.sum() * DT_HOUR, d.load_actual.sum() * DT_HOUR)
    print("光伏 0:00预报/实际 日电量 kWh", d.pv_forecast[0].sum() * DT_HOUR, d.pv_actual.sum() * DT_HOUR)
    print("6:00 起第几格", slot_index_at_hour(6))
    print("读数据通过。")
