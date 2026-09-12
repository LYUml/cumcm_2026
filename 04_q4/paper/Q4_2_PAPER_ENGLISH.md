# Problem 4-2: Day-Ahead Purchasing under Joint Net-Load and Price Uncertainty

> English manuscript for integration into the full paper. Parts A and B extend the shared assumptions and model preparation. Section 8 is the Problem 4-2 chapter. Part C supplies a short contribution to the shared evaluation chapter. The method preserves the chronology, storage model, empirical net-load scenarios, and physical execution rule of Model 2; only the tariff process and its effect on planning and settlement are extended.

# A. Additions to Assumptions and Explanations

1. **Price information.** The complete price trajectory of the operating day is unknown when the purchase schedule is committed at 00:00. Prices observed before 00:00 may be used for forecasting, whereas prices from the current or future day may not be used by an implementable policy.
2. **Price settlement.** Scheduled and emergency purchases are settled at the realized 10-minute price in Attachment 4. Emergency supply remains priced at five times the contemporaneous normal price. Unused energy has no refund or export revenue.
3. **Joint uncertainty.** Net-load and price uncertainty are represented by complete historical daily residual paths. Residuals selected from the same historical dates are paired, thereby preserving their empirical within-day timing and cross-variable dependence.
4. **Continuity with Model 2.** Storage parameters, the January warm-up, the February--December evaluation period, the strict midnight information boundary, and the causal physical controller are unchanged. This makes the Q2 and Q4-2 results directly comparable as complete operating policies.

# B. Additions to Model Preparation

## B.1 Price notation and realized settlement

Let $p^{\mathrm{act}}_{d,t}$ be the realized normal price, $\widehat p_{d,t}$ its midnight forecast, and $p^{(s)}_{d,t}$ the price in scenario $s$. The remaining symbols follow Model 2. Under fluctuating prices, realized expenditure becomes
$$
J^{4-2}=\sum_{d\in\mathcal D}\sum_t p^{\mathrm{act}}_{d,t}G_{d,t}
+\sum_{d\in\mathcal D}\sum_t5p^{\mathrm{act}}_{d,t}E_{d,t}.
\tag{P2}
$$
The first term prices the midnight commitment at the realized transaction price; the second prices only the deficit left after feasible battery discharge. Forecast and scenario prices affect the decision but are never substituted for realized prices in the final account.

## B.2 Common initialization, chronology, and evaluation period

The simulation starts at 6000 kWh on January 1. January is used for causal forecast warm-up and storage-state propagation, while reported costs cover the 334 days from February 1 to December 31, 2025. As in Model 2, the warm-up gives 10800 kWh at 00:00 on February 1. Stored energy is linked continuously between days.

The source and official-workbook timestamps retain the convention established in Section 6.0: row index 0 represents 00:10--00:20, and index 143 represents 00:00--00:10 on the following civil day. At midnight the new purchase row is committed before the pending final interval of the preceding row is executed. Both price forecasting and net-load scenario construction obey this boundary.

# 8 Model 4-2: Recalculation of Problem 2 under Fluctuating Prices

## 8.1 Extension of the Price Model

### 8.1.1 Causal price-forecast candidates

Price forecasting is evaluated as a decision component rather than as an isolated prediction exercise. Four causal candidates are constructed from information available at midnight:

| Model | Midnight price forecast |
|---|---|
| Seasonal naive | Price trajectory seven days earlier |
| Four-week weekday mean | Mean of the available trajectories at lags 7, 14, 21, and 28 days |
| Ridge ARX | Regularized regression using lag-1, lag-2, lag-7 prices, recent daily means, harmonic time features, and weekday indicators |
| Elastic-net ARX | The same predictors with combined $L_1$ and $L_2$ regularization |

For the transparent four-week model selected below,
$$
\widehat p_{d,t}
=\frac{1}{|\mathcal L_d|}\sum_{\ell\in\mathcal L_d}p^{\mathrm{act}}_{d-\ell,t},
\qquad
\mathcal L_d\subseteq\{7,14,21,28\},
\tag{8.1}
$$
where only available positive lags are retained. The regression models use a rolling window of at most 90 days and are refitted every seven days. Their hyperparameters are chosen by day-blocked expanding validation folds, so every validation block follows its training block.

Prediction error alone does not determine purchasing performance. Storage arbitrage depends strongly on the ordering of prices within a day, while conservative commitments trade scheduled expenditure against fivefold emergency cost. We therefore report mean absolute error (MAE), root mean squared error (RMSE), daily rank correlation, and realized closed-loop expenditure.

### 8.1.2 Paired price and net-load residual paths

Let
$$
e^p_{j,t}=p^{\mathrm{act}}_{j,t}-\widehat p_{j,t}
\tag{8.2}
$$
be the historical price residual. For day $d$, Model 2 first identifies eligible complete residual days within the preceding 56 days, prioritizes the same weekday, fills the remaining positions by recency, and selects twelve dates $j_s$. The price scenarios are
$$
p^{(s)}_{d,t}=\max\{0,\widehat p_{d,t}+e^p_{j_s,t}\},
\qquad s=1,\ldots,12.
\tag{8.3}
$$
The net-load scenario and price scenario with index $s$ use the same historical date $j_s$. Thus each scenario is the paired path
$$
\boldsymbol\xi_d^{(s)}=
\left(\boldsymbol P_d^{N,(s)},\boldsymbol p_d^{(s)}\right),
\qquad \pi_s=\frac1{12}.
\tag{8.4}
$$
Pairing preserves empirical co-movement without imposing a parametric dependence model. Complete paths also preserve ramping, peak duration, and intraday correlation, all of which affect storage decisions. Equal scenario weights remain an empirical approximation rather than calibrated probabilities.

### 8.1.3 Price-aware scenario-tree purchasing model

To isolate the effect of fluctuating prices, the selected Q2 information structure is retained. The twelve scenarios are partitioned through a six-stage, four-hour tree using the observed net-load history. Charging and discharging actions are equal within each active node, as specified by the nonanticipativity constraints in (6.4), while $G_{d,t}$ is common to all scenarios for the whole day.

The price-aware daily problem is
$$
\min\;
\sum_t\left(\sum_s\pi_sp^{(s)}_{d,t}\right)G_{d,t}
+\lambda\sum_s\pi_s\sum_t5p^{(s)}_{d,t}\widetilde E^{(s)}_{d,t}
+\epsilon\sum_s\pi_s\sum_t\left(C^{(s)}_{d,t}+D^{(s)}_{d,t}\right),
\tag{8.5}
$$
subject to the scenario energy balance, storage transition, operating limits, initial state, and terminal reserve in (6.4)--(6.6). The numerical settings are unchanged from Model 2:
$$
\lambda=0.9,\qquad \epsilon=10^{-4},\qquad
S^{(s)}_{d,144}\ge3000\ \mathrm{kWh}.
\tag{8.6}
$$
In the implementation, $5\lambda=4.5$, so the scenario-shortage coefficient is $4.5p^{(s)}_{d,t}$. This is a planning weight; actual emergency energy is still settled at exactly $5p^{\mathrm{act}}_{d,t}$. The formulation is a linear program and is solved with HiGHS [2].

The tree is deliberately constructed from net-load histories rather than jointly reclustered net-load and price histories. This preserves the Q2 information structure and makes the principal experiment an extension by price uncertainty, not a simultaneous redesign of every model component. Joint clustering is examined only as an ablation.

### 8.1.4 Causal execution and realized-price settlement

After committing $G_{d,t}$, the physical controller of (6.7)--(6.9) is replayed on actual net load in chronological order. A surplus is charged subject to battery limits and the remainder is discarded; a deficit is discharged subject to the power and state-of-charge limits and only the remainder becomes emergency purchase. The scenario storage actions are planning surrogates and are not copied into the realized trajectory.

For each physical interval, the actual price from Attachment 4 is then applied through (P2). Hence every candidate price model is evaluated with the same net-load scenarios, initial state, physical feedback rule, and realized trajectory. The perfect-price case repeats the actual daily price path across all twelve scenarios. It is an infeasible-information benchmark, not an implementable policy and not a mathematical lower bound over every possible controller.

## 8.2 Results and Interpretation

### 8.2.1 Price-prediction performance

| Price model | MAE (CNY/kWh) | RMSE (CNY/kWh) | Mean daily rank correlation |
|---|---:|---:|---:|
| Ridge ARX | **0.04160** | **0.05493** | 0.95168 |
| Elastic-net ARX | 0.04168 | 0.05534 | **0.95181** |
| Seasonal naive | 0.04715 | 0.06535 | 0.94600 |
| Four-week weekday mean | 0.04886 | 0.06963 | 0.95172 |

*Table 8. Price-forecast accuracy from February through December 2025. Daily rank correlation is the Pearson correlation between the within-day ranks of predicted and realized prices.*

The regularized ARX models minimize point-prediction error, but this ordering does not carry over to realized operating cost. In particular, the four-week weekday mean has the largest MAE among the four candidates yet gives the lowest total expenditure under the common Q2 controller. Accurate point forecasts and good storage decisions are therefore related but non-equivalent objectives.

### 8.2.2 Closed-loop policy comparison

| Price information used in planning | Scheduled cost | Emergency cost | Total cost | Emergency energy |
|---|---:|---:|---:|---:|
| Perfect daily price benchmark | 13.7661 | 0.7884 | 14.5544 | 124.32 |
| **Four-week weekday mean** | **13.9302** | **0.7234** | **14.6536** | **114.62** |
| Ridge ARX | 13.9422 | 0.7208 | 14.6630 | 113.16 |
| Elastic-net ARX | 13.9427 | 0.7207 | 14.6634 | 113.31 |
| Seasonal naive | 13.9887 | 0.7059 | 14.6946 | 111.74 |

*Table 9. February--December 2025 closed-loop expenditure in million CNY and emergency energy in MWh. The perfect-price row is a hindsight-information benchmark; all other rows are causal.*

The selected four-week weekday-mean policy yields
$$
\begin{aligned}
J_{\mathrm{plan}}&=13\,930\,211.95\ \mathrm{CNY},\\
J_{\mathrm{emg}}&=723\,365.12\ \mathrm{CNY},\\
J^{4-2}&=\boxed{14\,653\,577.06\ \mathrm{CNY}}.
\end{aligned}
\tag{8.7}
$$
Emergency expenditure is 4.94% of the total. The difference from the perfect-price benchmark is CNY 99,146.57, or 0.681% of the benchmark total. This small information regret indicates that the causal forecast retains most of the operational value of knowing the price profile in advance under the tested controller. It does not establish global optimality.

Lower emergency energy does not necessarily imply lower total cost. For example, the seasonal-naive policy buys the least emergency energy among the causal candidates, but its larger scheduled expenditure makes it the most expensive of them. The economically relevant selection criterion is therefore total realized cost rather than emergency volume or forecast MAE alone.

### 8.2.3 Robustness and ablation evidence

We split the reporting period into February--June and July--December and compare model choices without changing the Q2 reference structure. With joint residual prices, net-load tree construction, a 3000 kWh scenario terminal floor, and shortage coefficient $4.5p$, the four-week weekday mean is the lowest-cost price model in both subperiods. This consistency supports its selection over the more complex regressions.

Ablations vary the terminal floor, planning-shortage coefficient, point versus residual-path price uncertainty, and net-load versus joint tree signal. Their rankings reverse between the two subperiods. The full-sample minimum, CNY 14.6479 million, is attained by Ridge ARX with a jointly clustered tree, whereas the holdout minimum, CNY 8.7399 million for July--December, uses the weekday mean with shortage coefficient $4.0p$. These alternatives are not adopted because selecting them after observing the reporting year would mix structural retuning with the intended price-model comparison.

At the reference settings, using a single point-price path instead of paired residual paths raises the weekday-mean full-period cost from CNY 14.6536 million to CNY 14.6550 million. The difference is small but favors carrying complete price uncertainty into the storage-coupled optimization.

### 8.2.4 Feasibility and numerical validation

Across $334\times144=48{,}096$ realized intervals, the selected policy has maximum energy-balance error $1.14\times10^{-13}$ kWh. Stored energy remains in the required 1200--10800 kWh range. There are zero simultaneous charge/discharge intervals, and natural-day state assembly introduces zero linking error. The final workbook contains all 334 purchase rows, 2004 four-hour storage rows, and 430 emergency-purchase records.

The exported purchase trajectory is identical to the saved model trajectory. The maximum daily purchase-total discrepancy caused by decimal rounding is $9.0\times10^{-6}$ kWh; the workbook purchase-cost discrepancy is $1.71\times10^{-7}$ CNY; and the emergency-energy export difference is $3.54\times10^{-6}$ kWh. No formula errors were detected.

### 8.2.5 Required-date results

Table 10 follows the requested purchase-summary format. Interval and daily purchase quantities are in kWh.

| Date | 10:00--10:10 | 12:00--12:10 | 14:00--14:10 | 16:00--16:10 | 18:00--18:10 | 20:00--20:10 | Daily plan | Plan cost (CNY) | Emergency cost (CNY) | Total cost (CNY) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-03-20 | 0.00 | 601.32 | 0.00 | 413.00 | 0.00 | 718.49 | 68,182.96 | 42,766.07 | 1,326.31 | 44,092.38 |
| 2025-06-21 | 0.00 | 0.00 | 0.00 | 134.66 | 432.39 | 0.00 | 36,373.85 | 18,123.67 | 0.00 | 18,123.67 |
| 2025-09-23 | 0.00 | 575.15 | 0.00 | 456.29 | 0.00 | 759.11 | 71,659.17 | 46,350.32 | 0.00 | 46,350.32 |
| 2025-12-21 | 0.00 | 1,010.03 | 0.00 | 818.97 | 727.69 | 0.00 | 97,774.81 | 74,802.13 | 144.24 | 74,946.37 |

*Table 10. Selected-day purchase results under fluctuating prices.*

The corresponding storage and emergency-purchase details are retained in `result4-2.xlsx`. Their six four-hour blocks are assembled on the natural-day timeline, crossing adjacent official purchase rows where required, exactly as in Model 2.

# C. Contribution to Model Evaluation and Further Discussion

The Q4-2 extension separates three objects that are easily conflated: predicted prices used to construct decisions, scenario prices used to represent uncertainty, and realized prices used for settlement. Paired historical residual paths preserve temporal and cross-variable dependence, while the unchanged Q2 controller isolates the operational effect of price information. The results also show why price models should be judged by closed-loop expenditure: the lowest forecast error, the least emergency energy, and the least total cost are achieved by different candidates.

The main limitations are the short one-year price history, equal-weight empirical scenarios, absence of exogenous price drivers, and selection of the price model on the supplied reporting year. The perfect-price result is only a benchmark under the same surrogate formulation and feedback controller. More years of data would permit a genuinely independent test and probabilistic calibration; distributionally robust or risk-averse formulations could then be assessed without retuning on the reporting sample.

# Appendix: Reproducibility and Editorial Notes

## References for integration into the full bibliography

[1] Birge, J. R., and Louveaux, F. *Introduction to Stochastic Programming*. 2nd ed., Springer, 2011. [Publisher record](https://doi.org/10.1007/978-1-4614-0237-4).

[2] Huangfu, Q., and Hall, J. A. J. “Parallelizing the dual revised simplex method.” *Mathematical Programming Computation*, 10, 119--142, 2018. [DOI](https://doi.org/10.1007/s12532-017-0130-5).

## Local evidence

| Item | Workspace source |
|---|---|
| Price forecasts, paired scenarios, joint planning model, and replay | `../scripts/run_q4_2_comparison.py` |
| Primary forecast and policy comparison | `../outputs/q4_2_comparison/` |
| Robustness and ablation comparison | `../outputs/q4_2_robustness/` |
| Final workbook and model/export validation | `../outputs/final/` |
| Inherited net-load model, chronology, and controller | `../../02_q2/src/`; `../../02_q2/scripts/run_final.py` |

The manuscript reports full-precision saved outputs rounded only for presentation. `result4-2.xlsx` is the complete deliverable. The chosen price model is the stable winner under the fixed Q2 reference structure, but because candidate comparison uses the supplied 2025 reporting year, it should be described as a backtest selection rather than an independent out-of-sample generalization result.
