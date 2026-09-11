"""Canonical Q2 time semantics anchored to the official result2 template.

The source workbooks label columns 00:10,...,00:00+1 and the official purchase
template labels the corresponding columns 00:10-00:20,...,00:00-00:10+1.
Accordingly, array slot t is treated as the interval whose *left endpoint* is
the source label.  This is the only convention that preserves a one-to-one,
non-circular mapping to all 144 official output columns without inventing a
2026-01-01 observation.  The problem statement does not explicitly say
whether source labels are samples or interval representatives; that ambiguity
is recorded in the delivery validation and paper.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import csv

SLOTS_PER_DAY = 144
SLOT_MINUTES = 10


def clock(minute: int, plus_one: bool = False) -> str:
    minute %= 1440
    suffix = "+1" if plus_one else ""
    return f"{minute // 60}:{minute % 60:02d}{suffix}"


def source_label(slot: int) -> str:
    minute = (slot + 1) * SLOT_MINUTES
    return "0:00+1" if minute == 1440 else clock(minute)


def interval_label(slot: int) -> str:
    start = (slot + 1) * SLOT_MINUTES
    end = (slot + 2) * SLOT_MINUTES
    return f"{clock(start, start >= 1440)}-{clock(end, end >= 1440)}"


def interval_bounds(day: datetime, slot: int) -> tuple[datetime, datetime]:
    start = day + timedelta(minutes=(slot + 1) * SLOT_MINUTES)
    return start, start + timedelta(minutes=SLOT_MINUTES)


def state_label(boundary: int) -> str:
    """Boundary 0 is pre-slot state; boundary k is after slot k-1."""
    if boundary == 0:
        return "pre-0:10 planning state (template calls this 0:00)"
    minute = (boundary + 1) * SLOT_MINUTES
    return clock(minute, minute >= 1440)


def four_hour_blocks() -> list[tuple[int, int, str]]:
    """Six consecutive 24-slot blocks in the template-anchored horizon."""
    return [(24*b, 24*(b+1),
             f"{interval_label(24*b).split('-')[0]}-{interval_label(24*(b+1)-1).split('-')[1]}")
            for b in range(6)]


def write_mapping_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["source_time_label", "physical_interval", "array_index",
                    "result2_column", "storage_state_before", "storage_state_after"])
        for t in range(SLOTS_PER_DAY):
            w.writerow([source_label(t), interval_label(t), t, t + 2,
                        state_label(t), state_label(t + 1)])
