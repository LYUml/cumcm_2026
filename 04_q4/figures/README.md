# Q4 figures — Prism handoff

已按 vivid-figures-skill 生成 6 张英文科研数据图，沿用 Q2 成图的配色、
DejaVu Serif 字体、浅色填充/原色边框和 6-inch 原生宽度。未更改求解器或重算策略。

| 图 | 内容 | 论文位置 |
|---|---|---|
| F1 | 预测误差与运行成本的不同排序 | §4，预测器选择之后 |
| F2 | 净负荷—电价配对情景 | §5，残差配对公式之后 |
| F3 | Q4-2 代表日运行 | §6.3，全年结果分析之后 |
| F4 | Q4-3 滚动预测、购电修订及储能 | §7.3，结算公式之后 |
| F5 | 不同更新时点的费用与紧急购电 | §7.5，更新时点实验之后 |
| F6 | 月度费用及紧急电量比较 | §8 或附录，正文空间不足时移出 |

## 给 Prism

上传 `paper/q4_paper_english.md` 和本目录的六份 `fig_q4_f*.pdf`。
论文已有对应位置和完整英文 caption；`latex_includes.tex` 可直接复制。
优先使用矢量 PDF，PNG 为 300 dpi 预览备用。不要把图截图后再插入。
若正文宽度 160 mm，使用 `width=0.96\textwidth`（153.6 mm），保持与 Q2 一致。
不要把 F3/F4 缩成半栏；如版面紧张，减少正文图数量，而非牺牲字号。
没有重排或编译全文，因此最终浮动位置仍需在完整论文中检查。

## 口径说明

- F1 的费用是放大刻度的点图，非从零开始的柱图；不是置信区间。
- F2 十二条情景来自原 Q4-2 函数，相同颜色/线型在上下 panel 对应同一残差日期。
  三层渐变是十二条情景的经验范围，不应被称为 95% 置信区间。
- F3/F4 分为四个 panel，让价格、购电功率、电池功率、储能各自有单位。
  时间轴保留附件行定义：当日 00:10 至次日 00:10，不能直接当成自然日 00:00--24:00。
- F4 的价格曲线由现有 `point_price` 函数原样提取执行，不拟合新的模型。
  购电 panel 仅展示“午夜初始计划—最终计划”，没有假造各次优化的完整中间尾部。
  本轮是已有结果的可视化，不构成对优化实现信息可用性的新审计。
- F5 比较四个已运行的嵌套更新集合，不能外推到所有更新组合。
- F6 每月费用由原始日结果求和。Q4-3 在 2、8、9 月费用略高，全年费用更低；
  这是完整策略对比，信息价值的控制实验应看 F5。

## 复现

在 `04_q4` 下运行，Python 需 numpy/pandas/matplotlib/scipy/scikit-learn/openpyxl：

```bash
python figures/prepare_data.py
python figures/gen_fig_q4_f1.py
python figures/gen_fig_q4_f2.py
python figures/gen_fig_q4_f3.py
python figures/gen_fig_q4_f4.py
python figures/gen_fig_q4_f5.py
python figures/gen_fig_q4_f6.py
python figures/verify_figures.py
```

各图共用 `_figbase.py`（其中 `finish` 调用技能提供的 `save_fig`）。
因此原技能静态脚本对每个生成文件提示“没有 save_fig”属于共享函数封装的提示，
实际六份 PDF 和 PNG 均逐个检查。每张图对应独立可运行脚本。
原始输入见 `../FIGURE_MANIFEST.md`；抽取的代表日数组与月度 CSV 在 `data/`。
