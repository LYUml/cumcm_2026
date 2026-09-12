<!-- BEGIN FIGURE_MANIFEST -->
## Q4 figure manifest

**数据图（matplotlib；paper-figure）：**
- fig_q4_f1 | format=pdf,png | output=figures/fig_q4_f1.pdf,png | claim=Point accuracy and operating value rank forecasters differently | source=outputs/q4_2_comparison/price_forecast_comparison.csv,outputs/q4_2_comparison/policy_cost_comparison.csv | section=4 | language=en | layout=single-landscape | recipe:basic.multipanel
- fig_q4_f2 | format=pdf,png | output=figures/fig_q4_f2.pdf,png | claim=Each scenario pairs both residuals from one historical date | source=figures/data/representative_day.npz | section=5 | language=en | layout=single-landscape | recipe:basic.line
- fig_q4_f3 | format=pdf,png | output=figures/fig_q4_f3.pdf,png | claim=Q4-2 purchase and battery operation under fluctuating prices | source=outputs/q4_2_comparison/policy_weekday_mean_4w.npz | section=6.3 | language=en | layout=single-landscape | recipe:basic.multipanel
- fig_q4_f4 | format=pdf,png | output=figures/fig_q4_f4.pdf,png | claim=Q4-3 forecasts and final purchase differ from midnight commitments | source=outputs/q4_3_stochastic/policy.npz,figures/data/representative_day.npz | section=7.3 | language=en | layout=single-landscape | recipe:basic.multipanel
- fig_q4_f5 | format=pdf,png | output=figures/fig_q4_f5.pdf,png | claim=All three updates reduce total cost and emergency reliance | source=outputs/q4_3_stochastic/update_subset_comparison.csv | section=7.5 | language=en | layout=single-landscape | recipe:basic.grouped_bar
- fig_q4_f6 | format=pdf,png | output=figures/fig_q4_f6.pdf,png | claim=Monthly outcomes compare two complete policies rather than isolate a causal effect | source=figures/data/monthly_comparison.csv | section=8/appendix | language=en | layout=single-landscape | recipe:basic.grouped_bar

**DrawIO 确定性技术图（paper-technical-diagram）：**
- none
**TikZ 精确图（paper-technical-diagram）：**
- none
**AI 场景图（paper-illustration）：**
- none
**显式可选格式（HTML / Mermaid）：**
- none
**总数：** DATA=6, DRAWIO=0, TIKZ=0, ILLUSTRATION=0, OPTIONAL=0, ALL=6
<!-- END FIGURE_MANIFEST -->

Scope: six previously planned Q4 figures, not a whole-paper redesign. F6 is supplementary.
Q2's existing red/purple palette, DejaVu Serif typography and 6-inch native width
are authoritative style references. Inclusion width is 0.96 of a 160-mm text
block (153.6 mm), matching the existing Q2 artwork: scale 1.008, smallest 7.5-pt
legend becomes 7.56 pt. Do not shrink these multi-panel figures into half columns.
F1 retains a magnified dot axis for the closely spaced cost values, with explicit
ticks; F5/F6 bars start at zero. No invented confidence intervals. F2 uses nested
empirical scenario envelopes (not confidence bands). F3/F4 separate battery power
and stored energy, extending the original three-panel plan to four compact panels.
