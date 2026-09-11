"""Information available when an official purchase row is committed at midnight.

Official row ``d`` contains 00:10 on date d through 00:10 on date d+1.  At
00:00 on date d, rows through d-2 are complete, while row d-1 is missing its
last (00:00-00:10 on date d) interval.  These helpers prevent that pending
measurement from entering a forecast or scenario set.
"""
from __future__ import annotations

import numpy as np


LAST_SLOT = 143


def latest_complete_row(decision_day: int) -> int:
    """Largest row index whose every interval is observed at the decision."""
    return decision_day - 2


def recent_window(data: np.ndarray, decision_day: int, days: int) -> np.ndarray:
    """Recent observations with a slot-wise midnight availability boundary."""
    start = max(0, decision_day - days)
    block = np.asarray(data[start:decision_day], float).copy()
    if len(block):
        block[-1, LAST_SLOT] = np.nan
    return block


def slotwise_median(data: np.ndarray, decision_day: int, days: int = 7) -> np.ndarray:
    """Median of recent rows, excluding the pending latest-row final slot."""
    return np.nanmedian(recent_window(data, decision_day, days), axis=0)


def previous_row_curve(data: np.ndarray, decision_day: int) -> np.ndarray:
    """Previous-row persistence with the unavailable last slot backed off once."""
    if decision_day <= 0:
        return np.zeros(data.shape[1], dtype=float)
    curve = np.asarray(data[decision_day - 1], float).copy()
    curve[LAST_SLOT] = data[decision_day - 2, LAST_SLOT] if decision_day >= 2 else 0.0
    return curve


def complete_residual_candidates(decision_day: int, window: int = 56) -> np.ndarray:
    """Rows whose realized 144-slot residual path is fully known at midnight."""
    return np.arange(max(7, decision_day - window), max(7, decision_day - 1))
