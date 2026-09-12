"""Snapshot one Q3 scheme into Q3_new/versions/. Local only. Do not git push.

Typical use after a full-year run has written Q3_new/outputs/:

    python Q3_new/record_version.py \\
        --id v001 \\
        --slug raise_intraday_buffer \\
        --title "日内缓冲 0.70→0.80" \\
        --parent v000 \\
        --status discarded \\
        --spec-json path/to/spec.json

If --spec-json is omitted, the script copies spec.json already sitting in
the version folder (write spec first, then record). If the version folder
does not exist yet, pass --spec-json and it will be created.

status: champion | kept | discarded | trial
  champion = current official best (exactly one)
  kept     = better or useful, not the official pointer
  discarded = did not beat parent total cost (or rejected for other reasons)
  trial    = recorded but decision not yet made

Never overwrites an existing version folder unless --force.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if (HERE.parent / "versions").exists() else HERE
OUTPUT_DIR = ROOT / "outputs"
VERSIONS_DIR = ROOT / "versions"
CATALOG_PATH = VERSIONS_DIR / "catalog.json"
LEDGER_PATH = VERSIONS_DIR / "LEDGER.md"

SNAPSHOT_FILES = [
    "result3.xlsx",
    "summary.json",
    "subset_comparison.csv",
    "monthly_cost.csv",
    "monthly_cost.png",
    "table1.csv",
    "table2_charge.csv",
    "table2_discharge.csv",
    "table2_soc.csv",
    "table3_emergency.csv",
    "forecast_quality.csv",
    "block_forecast_mae.csv",
    "sample_2025-06-21.png",
]


def load_catalog() -> dict:
    if CATALOG_PATH.exists():
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {"champion": None, "versions": []}


def save_catalog(catalog: dict) -> None:
    CATALOG_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def copy_outputs(dest: Path) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    missing = []
    for name in SNAPSHOT_FILES:
        src = OUTPUT_DIR / name
        if not src.exists():
            missing.append(name)
            continue
        shutil.copy2(src, dest / name)
        copied.append(name)
    if missing:
        print("Warning, not found in outputs/:", ", ".join(missing))
    return copied


def yuan(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


def rebuild_ledger(catalog: dict) -> None:
    lines = [
        "# Q3 方案台账（只存在本地，不要 push）",
        "",
        "每一版一个子文件夹：`spec.json` 是假设和参数，其余是当年跑出来的计划与结果。",
        "比总费用：降低则 `kept` / `champion`，没有降低则 `discarded`。",
        "",
        f"- 当前正式最优（champion）：`{catalog.get('champion')}`",
        f"- 已记录版本数：{len(catalog.get('versions', []))}",
        "",
        "| 编号 | 状态 | 相对谁 | 总费用（元） | 差额（元） | 标题 |",
        "|---|---|---|---:|---:|---|",
    ]
    for entry in catalog.get("versions", []):
        delta = entry.get("delta_vs_parent_yuan")
        delta_s = "—" if delta is None else f"{delta:+,.2f}"
        lines.append(
            "| {id} | {status} | {parent} | {cost} | {delta} | {title} |".format(
                id=entry["id"],
                status=entry.get("status", ""),
                parent=entry.get("parent") or "—",
                cost=yuan(entry.get("total_cost_yuan")),
                delta=delta_s,
                title=entry.get("title", ""),
            )
        )
    lines.extend(
        [
            "",
            "## 怎么记下一版",
            "",
            "1. 先改代码或参数，全年跑完，结果写在 `Q3_new/outputs/`。",
            "2. 写好该版 `spec.json`（可先抄 v000 再改变动项）。",
            "3. 运行：",
            "",
            "```bash",
            "python Q3_new/record_version.py --id v00x --slug short_name --title \"一句话\" --parent v000 --status trial --spec-json ...",
            "```",
            "",
            "4. 看总费用是否低于 parent / champion。低则 `--status kept` 或改成 `champion`；否则 `--status discarded`。",
            "",
        ]
    )
    LEDGER_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Record one local Q3 scheme version.")
    parser.add_argument("--id", required=True, help="e.g. v000")
    parser.add_argument("--slug", required=True, help="folder suffix, e.g. corrected_billing_teammate")
    parser.add_argument("--title", required=True)
    parser.add_argument("--parent", default=None)
    parser.add_argument(
        "--status",
        choices=("champion", "kept", "discarded", "trial"),
        default="trial",
    )
    parser.add_argument("--spec-json", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-copy", action="store_true", help="only refresh catalog/ledger")
    args = parser.parse_args()

    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    folder = VERSIONS_DIR / f"{args.id}_{args.slug}"
    if folder.exists() and not args.force and not args.skip_copy:
        raise SystemExit(f"Already exists: {folder}. Use --force to overwrite artifacts.")

    if args.spec_json:
        spec = json.loads(args.spec_json.read_text(encoding="utf-8"))
    elif (folder / "spec.json").exists():
        spec = json.loads((folder / "spec.json").read_text(encoding="utf-8"))
    else:
        raise SystemExit("Need --spec-json or an existing spec.json in the version folder.")

    spec["id"] = args.id
    spec["slug"] = args.slug
    spec["title"] = args.title
    spec["status"] = args.status
    spec["parent"] = args.parent
    spec.setdefault("recorded", date.today().isoformat())

    copied: list[str] = []
    if not args.skip_copy:
        copied = copy_outputs(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    results = spec.get("results") or {}
    total = results.get("total_cost_yuan")
    catalog = load_catalog()
    parent_total = None
    if args.parent:
        for existing in catalog["versions"]:
            if existing["id"] == args.parent:
                parent_total = existing.get("total_cost_yuan")
                break
        if parent_total is None:
            parent_spec = None
            for child in VERSIONS_DIR.glob(f"{args.parent}_*/spec.json"):
                parent_spec = json.loads(child.read_text(encoding="utf-8"))
                parent_total = (parent_spec.get("results") or {}).get("total_cost_yuan")
                break
    delta = None if total is None or parent_total is None else float(total) - float(parent_total)

    entry = {
        "id": args.id,
        "slug": args.slug,
        "title": args.title,
        "status": args.status,
        "parent": args.parent,
        "folder": folder.name,
        "total_cost_yuan": total,
        "delta_vs_parent_yuan": delta,
        "selected_updates": results.get("selected_updates"),
        "recorded": spec.get("recorded"),
        "copied_files": copied or None,
    }
    catalog["versions"] = [v for v in catalog["versions"] if v["id"] != args.id]
    catalog["versions"].append(entry)
    catalog["versions"].sort(key=lambda v: v["id"])
    if args.status == "champion":
        old = catalog.get("champion")
        for version in catalog["versions"]:
            if version["id"] == old and version["id"] != args.id:
                version["status"] = "kept"
        catalog["champion"] = args.id
    elif catalog.get("champion") == args.id and args.status != "champion":
        catalog["champion"] = None
    save_catalog(catalog)
    rebuild_ledger(catalog)
    print("Recorded", args.id, "→", folder)
    print("Champion:", catalog.get("champion"))
    print("Ledger:", LEDGER_PATH)


if __name__ == "__main__":
    main()
