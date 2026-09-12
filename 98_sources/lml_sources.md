# LML Sources：按问题与方法整理

本文件只保留通用方法、论文和工具来源，不收录 CUMCM2026 题面仓库或直接竞赛解题仓库。每条来源后注明建议使用位置。

## Q2：全年仿真、净负荷预测与不确定性建模

### 预测误差、概率预测与分位数策略

- [arXiv:1801.06479](https://arxiv.org/abs/1801.06479) — 概率预测/预测不确定性方向。对应 Q2 的净负荷预测误差、条件分位数和保守购电策略。
- [arXiv:2011.05314](https://arxiv.org/abs/2011.05314) — 能源系统中的预测与不确定性方法。对应 Q2 的预测误差校准、场景或分位数构造。
- [EMHASS](https://github.com/davidusb-geek/emhass) — 家庭能源管理和储能调度。对应 Q2 的全年逐日仿真器、预测输入、储能调度和费用比较。
- [EMHASS 文档](https://emhass.readthedocs.io/en/latest/emhass.html) — 对应 Q2 的预测—优化—执行流程参考。

### 随机优化与场景方法

- [PyPSA-stochUC](https://github.com/PPGS-Tools/PyPSA-stochUC) — 随机、多阶段电力系统优化。对应 Q2 的场景 LP/随机规划备选方案和消融对比。
- [EMS-RL-DRO](https://github.com/dan-mim/EMS-RL-DRO) — 强化学习与分布鲁棒优化能源管理。对应 Q2 的进阶风险敏感对照；不建议作为当前主模型。

## Q3：预报更新、滚动优化与 MPC

### 滚动时域与随机模型预测控制

- [SMPC-for-Renewable-Energy-Microgrid](https://github.com/plandrem/SMPC-for-Renewable-Energy-Microgrid) — 光伏、储能、负荷和外部电网的随机模型预测控制。对应 Q3 的“新预报 → 重算剩余时域 → 只执行当前区间 → 再次更新”循环。
- [pv-bess-optimizer](https://github.com/lamproskonstantellos/pv-bess-optimizer) — 光伏储能优化、日前计划、日内再调度、滚动时域和不确定性分析。对应 Q3 的计划—调整—实际执行架构、perfect-foresight 下界和 rolling-horizon 评价。
- [FlexMeasures](https://github.com/FlexMeasures/flexmeasures) — 时间序列能源灵活性调度平台。对应 Q3 的预测版本、计划版本、实际购电量和实际 SOC 记录设计。
- [FlexMeasures 文档](https://github.com/FlexMeasures/flexmeasures/blob/main/documentation/index.rst) — 对应 Q3 的数据字段和调度工作流参考。

### 场景控制与风险扩展

- [arXiv:2502.04935](https://arxiv.org/abs/2502.04935) — 微网/能源调度中的不确定性与随机控制方向。对应 Q3 的多场景预测、风险约束或随机 MPC 扩展。
- [arXiv:2504.00685](https://arxiv.org/abs/2504.00685) — 微网随机控制/优化方向。对应 Q3 的预测更新、场景化滚动调度和风险成本扩展。

## Q4：波动电价、价格预测与统一调度扩展

- [pv-bess-optimizer](https://github.com/lamproskonstantellos/pv-bess-optimizer) — 分时价格套利和储能调度。对应 Q4 的波动电价、价格已知下界与因果价格预测策略比较。
- [arXiv:2011.05314](https://arxiv.org/abs/2011.05314) — 可作为价格预测和能源预测不确定性的方法参考，对应 Q4 的价格误差、价格场景和敏感性分析。
- [FlexMeasures](https://github.com/FlexMeasures/flexmeasures) — 灵活性与电价驱动调度。对应 Q4 的价格信号、储能套利和多时段调度接口。
- [arXiv:2502.04935](https://arxiv.org/abs/2502.04935) — 对应 Q4 的价格与可再生能源联合不确定性扩展。

## 跨 Q1–Q4：储能调度与求解器实现

- [HiGHS](https://highs.dev/) — LP/MILP 求解器。对应 Q1 的确定性 LP，以及 Q2–Q4 的场景 LP、滚动 LP/MILP 和统一求解内核。
- [NREL HOPP](https://github.com/NREL/HOPP) — 可再生能源系统建模与优化工具。对应光伏—储能系统建模扩展参考，不作为当前主框架。
- [PowerGridModel](https://github.com/PowerGridModel/power-grid-model) — 电网计算工具。对应 Q4 或论文展望中的潮流扩展；当前不纳入主模型。

## 项目文件中已有的基础参考

- [DOI: 10.1007/978-1-4614-0237-4](https://doi.org/10.1007/978-1-4614-0237-4)
- [DOI: 10.1007/s12532-017-0130-5](https://doi.org/10.1007/s12532-017-0130-5)

## 使用说明

- Q2：预测 → 误差/条件分位数 → 全年逐日仿真 → 费用结算。
- Q3：新预报 → 滚动 MPC/随机控制 → 只执行当前区间 → 比较调整费与紧急购电费。
- Q4：沿用 Q2/Q3 调度框架，引入波动电价，并区分完全信息下界与因果价格预测策略。
- GitHub 项目主要用于程序结构和实验设计；arXiv/DOI 主要用于论文方法依据。正式写作前请核对题名、作者、年份和具体结论。
