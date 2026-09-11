"""Fail if the Q2 manuscript drifts from authoritative corrected outputs."""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

Q2 = Path(__file__).resolve().parents[1]
PAPER = Q2 / "paper/Q2_PAPER_ENGLISH.md"
OUT = Q2 / "outputs"


def money(value: float) -> str:
    return f"{value:,.2f}".replace(",", r"\,")


def main() -> None:
    text = PAPER.read_text(encoding="utf-8")
    validation = json.loads((OUT / "validation.json").read_text(encoding="utf-8"))
    daily = pd.read_csv(OUT / "specified_dates_purchase.csv")
    storage = pd.read_csv(OUT / "specified_dates_storage.csv")
    emergency = pd.read_csv(OUT / "specified_dates_emergency.csv")
    comparison = pd.read_csv(OUT / "model_comparison/comparison.csv")

    required = [
        money(validation["planned_yuan"]),
        money(validation["emergency_yuan"]),
        money(validation["total_yuan"]),
        str(validation["actual_midnight_below_3000_days"]),
        f'{validation["max_planning_vs_feedback_terminal_soc_gap_kwh"]:.2f}',
        f'{validation["max_planning_vs_feedback_cost_gap_yuan"]:,.2f}',
    ]
    for value in required:
        assert value in text, f"paper is missing authoritative value {value}"

    expected_dates = {"2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"}
    assert set(daily["date"].astype(str)) == expected_dates
    assert set(storage["date"].astype(str)) == expected_dates
    assert set(emergency["date"].astype(str)) <= expected_dates
    for date in expected_dates:
        assert date in text, f"paper is missing required date {date}"

    assert len(comparison) == 6 and comparison["model"].nunique() == 6
    assert comparison["selected"].sum() == 1
    for value in comparison["total_yuan"] / 1e6:
        assert f"{value:.4f}" in text, f"paper is missing comparison total {value:.4f}"

    for rel in ("../outputs/q2_cost_chronology.png",
                "../outputs/q2_model_comparison.png",
                "../outputs/q2_representative_day_corrected.png"):
        assert rel in text and (PAPER.parent / rel).resolve().exists(), rel

    forbidden = ["13,168,516.81", "617,373.55", "13,785,890.36",
                 "13,790,230.54", "15,260 scenario", "on 68 days",
                 "actual daily hard constraint is 3000"]
    for stale in forbidden:
        assert stale not in text, f"stale claim remains: {stale}"
    print("Q2 paper is synchronized with corrected outputs.")


if __name__ == "__main__":
    main()
