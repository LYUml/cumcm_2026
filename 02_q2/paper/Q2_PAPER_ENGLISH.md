# Problem 2: Day-Ahead Purchasing under Net-Load Uncertainty

> English manuscript for integration into the full paper. Parts A and B belong in the shared assumptions and model preparation. Section 6 is the Problem 2 chapter. Part C supplies a short contribution to the shared evaluation chapter. Editorial notes are excluded from the manuscript.

# A. Additions to Assumptions and Explanations

1. **Information and commitment.** The purchase schedule is fixed at 00:00 each day. Current load and photovoltaic (PV) output are measurable for balancing within each 10-minute interval. Future realized values are unavailable to the controller.
2. **Settlement.** Scheduled purchases are paid for in full. Emergency purchases cover the remaining load deficit at five times the normal tariff and cannot charge the battery. Unused energy has no refund or export revenue.
3. **Storage and time resolution.** Storage efficiencies and operating limits remain constant; self-discharge and degradation are neglected. Power is represented by its interval-average value, with $\Delta t=1/6$ h. Stored energy is carried continuously between days.

Storage parameters and initialization are specified below rather than treated as additional assumptions.

# B. Additions to Model Preparation

## B.1 Variables and settlement

Let $d$ index days and $t\in\{1,\ldots,144\}$ index 10-minute intervals. Net-load power is
$$
P^N_{d,t}=P^L_{d,t}-P^{PV}_{d,t},
$$
where load and PV power are measured in kW. Negative net load represents a local generation surplus. Hats and superscripts $\mathrm{act}$ and $(s)$ distinguish forecasts, realizations, and scenarios.

| Symbol | Definition | Unit |
|---|---|---|
| $p_t$ | Known normal purchase tariff | CNY/kWh |
| $G_{d,t}$ | Purchase committed at 00:00 | kWh |
| $C_{d,t},D_{d,t}$ | Charging and discharging energy on the microgrid side | kWh |
| $S$ | Stored energy at a physical interval boundary | kWh |
| $E_{d,t},W_{d,t}$ | Actual emergency purchase and unused surplus | kWh |
| $\widetilde E^{(s)}_{d,t}$ | Scenario shortage used in planning | kWh |

The storage parameters inherited from Model 1 are
$$
\eta_c=\eta_d=0.9,\quad S_{\min}=1200,\quad S_{\max}=10800,\quad
\bar C=\bar D=5000\Delta t=\frac{2500}{3}\ \mathrm{kWh}.
$$
For any realized operating trajectory, expenditure is
$$
J=\sum_{d\in\mathcal D}\sum_t p_tG_{d,t}
+\sum_{d\in\mathcal D}\sum_t5p_tE_{d,t}.
\tag{P1}
$$
The first term depends on the committed schedule; the second is recomputed from actual operation. Scenario shortages do not enter settlement directly.

## B.2 Initialization and evaluation period

The simulation starts with 6000 kWh on January 1, 2025. With no preceding observation, the January 1 scheduled purchase is zero. On subsequent January days, the schedule is the nonnegative part of the previous row's net-load curve, converted to energy. Because that row's last interval has not ended at midnight, its final slot is backed off to the most recent complete row (or zero on 2 January). The causal controller in Section 6.1.4 advances storage throughout this warm-up, producing 10800 kWh at 00:00 on February 1.

All comparisons use this common February initial state and the 334 days from February 1 to December 31, 2025, matching the dates required for result2.xlsx in Appendix 2 of Problem C. January costs are excluded. The reported amount is an eleven-month evaluation cost, not a twelve-month operating bill.

# 6 Model 2: Solution to Problem 2

## 6.0 Time convention and data alignment

The statement does not specify whether the source timestamps are samples or interval representatives. Attachments 1 and 2 use $0{:}10,0{:}20,\ldots,0{:}00{+}1$, while the official workbook uses $0{:}10$–$0{:}20,\ldots,0{:}00$–$0{:}10{+}1$. We adopt the smallest complete assumption consistent with all 144 official columns: each source label is the left endpoint of its ten-minute interval. Thus array index 0 is $0{:}10$–$0{:}20$ and index 143 is $0{:}00$–$0{:}10$ on the following date. A right-end interpretation would leave the final official interval without the unavailable 1 January 2026 observation.

A row dated $d$ therefore covers 00:10 on $d$ through 00:10 on $d+1$. Civil-day storage summaries cross rows: 00:00–00:10 comes from the preceding row, followed by indices 0–142 of row $d$. The day-$d$ plan is fixed at civil midnight before the preceding row's final interval is replayed, so it cannot use the realized 00:10 state. The full mapping is included with the reproducibility files.

## 6.1 Extension of the Basic Model

### 6.1.1 Decision structure

Problem 2 replaces the deterministic input curves of Model 1 with uncertain daily load and PV generation. The microgrid must commit to purchases before observing either curve. Insufficient purchases expose it to expensive emergency supply, while excessive purchases create unused energy. Consequently, forecast accuracy alone is insufficient: the relevant outcome is expenditure after the purchase schedule has been executed.

We construct a central forecast, represent its uncertainty through historical daily residuals, and solve a scenario-based purchasing problem. Nodewise nonanticipativity constraints limit how early the planning model can adapt its storage actions to different scenarios. Only the purchase schedule is committed; actual storage operation follows a causal feedback rule.

### 6.1.2 Central forecast and daily residual scenarios

Load and PV generation have different temporal structures. We use load from the same weekday one week earlier and median PV output among observations available at midnight. Let $\mathcal A_{d,t}$ contain the preceding seven row indices, except that $d-1$ is excluded when $t=144$ because its 00:00--00:10 interval is still pending. Then
$$
\widehat P^{N,0}_{d,t}
=P^L_{d-7,t}
-\operatorname{median}\{P^{PV}_{j,t}:j\in\mathcal A_{d,t}\}.
\tag{6.1}
$$
The weekly lag represents recurring demand patterns, while the median estimates recent PV levels robustly. This parsimonious baseline supplies the center of the scenario distribution; it does not explicitly forecast the next day's weather.

Storage responds to the duration and timing of a deficit as well as its magnitude. We therefore select complete historical residual paths rather than sample each interval independently. For historical day $j$,
$$
r_{j,t}=P^{N,\mathrm{act}}_{j,t}-\widehat P^{N,0}_{j,t}.
\tag{6.2}
$$
Each historical forecast is reconstructed using observations preceding $j$. From the previous 56 days, subject to availability of the seven-day lag, we select same-weekday residuals first and fill the remaining places with the most recent eligible days. Only complete residual rows through $d-2$ are eligible; row $d-1$ is not patched or partially reused. Twelve selected paths give
$$
P^{N,(s)}_{d,t}=\widehat P^{N,0}_{d,t}+r_{j_s,t},
\qquad s=1,\ldots,12,\qquad \pi_s=\frac1{12}.
\tag{6.3}
$$
At the beginning of the evaluation period, only available eligible history is used. These trajectories represent empirical uncertainty around the current forecast. Equal weights are a modeling approximation, not calibrated confidence probabilities.

### 6.1.3 Scenario-tree purchasing model

A scenario is a possible daily trajectory, not information known at 00:00. We divide the day into six four-hour stages. All scenarios share the initial node. At each subsequent boundary, scenarios within each parent node are split by two-cluster K-means using their net-load trajectories over the preceding stage. Singleton nodes remain unchanged. These nested partitions contain at most twelve nodes.

Let $\mathcal T_k=\{24(k-1)+1,\ldots,24k\}$ and let $s\sim_k s'$ mean that two scenarios share a stage-$k$ node. We impose
$$
C^{(s)}_{d,t}=C^{(s')}_{d,t},\qquad
D^{(s)}_{d,t}=D^{(s')}_{d,t},
\quad t\in\mathcal T_k,\quad s\sim_k s'.
\tag{6.4}
$$
Storage actions can differ only after the corresponding histories have been separated by the tree. These constraints enforce nonanticipativity on a coarsened information structure, following the multistage stochastic-programming framework [1]. The purchase schedule $G_{d,t}$ remains identical across all scenarios throughout the day.

The daily planning problem is
$$
\min\
\sum_t p_tG_{d,t}
+\lambda\sum_s\pi_s\sum_t5p_t\widetilde E^{(s)}_{d,t}
+\epsilon\sum_s\pi_s\sum_t(C^{(s)}_{d,t}+D^{(s)}_{d,t}),
\tag{6.5}
$$
subject to (6.4) and, for every scenario and interval,
$$
\begin{aligned}
G_{d,t}+D^{(s)}_{d,t}+\widetilde E^{(s)}_{d,t}
&=\Delta tP^{N,(s)}_{d,t}+C^{(s)}_{d,t}+W^{(s)}_{d,t},\\
S^{(s)}_{d,t}
&=S^{(s)}_{d,t-1}+\eta_cC^{(s)}_{d,t}-D^{(s)}_{d,t}/\eta_d,\\
S_{\min}\le S^{(s)}_{d,t}&\le S_{\max},\\
0\le C^{(s)}_{d,t}&\le\bar C,\qquad 0\le D^{(s)}_{d,t}\le\bar D,\\
G_{d,t},\widetilde E^{(s)}_{d,t},W^{(s)}_{d,t}&\ge0,\\
S^{(s)}_{d,0}&=S_{d,0},\qquad S^{(s)}_{d,144}\ge S_{\mathrm{res}}.
\end{aligned}
\tag{6.6}
$$
Here, $S_{d,0}$ is the actual stored energy observed at civil midnight when row $d$ is committed. Because the official row begins at 00:10, the surrogate omits the still-pending 00:00–00:10 interval belonging to row $d-1$. It therefore uses the midnight state as an approximation to the state at the start of its first modeled interval. The terminal reserve $S_{\mathrm{res}}=3000$ kWh is imposed at the end of the surrogate row, 00:10 on the following date; it discourages excessive planned depletion but is not a civil-midnight operating constraint.

The weight $\lambda$ calibrates how strongly the planner penalizes simulated shortages: $\lambda=1$ uses the actual emergency tariff, while larger weights encourage more conservative purchases. Storage capacity, power, efficiencies, the 1 January initial state, and the fivefold emergency tariff are problem data. The 12 scenarios, 56-day window, four-hour stages, 3000 kWh planning reserve, and $\epsilon=10^{-4}$ CNY/kWh are fixed modeling choices. The value $\lambda=0.9$ was selected by an in-sample backtest. It compensates empirically for scenario and execution approximations; it is not a change to the settlement tariff or independently validated tuning.

The objective and constraints form a linear program solved with HiGHS [2]. Shortage and surplus are scenario balancing variables and may differ within a node. This planning model approximates subsequent operation: it does not explicitly prohibit emergency-assisted charging or simultaneous charge and discharge in the surrogate trajectories, and its terminal reserve is not guaranteed on every actual path. The physical controller below enforces the operating rules.

### 6.1.4 Causal execution and settlement

At interval $t$, define
$$
N^{\mathrm{act}}_{d,t}=\Delta tP^{N,\mathrm{act}}_{d,t},
\qquad M_{d,t}=G_{d,t}-N^{\mathrm{act}}_{d,t}.
$$
For $M_{d,t}\ge0$, the battery absorbs the available surplus:
$$
C_{d,t}=\min\left\{M_{d,t},\bar C,
\frac{S_{\max}-S_{d,t-1}}{\eta_c}\right\},\quad
D_{d,t}=E_{d,t}=0,\quad W_{d,t}=M_{d,t}-C_{d,t}.
\tag{6.7}
$$
For $M_{d,t}<0$, it supplies as much of the deficit as its limits allow:
$$
D_{d,t}=\min\left\{-M_{d,t},\bar D,
\eta_d(S_{d,t-1}-S_{\min})\right\},\quad
C_{d,t}=W_{d,t}=0,\quad E_{d,t}=-M_{d,t}-D_{d,t}.
\tag{6.8}
$$
For every physically executed interval $i$, the realized storage state satisfies
$$
S_i^{+}=S_i^{-}+\eta_cC_i-D_i/\eta_d,
\qquad S_{i+1}^{-}=S_i^{+}.
\tag{6.9}
$$
Physical execution follows chronological time rather than spreadsheet row order. At midnight on date $d$, row $d$ is first committed using the current state. The already committed last interval of row $d-1$ is then executed over 00:00–00:10, followed by intervals 1–143 of row $d$ over 00:10–24:00. This feedback rule uses only the current interval measurement and stored energy. It prevents simultaneous charging and discharging, confines emergency purchases to the remaining deficit, and respects storage limits. It is a feasible operating rule, not a claim of optimal real-time control. Equation (P1) settles each physical interval using the purchase row to which the official template assigns it.

The daily procedure is: observe the civil-midnight state; generate twelve scenarios from complete rows through $d-2$ and the available slots of row $d-1$; solve (6.5)–(6.6); commit row $d$; execute the pending final interval of row $d-1$ and then the 143 row-$d$ intervals ending by midnight; and repeat. Row $d$'s final interval is executed after the next midnight decision. Both the state transition and the forecast builder therefore respect the same midnight information boundary.

## 6.2 Results and Interpretation

### 6.2.1 Comparison definitions and evidence status

We recomputed six complete purchasing policies using the same dates, initial stored energy, physical controller, settlement rule, and strict midnight information boundary. Point-forecast policies use
$$
\widehat P^{N,\tau}_{d,t}
=b_{d,t}+Q_\tau\{P^{N,\mathrm{act}}_{j,t}-b_{j,t}:j\in\mathcal H_d\},
\tag{6.10}
$$
where $\mathcal H_d$ contains eligible days in the preceding 56-day window. The direct baseline has $b_{d,t}=P^N_{d-7,t}$; the separate baseline uses (6.1). Each point forecast enters the deterministic purchasing LP.

For one interval without storage or salvage value, underage and overage costs are $4p_t$ and $p_t$, respectively. The critical quantile is $4p_t/(4p_t+p_t)=0.8$. This motivates the cost-sensitive $Q_{0.8}$ benchmark, without implying optimality for the storage-coupled problem.

| Policy | Forecast or scenarios | Planning storage structure |
|---|---|---|
| Separate $Q_{0.5}$ | Separate baseline plus median residual | Deterministic; daily cyclic storage |
| Direct $Q_{0.8}$ | Weekly net-load baseline plus 0.8 residual quantile | Deterministic; daily cyclic storage |
| Separate $Q_{0.8}$ | Separate baseline plus 0.8 residual quantile | Deterministic; daily cyclic storage |
| Fixed-action scenarios | Twelve daily residual paths around weekly net load | Actions shared across scenarios; daily cyclic storage |
| Four-hour tree | Twelve separate-baseline residual paths | Nodewise actions; 3000 kWh scenario terminal floor |
| Two-stage relaxation | Same type of residual paths as the tree | Unrestricted scenario-specific actions; 3000 kWh floor |

Daily cyclic storage means that the planned final state equals that day's planning initial state. All policies use the same feedback rule, whose realized final state is free within physical limits. Because their forecast, planning structure, terminal policy, and tuned settings differ, this is a complete-policy comparison rather than an isolated estimate of the value of nonanticipativity.

### 6.2.2 Overall expenditure

Table 2 reports the authoritative corrected backtest, rounded independently to four decimal places in millions of CNY.

| Policy | Day-ahead cost | Emergency cost | Total cost |
|---|---:|---:|---:|
| **Four-hour tree (selected, strict midnight availability)** | **13.1631** | **0.7302** | **13.8932** |

*Table 2. Authoritative February–December 2025 expenditure, million CNY.*

The reported objective contains only paid scheduled energy and realized emergency energy; unused energy receives no credit, and final inventory receives no salvage value. Relative to the legacy implementation, strict enforcement of the midnight information boundary raises the selected policy's total expenditure by CNY 107,318.96 (0.7785%).

The selected configuration yields
$$
\begin{aligned}
J_{\mathrm{plan}}&=13\,163\,054.77\ \mathrm{CNY},\\
J_{\mathrm{emg}}&=730\,154.55\ \mathrm{CNY},\\
J&=\boxed{13\,893\,209.32\ \mathrm{CNY}}.
\end{aligned}
\tag{6.11}
$$
Emergency expenditure accounts for 5.26% of the total. This is the selected nonanticipative planning configuration among the tested settings, not a certified minimum over all causal policies.

### 6.2.3 Chronology correction

![Chronology correction comparison](../outputs/figures/q2_cost_chronology.png)

*Figure 1. Legacy and strictly causal realized expenditure for the selected four-hour-tree configuration. The correction affects both the state transition and the measurements available to forecasting at midnight; it does not change the tariff or reported units.*

The old run used the state after the 00:00–00:10 interval when preparing the plan nominally issued at 00:00. An intermediate revision fixed that ordering but still allowed forecasting to read the pending interval as the last cell of row $d-1$. The final implementation excludes that measurement from the recent PV statistic, residual candidates, and January persistence rule. We retain the tree as the principal model because its surrogate storage decisions respect the specified nodewise information structure, not because of an assumed cost advantage.

### 6.2.4 Recomputed policy comparison and information constraints

![Recomputed policy comparison](../outputs/figures/q2_model_comparison.png)

| Policy | Day-ahead cost | Emergency cost | Total cost |
|---|---:|---:|---:|
| **Four-hour tree (selected)** | **13.1631** | **0.7302** | **13.8932** |
| Two-stage relaxation | 12.7122 | 1.3822 | 14.0944 |
| Separate $Q_{0.8}$ | 13.4808 | 0.7242 | 14.2050 |
| Fixed-action scenarios | 13.8222 | 0.5594 | 14.3815 |
| Direct $Q_{0.8}$ | 13.6943 | 0.7876 | 14.4819 |
| Separate $Q_{0.5}$ | 12.1866 | 3.2575 | 15.4441 |

*Table 3 and Figure 2. Complete-policy comparison under the common strict chronology, million CNY. The selected row remains bold even though selection is based on the tree's information structure rather than hindsight cost alone.*

At matched scenario construction, reserve, penalty, and execution settings, the two-stage relaxation costs CNY 14.0944 million and the four-hour tree costs CNY 13.8932 million in realized feedback replay. This is mechanism evidence only: relaxing surrogate information constraints cannot worsen the surrogate objective, but its committed schedule can perform differently under a distinct feedback controller. The relaxation's internal trajectory violating nodewise information constraints does not make its purchase row physically unexecutable.

### 6.2.5 Sensitivity

With the shortage multiplier fixed at 4.5 and the scenario terminal floor fixed at 3000 kWh, the archived legacy run increases from CNY 13.7859 million with four-hour stages to CNY 13.8951 million with two-hour stages. The legacy four-hour penalty grid gives CNY 13.7874, 13.7859, and 13.7917 million at multipliers 4.0, 4.5, and 5.5. These results show local in-sample stability only. Comparisons that change the forecast, terminal condition, and penalty together remain complete-policy comparisons and cannot attribute the whole difference to nonanticipativity.

### 6.2.6 Execution validation and cases

Across 48,096 realized intervals, the corrected run has maximum energy-balance residual $1.14\times10^{-13}$ kWh and zero inter-row state-linking error. Stored energy remains within 1200–10800 kWh, with no simultaneous charging/discharging and no emergency purchase during actual charging. The actual civil-midnight state is below 3000 kWh on 74 days. Hence 3000 kWh is a scenario-planning reserve, not an actual daily hard constraint.

The surrogate has no simultaneous charge/discharge, but it has 15,200 scenario intervals with emergency purchase and charging together. Replaying every scenario with the feedback rule yields 478 scenario-day terminal states below 3000 kWh. The maximum planning-versus-feedback terminal-state gap is 5392.32 kWh, and the maximum daily internal-cost gap is CNY 21,650.08. The method is therefore an approximate purchase-decision method, not a strict optimum for the executed closed loop.

### 6.2.7 Information Availability and Scope of Validation

The causality suite perturbs (i) all rows from day $d$ onward, (ii) specifically row $d-1$ slot 144, and (iii) the latter half of the realized control day. In all cases, earlier scenarios, committed purchases, or controls remain bitwise unchanged as applicable. This directly covers the pending-ten-minute defect that the earlier prefix test missed. Thus the final reported run no longer carries the earlier known leakage limitation. The source timestamp semantics remain an explicit modeling assumption, and settings were selected after comparisons on the same evaluation period; the results establish historical feasibility and expenditure rather than independently validated generalization.

### 6.2.8 Representative daily operation

![Representative daily purchasing and storage operation](../outputs/figures/q2_representative_day_corrected.png)

*Figure 3. Realized operation of the selected four-hour tree policy on the day whose total cost is closest to the median of the 334 daily costs; the earliest date breaks a tie. The panels show supply, signed battery action, and stored energy. The selection rule uses realized costs only to choose an illustration after simulation and does not influence purchase decisions.*

The selected date is May 1, 2025, with total expenditure of CNY 44,485.23 and 1658.70 kWh of emergency purchases. It is only the closest observed daily cost to the annual median, not an automatically “typical” operating day. The trajectory shows substantial residual shortage after stored energy is depleted toward its lower bound, while committed surpluses in other intervals recharge the store. The committed schedule remains fixed throughout the day.

### 6.2.9 Required-date results

| Date | 10:00–10:10 | 12:00–12:10 | 14:00–14:10 | 16:00–16:10 | 18:00–18:10 | 20:00–20:10 | Daily plan (kWh) | Plan cost (CNY) | Emergency cost (CNY) | Total cost (CNY) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-03-20 | 0.00 | 601.32 | 0.00 | 384.07 | 715.50 | 0.00 | 68,432.21 | 41,755.67 | 1,385.89 | 43,141.56 |
| 2025-06-21 | 0.00 | 0.00 | 0.00 | 134.66 | 388.23 | 0.00 | 36,123.17 | 20,770.51 | 0.00 | 20,770.51 |
| 2025-09-23 | 0.00 | 575.15 | 0.00 | 406.83 | 805.93 | 17.12 | 71,337.35 | 44,207.16 | 0.00 | 44,207.16 |
| 2025-12-21 | 0.00 | 1,010.03 | 0.00 | 818.97 | 727.69 | 0.00 | 98,611.43 | 63,689.25 | 119.15 | 63,808.40 |

Table 4 reports natural-day storage operation. Each interval cell is charge/discharge energy in kWh.

| Date | 00:00–04:00 | 04:00–08:00 | 08:00–12:00 | 12:00–16:00 | 16:00–20:00 | 20:00–24:00 | $S(00{:}00)$ | $S(24{:}00)$ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-03-20 | 6,887.44 / 174.58 | 1,503.29 / 3,933.84 | 5,212.99 / 3,265.56 | 3,771.98 / 453.51 | 200.76 / 5,092.72 | 2,258.14 / 3,607.67 | 3,638.20 | 3,125.04 |
| 2025-06-21 | 788.96 / 142.69 | 747.17 / 1,849.25 | 8,078.69 / 0.00 | 0.00 / 0.00 | 139.46 / 4,918.06 | 2,818.74 / 3,123.44 | 4,359.93 | 4,527.37 |
| 2025-09-23 | 7,758.21 / 14.23 | 1,220.79 / 5,545.36 | 5,133.51 / 2,387.94 | 5,009.48 / 454.71 | 266.25 / 4,879.17 | 2,324.99 / 3,986.91 | 2,926.03 | 3,280.91 |
| 2025-12-21 | 7,143.08 / 164.53 | 2,373.79 / 767.41 | 5,089.81 / 7,327.91 | 6,806.28 / 2,307.92 | 18.80 / 4,772.36 | 2,135.09 / 3,662.91 | 3,270.30 | 3,365.97 |

*Table 4. Charge/discharge energy and civil-midnight storage, kWh. The six blocks are assembled across adjacent official purchase rows where required.*

Emergency purchases occur on 20 March at 20:40–20:50 (145.47 kWh) and 21:30–22:00 (78.87 kWh), and on 21 December at 08:00–08:10 (20.51 kWh); the other two dates have none. Full-precision values are retained in `../outputs/specified_dates_storage.csv` and `../outputs/specified_dates_emergency.csv`. These interval labels follow the corrected official-template mapping.

# C. Contribution to Model Evaluation and Further Discussion

The framework separates advance commitments from realized operation and uses a common physical simulator and settlement rule. Complete daily residual paths retain temporal dependence relevant to storage, while nodewise constraints limit premature scenario adaptation. This provides an interpretable connection between uncertainty and purchasing decisions.

The principal limitations are the finite historical scenario set, the absence of weather predictors, and the difference between surrogate storage optimization and actual feedback. A fixed terminal reserve only approximates future storage value. Parameters selected on the evaluation period require independent testing before claims of generalization. Subsequent rolling optimization can be evaluated as an extension of the same execution and settlement framework.

# Appendix: Reproducibility and editorial notes

## References for integration into the full bibliography

[1] Birge, J. R., and Louveaux, F. *Introduction to Stochastic Programming*. 2nd ed., Springer, 2011. [Publisher record](https://doi.org/10.1007/978-1-4614-0237-4).

[2] Huangfu, Q., and Hall, J. A. J. “Parallelizing the dual revised simplex method.” *Mathematical Programming Computation*, 10, 119–142, 2018. [DOI](https://doi.org/10.1007/s12532-017-0130-5). This is the citation recommended by the [HiGHS project](https://highs.dev/); it does not specify which algorithm the default solver selected for each run.

## Local evidence

This appendix supports integration and is excluded from the main Problem 2 chapter.

| Item | Workspace source |
|---|---|
| Model and scenario construction | `../src/q2_model.py`; `../src/q2_near_optimal.py` |
| Final costs, daily results and validation | `../outputs/` |
| Final workbook | `../outputs/result2.xlsx` |
| Full numerical and planning trajectories | `../outputs/selected_policy_numeric_trace.npz` |
| Recomputed six-policy comparison and traces | `../outputs/model_comparison/` |
| Time convention | `../outputs/time_mapping.csv` |
| Legacy comparisons retained for audit | `../archive/legacy_snapshot.zip` |
| Recalculation and figure generation | `../scripts/` |

Final figures are supplied as 300-dpi PNG previews and vector PDFs in `../outputs/`. Use the PDF versions for typesetting. Saved legacy sensitivity runs remain in `../archive/legacy_snapshot.zip` and are clearly separated from corrected final outputs. The midnight-availability rule is implemented centrally in `../src/q2_availability.py`.

K-means uses random_state=0 and n_init=20. The probability-weighted throughput penalty matches the implementation coefficient $10^{-4}/12$ per scenario.

The previously quoted perfect-information value of CNY 12,226,852.42 is omitted from the main results because a saved formulation and reproducible output for that computation were not located during this revision. Before restoring it, save its optimization script, matched initial and terminal conditions, solver status and objective. The selected final state satisfies a 3000 kWh terminal reserve; that alone does not verify all lower-bound conditions.

This English manuscript supersedes earlier wording that attributes the entire 0.25% difference to nonanticipativity. Superseded drafts are retained only inside the legacy archive. Merge Parts A–C into their corresponding chapters and update numbering globally. Verified methodological references should be integrated with the full-paper bibliography.
