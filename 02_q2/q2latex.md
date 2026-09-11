% CUMCM 2026 English LaTeX Template with the original top border retained
% IMPORTANT: Compile with XeLaTeX (not pdfLaTeX), because the border uses CJK fonts.

\documentclass[UTF8,a4paper,zihao=-4]{ctexart}

% ---------- Page layout ----------
\usepackage[a4paper,top=2.5cm,bottom=2.5cm,left=2.5cm,right=2.5cm]{geometry}
\usepackage{setspace}
\usepackage{microtype}
\setstretch{1.15}
\setlength{\parindent}{2em}
\setlength{\parskip}{0.35em}

% ---------- Fonts ----------
% Latin Modern is used for English text; ctex provides the CJK font set.

% ---------- Mathematics ----------
\usepackage{amsmath,amssymb,mathtools}
\usepackage{bm}
\numberwithin{equation}{section}

% ---------- Tables and figures ----------
\usepackage{array}
\usepackage{multirow}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{longtable}
\usepackage{graphicx}
\usepackage{float}
\usepackage{placeins}
\usepackage{subcaption}
\usepackage{siunitx}
\renewcommand{\arraystretch}{1}

% ---------- Border / drawing ----------
\usepackage{tikz}
\usepackage{xcolor}

% ---------- Lists, algorithms, code ----------
\usepackage{enumitem}
\usepackage{algorithm}
\usepackage{algpseudocode}
\usepackage{listings}

\lstset{
  basicstyle=\ttfamily\small,
  numbers=left,
  numberstyle=\tiny,
  frame=single,
  breaklines=true,
  columns=fullflexible,
  showstringspaces=false,
  keywordstyle=\bfseries,
  captionpos=b
}

% ---------- Section style ----------
\usepackage{titlesec}
\titleformat{\section}{\Large\bfseries}{\thesection}{0.8em}{}
\titleformat{\subsection}{\large\bfseries}{\thesubsection}{0.7em}{}
\titleformat{\subsubsection}{\normalsize\bfseries}{\thesubsubsection}{0.6em}{}
\titlespacing*{\section}{0pt}{1.2em}{0.55em}
\titlespacing*{\subsection}{0pt}{0.9em}{0.4em}

% ---------- References and hyperlinks ----------
\usepackage{cite}
\usepackage[hidelinks]{hyperref}
\usepackage[nameinlink,noabbrev]{cleveref}
\usepackage{url}

% ---------- English labels ----------
\renewcommand{\figurename}{Figure}
\renewcommand{\tablename}{Table}
\renewcommand{\refname}{References}
\renewcommand{\abstractname}{Abstract}

% ---------- Page numbering ----------
\pagestyle{plain}

% ---------- Useful commands ----------
\newcommand{\R}{\mathbb{R}}
\newcommand{\E}{\mathbb{E}}
\newcommand{\Var}{\operatorname{Var}}
\newcommand{\argmin}{\operatorname*{arg\,min}}
\newcommand{\argmax}{\operatorname*{arg\,max}}
\newcommand{\keywords}[1]{%
  \vspace{0.6em}\noindent\textbf{Keywords:} #1
}

% ---------- Font commands used by the retained top border ----------
\newcommand{\songfourteen}{%
    \songti%
    \fontsize{14pt}{16.8pt}\selectfont
}

\newcommand{\songtenhalf}{%
    \songti%
    \fontsize{10.5pt}{12.6pt}\selectfont
}

\newcommand{\heitififteen}{%
    \heiti%
    \fontsize{15pt}{18pt}\selectfont
}

\newcommand{\songxiaosi}{%
    \songti%
    \fontsize{12pt}{12pt}\selectfont
}

% ---------- Retained top-border block ----------
% Edit only the text inside the nodes if you need to change category/title/team code.
\newcommand{\fronttable}{%
    \noindent
    \begin{tikzpicture}[x=1cm,y=1cm]
        \def\colA{3.05}
        \def\colB{10.16}
        \def\colC{2.78}
        \def\rowA{0.57}
        \def\rowB{1.66}
        \def\totalW{15.99}
        \def\totalH{2.23}

        \draw[line width=0.55pt]
            (0,0) rectangle (\totalW,-\totalH);

        \draw[line width=0.55pt]
            (\colA,0) -- (\colA,-\totalH);

        \draw[line width=0.55pt]
            ({\colA+\colB},0)
            -- ({\colA+\colB},-\totalH);

        \draw[line width=0.55pt]
            (0,-\rowA) -- (\colA,-\rowA);

        \draw[line width=0.55pt]
            ({\colA+\colB},-\rowA)
            -- (\totalW,-\rowA);

        \node[font=\songtenhalf]
            at ({\colA/2},{-\rowA/2})
            {Category};

        \node[font=\songtenhalf]
            at ({\colA+\colB+\colC/2},{-\rowA/2})
            {CUMCM};

        \node[font=\zihao{-4},align=center,text width=2.75cm]
            at ({\colA/2},{-\rowA-\rowB/2})
            {Undergraduate Group};

        \node[
            font=\bfseries\fontsize{13pt}{15.6pt}\selectfont,
            align=center,
            anchor=center,
            text width=9.5cm
        ]
            at ({\colA+\colB/2},{-\totalH/2})
            {2026 China Undergraduate\\Mathematical Contest in Modeling};

        \node[
            font=\bfseries\zihao{-4},
            align=center
        ]
            at ({\colA+\colB+\colC/2},{-\rowA-\rowB/2})
            {Team No.};
    \end{tikzpicture}%
}

\begin{document}

% ================================================================
% ABSTRACT PAGE -- PAGE 1 OF THE ELECTRONIC SUBMISSION
% ================================================================
\pagenumbering{arabic}
\setcounter{page}{1}

% Retained border from the uploaded template
\vspace*{-0.50cm}%
\fronttable

\vspace{0.50cm}
{\centering\bfseries\heitififteen Problem C\par}

\vspace{0.29cm}
{\centering\heiti\zihao{4} Your Paper Title Here\par}
\vspace{0.16cm}

\begin{center}
  {\large\bfseries Abstract}
\end{center}

% The abstract, title, and keywords should normally fit on this first page.
% Do not include names, university, region, or other identity information in the paper body.

This paper addresses \emph{[briefly state the practical problem]}. To solve the problem, we first
\emph{[describe data preprocessing / assumptions / exploratory analysis]}. For Problem 1, we construct
\emph{[Model I]} to determine \emph{[main decision/output]}. For Problem 2, we extend the framework by
incorporating \emph{[uncertainty / prediction / additional constraints]}. For Problem 3, we develop
\emph{[Model II / rolling optimization / simulation / other method]}. Finally, for Problem 4, we
\emph{[describe the final extension]}.

The main numerical results show that \emph{[insert the most important quantitative conclusion]}. Sensitivity
and robustness analyses indicate that \emph{[state stability or practical interpretation]}. The proposed
framework is interpretable, computationally feasible, and can provide useful guidance for
\emph{[application context]}.

\keywords{mathematical modeling; optimization; forecasting; sensitivity analysis; decision making}

\clearpage

% ================================================================
% MAIN TEXT -- DO NOT INSERT A TABLE OF CONTENTS
% ================================================================

\section{Introduction}

\subsection{Problem Background}

Introduce the application background, explain why the problem is important, and identify the key objects
and practical challenges involved. Briefly describe the context needed to understand the modeling tasks.

\subsection{Restatement of the Problem}

Restate the problem in your own words and summarize exactly what each subproblem asks you to determine.
Avoid copying large portions of the
original problem statement.

A clear structure is often:
\begin{enumerate}[label=\textbf{Problem \arabic*:},leftmargin=3.2cm]
  \item Briefly state the objective of Problem 1.
  \item Briefly state the objective of Problem 2.
  \item Briefly state the objective of Problem 3.
  \item Briefly state the objective of Problem 4 (if applicable).
\end{enumerate}

\section{Assumptions and Explanations}

List assumptions that are necessary, reasonable, and actually used later in the model. Typical examples are:
\begin{enumerate}
  \item The data supplied by the problem are reliable unless an explicit anomaly is identified.
  \item Variables not explicitly modeled have negligible influence over the study horizon.
  \item Model parameters remain stable within each specified operating regime.
  \item Random disturbances are represented by the uncertainty model introduced later.
\end{enumerate}

\section{Notations}

\begin{table}[H]
\centering
\caption{Main notation used in this paper.}
\label{tab:notation}
\begin{tabularx}{0.88\textwidth}{>{\centering\arraybackslash}p{0.18\textwidth} X >{\centering\arraybackslash}p{0.18\textwidth}}
\toprule
Symbol & Description & Unit \\
\midrule
$t$ & Time index & -- \\
$x_t$ & Example state variable at time $t$ & -- \\
$u_t$ & Example decision variable at time $t$ & -- \\
$c_t$ & Example unit cost at time $t$ & CNY/kWh \\
$J$ & Objective-function value & CNY \\
\bottomrule
\end{tabularx}
\end{table}

\section{Model Preparation}

Explain the modeling logic before presenting formulas. Show how the subproblems are connected and which
mathematical tools are appropriate for each one. The overall workflow may be summarized as
\[
\begin{aligned}
\text{Data preprocessing} &\longrightarrow \text{Prediction / estimation} \\
&\longrightarrow \text{Optimization} \\
&\longrightarrow \text{Validation and sensitivity analysis}.
\end{aligned}
\]

\subsection{Data Processing and Exploratory Analysis}

Describe the supplied data, units, missing-value treatment, interpolation or aggregation, and any derived
variables. Figures should explain a modeling decision rather than merely decorate the paper.

\begin{figure}[H]
  \centering
  % Replace the box below with, for example:
  % \includegraphics[width=0.78\textwidth]{figures/example.pdf}
  \fbox{\rule{0pt}{4.5cm}\rule{0.78\textwidth}{0pt}}
  \caption{Placeholder for an informative data or model figure.}
  \label{fig:placeholder}
\end{figure}

\section{Model 1: Solution to Question 1}

\subsection{Model Formulation}

Define the decision variables, state variables, objective function, and constraints. For a generic optimization
problem, one may write
\begin{equation}
  \min_{\bm{x}} \quad f(\bm{x})
  \label{eq:objective}
\end{equation}
subject to
\begin{align}
  g_i(\bm{x}) &\le 0, && i=1,\ldots,m, \\
  h_j(\bm{x}) &= 0, && j=1,\ldots,q.
\end{align}

Every term should be explained immediately after it is introduced.

\subsection{Solution Method}

Explain the numerical method or algorithm. If an iterative algorithm is used, provide concise pseudocode.

\begin{algorithm}[H]
\caption{Generic solution procedure}
\begin{algorithmic}[1]
\State Load and preprocess the input data.
\State Initialize parameters and state variables.
\For{each decision period}
  \State Update model inputs.
  \State Solve the optimization / estimation problem.
  \State Record decisions and system states.
\EndFor
\State Compute the requested summary statistics.
\end{algorithmic}
\end{algorithm}

\subsection{Results for Problem 1}

Report the quantities requested by the problem statement. Put the most important values in the main text and
large complete output tables in the required result files or supporting materials.

\begin{table}[H]
\centering
\caption{Example results for Problem 1.}
\label{tab:q1results}
\begin{tabular}{lrr}
\toprule
Scenario & Objective value & Key metric \\
\midrule
Baseline & 0.000 & 0.000 \\
Proposed model & 0.000 & 0.000 \\
\bottomrule
\end{tabular}
\end{table}

\section{Model 2: Solution to Question 2}
\label{sec:model2}

\subsection{Extension of the Basic Model}

\subsubsection{Decision Timing and Modeling Assumptions}

Question 2 extends deterministic energy scheduling to a setting in which both demand and photovoltaic
(PV) generation vary from day to day. At 00:00, the microgrid must commit to an electricity purchase
schedule before observing the day's actual net load. Under-purchasing may require emergency electricity
at five times the normal tariff, whereas unused scheduled purchases receive no refund or export revenue.
The objective is therefore to minimize operating expenditure under uncertainty, rather than forecast
error alone.

We retain the energy-balance and storage framework of Model 1 and introduce three linked components:
separate load and PV forecasting, whole-day residual scenarios, and scenario-tree optimization with
nonanticipativity constraints. Only the resulting purchase schedule is committed in advance. Storage
is subsequently operated by a causal feedback rule, and costs are settled using realized demand and PV
generation. Forecasting, planning, execution, and settlement thus have distinct information boundaries.

Let $d$ index days and $t\in\mathcal T=\{1,\ldots,144\}$ index 10-minute intervals, with
$\Delta t=1/6$ h. Load and PV power are denoted by $P^L_{d,t}$ and $P^{PV}_{d,t}$, respectively, and
$P^N_{d,t}=P^L_{d,t}-P^{PV}_{d,t}$ is net-load power. Power is treated as constant within each interval.
The normal tariff $p_t$ is known at the planning stage. All forecasts for day $d$ use only data from
dates strictly earlier than $d$; actual interval data become available only when that interval is reached.
The scheduled purchase $G_{d,t}$ cannot be revised during the day, and emergency purchases may cover
unmet demand but may not charge the battery.

Charging and discharging energies, $C_{d,t}$ and $D_{d,t}$, are measured on the microgrid side; $S_{d,t}$
is stored energy at the end of interval $t$. The storage parameters are
\begin{equation}
\begin{gathered}
 \eta_c=\eta_d=0.9,\qquad S_{\min}=1200\ \mathrm{kWh},\qquad S_{\max}=10800\ \mathrm{kWh},\\
 \bar C=\bar D=5000\Delta t=\frac{2500}{3}\ \mathrm{kWh}.
\end{gathered}
\label{eq:q2-storage-parameters}
\end{equation}
These parameters remain constant; self-discharge, degradation, and start-up losses are neglected.
Stored energy is carried across day boundaries without artificial resetting.

\subsubsection{Separate Load and PV Forecasting}

Load and PV generation reflect different sources of variability: demand may exhibit weekly behavioral
patterns, while PV output is strongly affected by recent weather conditions. We therefore use the load
from the same weekday of the preceding week and the median PV output at the same interval over the
preceding seven days to construct a central net-load forecast:
\begin{equation}
 \widehat P^{N,0}_{d,t}
 =P^L_{d-7,t}
 -\operatorname{median}\bigl\{P^{PV}_{d-7,t},\ldots,P^{PV}_{d-1,t}\bigr\}.
 \label{eq:q2-central-forecast}
\end{equation}
The weekly lag retains weekday-specific demand patterns, while the median reduces the influence of
isolated PV fluctuations. This is a structured decomposition, not an ensemble average of competing
predictors. Uncertainty around the central forecast is represented explicitly by historical residuals.

\subsubsection{Whole-Day Residual Scenarios}

Independent interval-by-interval sampling would discard the temporal dependence that determines whether
a battery can bridge a prolonged deficit. Instead, we retain complete daily forecast-error trajectories.
For each eligible historical day $j$, define
\begin{equation}
 r_{j,t}=P^{N,\mathrm{act}}_{j,t}-\widehat P^{N,0}_{j,t},
 \qquad t\in\mathcal T,
 \label{eq:q2-residual}
\end{equation}
where the historical forecast is itself constructed using only information available before day $j$.
Within the preceding 56-day window, we prioritize residual days matching the target day's weekday
and then fill the remaining places in reverse chronological order. During the initial evaluation period,
the window uses only the available eligible history. Twelve selected paths yield
\begin{equation}
 P^{N,(s)}_{d,t}=\widehat P^{N,0}_{d,t}+r_{j_s,t},
 \qquad s\in\mathcal S=\{1,\ldots,12\},\qquad \pi_s=\frac{1}{12}.
 \label{eq:q2-scenarios}
\end{equation}
The resulting scenarios combine the target day's central forecast with historical patterns of persistent
over- or under-prediction. Their usefulness depends on recent residuals remaining representative of
future uncertainty.

\subsubsection{Scenario Tree and Nonanticipativity}

The existence of twelve scenarios does not imply that their identities are known at 00:00. To limit
premature scenario-dependent adaptation, we divide the day into six 4-hour stages of 24 intervals each.
All scenarios initially share a root node. At each subsequent stage boundary, scenarios within each
parent node are split using two-cluster $K$-means applied to their net-load trajectories over the
preceding stage. Singleton nodes are not split; the number of nodes can grow to at most twelve.
Thus, node membership depends on an already elapsed scenario prefix, not on the remaining daily path.

Let $\mathcal T_k=\{24(k-1)+1,\ldots,24k\}$ and write $s\sim_k s'$ when scenarios $s$ and $s'$
belong to the same stage-$k$ node. Their planned storage actions must satisfy
\begin{equation}
 C^{(s)}_{d,t}=C^{(s')}_{d,t},\qquad
 D^{(s)}_{d,t}=D^{(s')}_{d,t},
 \quad t\in\mathcal T_k,\quad s\sim_k s'.
 \label{eq:q2-nonanticipativity}
\end{equation}
The purchase schedule $G_{d,t}$ is shared by every scenario throughout the day. These equalities enforce
nonanticipativity of storage actions on the chosen, coarsened scenario tree. They do not constitute an
exact representation of every possible real-time information history.

Scenario shortage and surplus variables close the interval energy balances after the current net load
is revealed; they are not advance control commitments. Unlike storage actions within a stage, these
passive balancing quantities may differ across scenarios sharing a node. Actual operation uses the
feedback rule below rather than selecting a precomputed scenario trajectory.

\subsubsection{Day-Ahead Stochastic Optimization}

For each scenario, let $\widetilde E^{(s)}_{d,t}$ denote simulated emergency energy and $W^{(s)}_{d,t}$
unused surplus energy. At 00:00, we solve
\begin{equation}
\begin{aligned}
 \min\quad &\sum_{t\in\mathcal T}p_tG_{d,t}
 +\lambda\sum_{s\in\mathcal S}\pi_s\sum_{t\in\mathcal T}5p_t\widetilde E^{(s)}_{d,t}\\
 &+\varepsilon\sum_{s\in\mathcal S}\sum_{t\in\mathcal T}
 \bigl(C^{(s)}_{d,t}+D^{(s)}_{d,t}\bigr).
\end{aligned}
\label{eq:q2-objective}
\end{equation}
The first term is the committed purchase cost; the second prices expected scenario shortages.
The calibration weight $\lambda$ adjusts the planning penalty without changing the actual fivefold
emergency tariff. The small positive coefficient $\varepsilon$ discourages unnecessary battery
throughput and is excluded from reported electricity expenditure.

For every $s\in\mathcal S$ and $t\in\mathcal T$, the constraints are
\begin{align}
 G_{d,t}+D^{(s)}_{d,t}+\widetilde E^{(s)}_{d,t}
 &=\Delta t P^{N,(s)}_{d,t}+C^{(s)}_{d,t}+W^{(s)}_{d,t},
 \label{eq:q2-planning-balance}\\
 S^{(s)}_{d,t}
 &=S^{(s)}_{d,t-1}+\eta_c C^{(s)}_{d,t}-D^{(s)}_{d,t}/\eta_d,
 \label{eq:q2-planning-storage}\\
 S_{\min}\le S^{(s)}_{d,t}&\le S_{\max},\qquad
 0\le C^{(s)}_{d,t}\le\bar C,\qquad 0\le D^{(s)}_{d,t}\le\bar D,
 \label{eq:q2-planning-bounds}\\
 G_{d,t},\ \widetilde E^{(s)}_{d,t},\ W^{(s)}_{d,t}&\ge0.
 \label{eq:q2-planning-nonnegative}
\end{align}
All scenarios start from the actual stored energy $S_{d,0}$. We also impose a terminal reserve:
\begin{equation}
 S^{(s)}_{d,0}=S_{d,0},\qquad S^{(s)}_{d,144}\ge3000\ \mathrm{kWh},
 \qquad s\in\mathcal S.
 \label{eq:q2-terminal-reserve}
\end{equation}
The terminal lower bound approximates the value of retaining energy for the next day.
Together with \cref{eq:q2-nonanticipativity}, these relations define a linear program solved using
HiGHS. The planning model is a surrogate for subsequent feedback operation: the throughput penalty is
not a hard charge--discharge exclusivity constraint, and the scenario terminal reserve does not guarantee
the same reserve on every realized path. Physical operating rules are enforced explicitly during execution.

\subsubsection{Causal Execution and Actual Settlement}

At interval $t$, the controller observes current net-load energy
$N^{\mathrm{act}}_{d,t}=\Delta t(P^{L,\mathrm{act}}_{d,t}-P^{PV,\mathrm{act}}_{d,t})$ and computes
$M_{d,t}=G_{d,t}-N^{\mathrm{act}}_{d,t}$. If $M_{d,t}\ge0$, surplus scheduled energy and PV output
are used to charge the battery:
\begin{equation}
\begin{aligned}
 C_{d,t}&=\min\left\{M_{d,t},\bar C,
                  \frac{S_{\max}-S_{d,t-1}}{\eta_c}\right\},\\
 D_{d,t}&=E_{d,t}=0,\qquad W_{d,t}=M_{d,t}-C_{d,t}.
\end{aligned}
\label{eq:q2-feedback-surplus}
\end{equation}
If $M_{d,t}<0$, the battery discharges first and emergency purchases cover only the remaining deficit:
\begin{equation}
\begin{aligned}
 D_{d,t}&=\min\left\{-M_{d,t},\bar D,
                         \eta_d(S_{d,t-1}-S_{\min})\right\},\\
 C_{d,t}&=W_{d,t}=0,\qquad E_{d,t}=-M_{d,t}-D_{d,t}.
\end{aligned}
\label{eq:q2-feedback-deficit}
\end{equation}
Actual stored energy then follows
\begin{equation}
 S_{d,t}=S_{d,t-1}+\eta_c C_{d,t}-D_{d,t}/\eta_d,
 \qquad S_{d+1,0}=S_{d,144}.
 \label{eq:q2-actual-storage}
\end{equation}
This rule prevents simultaneous charging and discharging, prohibits charging from emergency purchases,
and respects energy and power limits without using future actual observations.

The simulation starts with 6000 kWh at 00:00 on January 1, 2025. A January warm-up based on
previous-day net-load scheduling and causal feedback gives an initial evaluation state of 10800 kWh
at 00:00 on February 1. The evaluation set $\mathcal D$ covers February 1--December 31, 2025
($334$ days); January warm-up costs are not included. Actual expenditure is
\begin{equation}
 C_{\mathrm{total}}
 =\underbrace{\sum_{d\in\mathcal D}\sum_{t\in\mathcal T}p_tG_{d,t}}_{C_{\mathrm{plan}}}
 +\underbrace{\sum_{d\in\mathcal D}\sum_{t\in\mathcal T}5p_tE_{d,t}}_{C_{\mathrm{emg}}}.
 \label{eq:q2-settlement}
\end{equation}
Importantly, settlement uses actual emergency energy $E_{d,t}$, not the scenario quantity
$\widetilde E^{(s)}_{d,t}$, and never applies the calibration weight $\lambda$.

\subsection{Results and Interpretation}

\subsubsection{Comparison of Candidate Methods}

All candidate purchase schedules are evaluated with the same storage parameters, causal controller,
and settlement formula. For intuition, consider a single-interval purchase decision without storage or
salvage value. Under-purchasing by 1 kWh saves $p_t$ but incurs $5p_t$ in emergency cost, giving a net
underage cost of $4p_t$; over-purchasing costs $p_t$. The corresponding critical quantile is
\begin{equation}
 \tau=\frac{4p_t}{4p_t+p_t}=0.8.
 \label{eq:q2-critical-quantile}
\end{equation}
This motivates the $Q_{0.8}$ point-forecast baselines, but is not an optimality result for the full
storage-coupled problem. The proposed tree uses the central forecast and residual scenarios directly,
not a $Q_{0.8}$ curve as an additional input.

\begin{table}[htbp]
\centering
\small
\caption{Rolling-backtest expenditure over 334 days. All methods use causal feedback; costs are in
$10^4$ CNY and are rounded independently.}
\label{tab:q2-method-comparison}
\begin{tabularx}{\textwidth}{@{}Xrrr@{}}
\toprule
Planning method & Scheduled & Emergency & Total \\
\midrule
Separate load--PV $Q_{0.5}$ & 1218.97 & 323.07 & 1542.03 \\
Direct net-load $Q_{0.8}$ & 1370.74 & 77.28 & 1448.02 \\
Twelve whole-day residual scenarios & 1383.58 & 47.30 & 1430.88 \\
Separate load--PV $Q_{0.8}$ & 1349.44 & 71.01 & 1420.45 \\
\textbf{Nonanticipative 4-hour scenario tree} & \textbf{1316.85} & \textbf{61.74} & \textbf{1378.59} \\
Two-stage nonanticipativity relaxation & 1303.43 & 71.72 & 1375.15 \\
\bottomrule
\end{tabularx}
\end{table}

The median-based baseline incurs substantial emergency expenditure. Cost-sensitive quantiles reduce
this exposure, while separating load and PV improves the $Q_{0.8}$ baseline further. The 4-hour tree
reduces total expenditure relative to both the decomposed $Q_{0.8}$ baseline and the whole-day-scenario
alternative. Notably, its emergency cost is not the lowest: the reduction in scheduled purchases more
than offsets the remaining emergency expense. Economic performance therefore depends on balancing
the two cost components, not eliminating emergency purchases at any price.

The two-stage relaxation allows scenario-specific storage actions before those scenarios can be
distinguished. Its common purchase schedule is still executable under causal feedback, and its realized
cost is slightly lower. We nevertheless select the 4-hour tree because its planning-stage storage
decisions satisfy the specified nodewise information constraints; the relaxation is retained as an
ablation reference, not as a strictly nonanticipative planning model.

\subsubsection{Selected Configuration and Cost Breakdown}

The selected configuration uses twelve scenarios, 4-hour branching, a 3000 kWh scenario terminal
reserve, and $\lambda=0.9$. Thus, the internal shortage coefficient is $4.5p_t$, while actual emergency
purchases are still charged at $5p_t$. The reported expenditure for the 334-day evaluation period is
\begin{equation}
\begin{aligned}
 C_{\mathrm{plan}}&=13\,168\,516.81\ \mathrm{CNY},\\
 C_{\mathrm{emg}}&=617\,373.55\ \mathrm{CNY},\\
 C_{\mathrm{total}}&=\boxed{13\,785\,890.36\ \mathrm{CNY}}.
\end{aligned}
\label{eq:q2-final-cost}
\end{equation}
Scheduled and emergency purchases account for 95.52\% and 4.48\% of the total, respectively.
These figures describe February--December operation, not a full twelve-month cost.

\subsubsection{Sensitivity, Benchmarking, and Feasibility}

Imposing the tree's nodewise nonanticipativity constraints increases realized expenditure by approximately
$3.44\times10^4$ CNY, or 0.25\%, relative to the two-stage relaxation. This comparison shows that a
more information-consistent planning approximation retains competitive performance in this backtest.
It is not a proof that the realized-cost difference must be nonnegative for every dataset.

Reducing the branching interval from 4 hours to 2 hours raises the reported total to
$1388.40\times10^4$ CNY. Scheduled expenditure falls to $1292.76\times10^4$ CNY, but emergency
expenditure rises to $95.65\times10^4$ CNY. This decomposition is consistent with earlier branching
making the planner more optimistic about future storage flexibility and reducing advance purchases.
It does not establish that finer trees are intrinsically inferior; branching resolution must be assessed
together with scenario quality and the controller used in actual operation.

A reported perfect-information optimization, supplied with the entire realized net-load trajectory,
gives $C_{\mathrm{PI}}=12\,226\,852.42$ CNY, using the same February initial stored energy, continuous
interday storage dynamics, and a 3000 kWh end-of-horizon reserve. The selected strategy costs 12.75\%
more than this optimistic benchmark. A formal lower-bound comparison requires matching physical and
terminal-state requirements, including verification that the realized strategy meets the benchmark's
terminal reserve. The observed gap can reflect uncertainty, restricted information, and planning or
control approximations; it should not be attributed to linear-program solver error or exclusively to
forecast uncertainty.

The reported interval-level checks cover $334\times144=48\,096$ intervals. The maximum energy-balance
residual is $1.14\times10^{-13}$ kWh, and the interday storage-linking error is zero. Stored energy and
charging/discharging quantities remain within their limits; actual operation exhibits neither simultaneous
charging and discharging nor charging from emergency electricity. The interval-level quantities to be
reported in \texttt{result2.xlsx} are the committed purchases and corresponding realized charging,
discharging, emergency purchases, and storage states.

Finally, the scenario count, branching interval, and calibration weight were selected through exploratory
comparisons over the evaluation period. Although daily forecast construction and execution are causal,
these results are rolling-backtest results, not an independent out-of-sample assessment of a frozen
method. Independent testing would require selecting and fixing the parameters on an earlier
training--validation period. Additional limitations include the absence of weather covariates and the
use of a fixed terminal reserve to approximate the value of energy carried into the next day.

\section{Model 3: Solution to Question 3}

Present the additional mechanism required in Problem 3, such as rolling-horizon optimization, dynamic
control, spatial extension, or a more realistic constraint set.

\section{Model 4: Solution to Question 4}

If Problem 4 is an extension of earlier models, emphasize which assumptions, parameters, or data streams are
changed and which parts of the framework remain unchanged.

\section{Model Evaluation and Further Discussion}

\subsection{Sensitivity and Robustness Analysis}

Vary important parameters over reasonable ranges and report how conclusions change. Possible analyses include:
\begin{itemize}
  \item sensitivity of the objective value to key parameters;
  \item robustness to prediction error or noisy data;
  \item comparison with a baseline strategy;
  \item ablation of important model components.
\end{itemize}

A useful normalized sensitivity index is
\begin{equation}
S_{\theta}
=
\frac{\Delta J/J}{\Delta \theta/\theta},
\end{equation}
where $\theta$ is a model parameter and $J$ is the principal outcome measure.

\subsection{Strengths}
\begin{itemize}
  \item State the main methodological strengths.
  \item Explain why the model is interpretable and computationally feasible.
  \item Relate the model structure to the practical problem.
\end{itemize}

\subsection{Limitations and Possible Improvements}
\begin{itemize}
  \item Identify assumptions that may limit real-world accuracy.
  \item Discuss data limitations and unmodeled uncertainty.
  \item Suggest specific extensions rather than vague statements.
\end{itemize}

\subsection{Potential for Future Model Extension}

Discuss how the proposed framework could be extended when additional data, mechanisms, constraints, or
application scenarios become available. Identify concrete directions for improving generality, accuracy,
or computational efficiency.

\section{Conclusion}

Summarize the answers to all subproblems using the most important quantitative results. Avoid introducing new
methods or results in this section.

% ================================================================
% REFERENCES
% ================================================================
\begin{thebibliography}{99}

\bibitem{ref1}
A. Author and B. Author,
``Title of the referenced paper,''
\emph{Journal Name}, vol.~1, no.~1, pp.~1--10, 2025.

\bibitem{ref2}
Organization Name,
``Title of the data source or technical document,'' 2026.

\end{thebibliography}

% ================================================================
% APPENDIX
% ================================================================
\appendix

\section{Supporting-Material File List}

List every supporting file that is actually submitted. Example:
\begin{itemize}
  \item \texttt{code/model.py}: complete executable code for the main model;
  \item \texttt{code/forecast.py}: forecasting procedure;
  \item \texttt{results/intermediate.xlsx}: large intermediate result tables;
  \item \texttt{figures/}: figures generated by the submitted code.
\end{itemize}

\section{Key Source Code}

\begin{lstlisting}[language=Python,caption={Example code block}]
def objective(decision, price):
    return sum(x * p for x, p in zip(decision, price))
\end{lstlisting}

\end{document}
