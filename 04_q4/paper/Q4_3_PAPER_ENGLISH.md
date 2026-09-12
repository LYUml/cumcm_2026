# Problem 4-3: Rolling Joint-Scenario Purchasing under Fluctuating Prices

> Revised formal version. This section extends Model 4-2 directly and does not
> inherit the independent deterministic implementation in `03_q3`.

## 9.1 Logical connection with Model 4-2

Model 4-2 makes one purchase commitment at 00:00 under joint net-load and price
uncertainty. Problem 4-3 retains this uncertainty representation and physical
controller, but admits new photovoltaic forecasts at 06:00, 12:00 and 18:00.
The natural extension is therefore a rolling multistage controller: construct
twelve paired net-load--price paths, solve the remaining-horizon scenario-tree
LP, execute only the block before the next release, then observe the realised
system and repeat. Model 4-2 is the root problem and Model 4-3 is its
receding-horizon extension [3,4].

## 9.2 Information sets and paired residual scenarios

Let $k\in\{0,6,12,18\}$ be an issue time and $\mathcal H_k$ the remaining
ten-minute intervals. At $k$, the controller knows the new PV forecast, load,
PV and prices strictly before $k$, current SOC $S_k$, and the 00:00 baseline.
It never uses realised values at or after $k$. The point net-load forecast is

$$\widehat N_{d,k,t}=\widehat L_{d,k,t}-\widehat P^{PV}_{d,k,t}.\tag{9.1}$$

For a fully observed historical date $j$, reconstruct the forecasts available
at the same issue time and calculate

$$e^N_{j,k,t}=N^{\rm act}_{j,t}-\widehat N_{j,k,t},\qquad
e^p_{j,k,t}=p^{\rm act}_{j,t}-\widehat p_{j,k,t}.\tag{9.2}$$

The price point forecast inherits the four-week same-weekday model selected in
Q4-2. For $k>0$, its remaining curve is shifted by the median price error over
the already observed six hours, with a six-hour exponential decay. The twelve
scenarios are

$$N^{(s)}_{d,k,t}=\widehat N_{d,k,t}+e^N_{j_s,k,t},\qquad
p^{(s)}_{d,k,t}=\max\{0,\widehat p_{d,k,t}+e^p_{j_s,k,t}\}.\tag{9.3}$$

Dates $j_s$ come from the preceding 56 days, prioritising the same weekday and
then recency. Net-load and price residuals use the same historical date, thus
preserving empirical dependence and intraday shape. This is the paired-residual
principle of Model 4-2 reconstructed at each new information boundary.

## 9.3 Scenario-tree rolling linear program

Let $q^0_t$ be the 00:00 commitment and $q^k_t$ the revision. For $k>0$,

$$q^k_t=q^0_t+u^k_t-v^k_t,\qquad u^k_t,v^k_t\ge0.\tag{9.4}$$

For every scenario $s$,

$$q^k_t+D^{(s)}_t+E^{(s)}_t-C^{(s)}_t-W^{(s)}_t=N^{(s)}_{d,k,t},\tag{9.5}$$

$$S^{(s)}_{t+1}=S^{(s)}_t+0.9C^{(s)}_t-D^{(s)}_t/0.9,\tag{9.6}$$

$$1200\le S^{(s)}_t\le10800,\quad
0\le C^{(s)}_t,D^{(s)}_t\le5000/6,\quad S^{(s)}_{144}\ge3000.\tag{9.7}$$

At 00:00 the Q4-2 objective is

$$\min\ \sum_t\bar p_tq^0_t+4.5\sum_s\pi_s\sum_t p^{(s)}_tE^{(s)}_t
+\varepsilon\sum_s\pi_s\sum_t(C^{(s)}_t+D^{(s)}_t),\tag{9.8}$$

where $\bar p_t=\sum_s\pi_sp^{(s)}_t$ and $\pi_s=1/12$. At an intraday update,

$$\min\ \sum_t\bar p_t(1.5u^k_t-0.5v^k_t)
+4.5\sum_s\pi_s\sum_t p^{(s)}_tE^{(s)}_t
+\varepsilon\sum_s\pi_s\sum_t(C^{(s)}_t+D^{(s)}_t).\tag{9.9}$$

The constant baseline cost is omitted from (9.9). A binary scenario tree is
rebuilt in four-hour stages. Battery actions are equal for scenarios in the
same active node, preventing anticipatory response; purchase is common to all
scenarios because it is committed at the current issue time.

## 9.4 Execution and settlement

Only the next block is locked. Actual net-load deficits are supplied first by
feasible battery discharge and then emergency purchase; surpluses are charged
and then curtailed. The resulting SOC initialises the next problem. Forecast
prices guide decisions but final settlement uses actual Attachment-4 prices:

$$J^{4-3}=\sum_{d,t}p^{\rm act}_{d,t}q^0_{d,t}
+\sum_{d,t}p^{\rm act}_{d,t}(1.5u_{d,t}-0.5v_{d,t})
+\sum_{d,t}5p^{\rm act}_{d,t}E_{d,t}.\tag{9.10}$$

For downward revision, (9.10) equals the actual delivered-energy payment plus
a 50% penalty on the cancelled quantity.

## 9.5 Full-year result

The simulation propagates the stated 6000 kWh SOC causally through January;
reported expenditure covers February 1--December 31.

| Cost component | CNY |
|---|---:|
| 00:00 planned purchase | 14,062,104.71 |
| Intraday adjustment | 32,342.23 |
| Emergency purchase | 51,895.41 |
| **Total** | **14,146,342.35** |

Planned and final ordinary purchases are 21,586,205.23 and 21,026,895.45 kWh.
Emergency energy is 9,523.38 kWh, and executed SOC remains within
1200--10800 kWh over all 334 reported days.

| Date | Planned kWh | Final kWh | Emergency kWh | Total CNY |
|---|---:|---:|---:|---:|
| 2025-03-20 | 71,244.09 | 66,589.71 | 75.98 | 44,135.28 |
| 2025-06-21 | 35,397.11 | 35,435.85 | 0 | 18,037.24 |
| 2025-09-23 | 71,759.98 | 68,119.67 | 0 | 46,166.36 |
| 2025-12-21 | 97,295.35 | 96,108.87 | 0 | 73,555.01 |

## 9.6 Value of additional forecasts

The same forecaster, scenario construction, tree, reserve, controller and
settlement are held fixed; only enabled update times change.

| Updates | Total cost (CNY) | Emergency energy (kWh) |
|---|---:|---:|
| 00:00 only | 14,721,149.47 | 99,656.38 |
| 06:00 | 14,445,073.06 | 49,734.19 |
| 06:00 and 12:00 | 14,201,984.63 | 25,351.65 |
| **06:00, 12:00 and 18:00** | **14,146,342.35** | **9,523.38** |

Every release lowers both expenditure and emergency energy. All three updates
save 574,807.13 CNY (3.905%) and reduce emergency energy by 90.44% relative to
the 00:00-only policy. Hence all three additional forecasts should be used.
This conclusion comes from an ablation within one fixed Q4-2-derived stochastic
controller, rather than from switching between unrelated Q3 and Q4 models.

## References added for Model 4-3

[3] J. Hönen, J. L. Hurink, and B. Zwart, “Dynamic Rolling Horizon-Based Robust
Energy Management for Microgrids Under Uncertainty,” arXiv:2307.05154, 2023.
https://arxiv.org/abs/2307.05154

[4] F. Pacaud, P. Carpentier, J.-P. Chancelier, and M. de Lara, “Optimization of
a domestic microgrid equipped with solar panel and battery: Model Predictive
Control and Stochastic Dual Dynamic Programming approaches,” arXiv:2205.07700,
2022. https://arxiv.org/abs/2205.07700

## Local evidence

| Item | Workspace source |
|---|---|
| Formal rolling scenario-tree model | `../scripts/run_q4_3_stochastic.py` |
| Full-year results and update ablation | `../outputs/q4_3_stochastic/` |
| Official workbook | `../outputs/q4_3_stochastic/result4-3.xlsx` |
| Parent Q4-2 model | `../scripts/run_q4_2_comparison.py` |
