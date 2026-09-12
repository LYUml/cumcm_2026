# Q3 方案台账（只存在本地，不要 push）

每一版一个子文件夹：`spec.json` 是假设和参数，其余是当年跑出来的计划与结果。
比总费用：降低则 `kept` / `champion`，没有降低则 `discarded`。

- 当前正式最优（champion）：`v002`
- 已记录版本数：4

| 编号 | 状态 | 相对谁 | 总费用（元） | 差额（元） | 标题 |
|---|---|---|---:|---:|---|
| v000 | kept | — | 14,669,597.26 | — | 计费改正，组员其余原样 |
| v001 | kept | v000 | 14,438,642.68 | -230,954.58 | 四次缓冲独立网格最优：0.75 / 0.85 / 0.85 / 0.80，三次都开 |
| v002 | champion | v001 | 13,521,409.71 | -917,232.98 | 解开三把电池锁：跨夜 SOC + 当天剩余时域重排 + 实时贪心充放 |
| v003 | discarded | v002 | 13,524,284.68 | +2,874.98 | 晚间最低价时段向午夜目标充电（相对 v002 的全量扫描） |

## 怎么记下一版

1. 先改代码或参数，全年跑完，结果写在 `Q3_new/outputs/`。
2. 写好该版 `spec.json`（可先抄 v000 再改变动项）。
3. 运行：

```bash
python Q3_new/record_version.py --id v00x --slug short_name --title "一句话" --parent v000 --status trial --spec-json ...
```

4. 看总费用是否低于 parent / champion。低则 `--status kept` 或改成 `champion`；否则 `--status discarded`。
