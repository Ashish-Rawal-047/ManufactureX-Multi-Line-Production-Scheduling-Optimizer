# PlantSched — Multi-Line Production Scheduling & Changeover Optimization

> A constraint-based production scheduling, optimization, and discrete-event simulation system for multi-product, multi-line manufacturing operations under machine eligibility, capacity, sequence-dependent changeover, planned downtime, and due-date constraints.

---

## 1. Project Overview

**PlantSched** bridges Operations Research and practical manufacturing engineering. In multi-product plants sharing production lines, naive dispatching (such as First-Come First-Served) triggers excessive product changeovers, unbalanced line utilization, elevated makespan, and missed customer delivery dates.

PlantSched formulates the scheduling problem under a unified domain model (`SchedulingProblem` → `Schedule`) and provides:

- **Configurable Synthetic Data Engine**: Reproducible manufacturing instances (10 to 500+ jobs) with directional changeover matrices, machine eligibility, initial setup states, and planned maintenance windows.
- **FCFS Baseline**: Arrival-order reference scheduler respecting all manufacturing constraints.
- **Exact Optimization**:
  - **Google OR-Tools CP-SAT** using optional intervals, `AddNoOverlap`, and per-machine `AddCircuit` for immediate-predecessor sequence-dependent setups.
  - **PuLP / CBC MILP** using immediate-predecessor flow variables and Big-M precedence constraints.
- **Metaheuristics**:
  - **Genetic Algorithm (GA)** with Order Crossover (OX1), uniform machine crossover, and product-clustering mutation.
  - **Simulated Annealing (SA)** with swap, insert, machine-reassignment, and product-clustering neighborhoods.
- **Schedule Validator & KPI Engine**: Independent verification of every schedule invariant and plant/machine-level KPI calculation.
- **SimPy Discrete-Event Simulation & Monte Carlo Robustness**: Evaluates deterministic schedules under stochastic processing times, arrival delays, and unplanned machine breakdowns.
- **Visualization Suite**: Static Matplotlib (PNG) and interactive Plotly (HTML) Gantt charts, KPI comparisons, convergence curves, scaling plots, and Monte Carlo distributions.

---

## 2. Manufacturing Scheduling Problem

Consider a manufacturing plant with:

- **Production Lines / Machines ($M$)**: Parallel lines with availability windows (`available_from`, optional `available_until`), product eligibility sets, production capacity multipliers, initial setup product states ($p^0_m$), and planned downtime windows.
- **Products ($P$)**: Distinct SKUs grouped into families with directional sequence-dependent changeover durations.
- **Jobs / Orders ($J$)**: Customer orders with product type, quantity, processing duration, arrival time ($r_j$), due date ($d_j$), priority weight ($w_j$), and optional machine restrictions.

The core engineering question is:

> **Which product should be produced, on which production line, and in what sequence to minimize operational loss while satisfying delivery and capacity requirements?**

Because changeover times are **directional** ($\text{Setup}(A, B) \neq \text{Setup}(B, A)$ in general, with $\text{Setup}(A, A) = 0$), sequencing `A → A → B → B` instead of `A → B → A → B` eliminates unproductive setup capacity loss without changing total production volume.

---

## 3. System Architecture

```text
Production Orders / Synthetic Generator (plantsched/data/)
                         │
                         ▼
         Validation & Preprocessing (core/problem.py, data/preprocessing.py)
                         │
                         ▼
              SchedulingProblem Contract
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
   FCFS Baseline              Optimization & Metaheuristics
 (baselines/fcfs.py)             ├── OR-Tools CP-SAT (optimization/cp_sat.py)
                                 ├── PuLP / CBC MILP (optimization/milp.py)
                                 ├── Genetic Algorithm (heuristics/genetic_algorithm.py)
                                 └── Simulated Annealing (heuristics/simulated_annealing.py)
         │                               │
         └───────────────┬───────────────┘
                         ▼
                Schedule Contract
                         │
                         ▼
           ScheduleValidator (core/validator.py)
                         │
                         ▼
             KPI Engine (evaluation/metrics.py)
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
SimPy Plant & Monte Carlo       Gantt & KPI Visualizations
  (simulation/plant.py,           (visualization/gantt.py,
   simulation/monte_carlo.py)      visualization/kpi_plots.py)
```

---

## 4. Mathematical Formulation

### Decision Variables

- $x_{jm} \in \{0, 1\}$: $1$ if job $j$ is assigned to eligible machine $m \in M_j$.
- $f_{jm} \in \{0, 1\}$: $1$ if job $j$ is the first job executed on machine $m$.
- $l_{jm} \in \{0, 1\}$: $1$ if job $j$ is the last job executed on machine $m$.
- $y_{ijm} \in \{0, 1\}$: $1$ if job $j$ immediately follows job $i$ on machine $m$ ($i \neq j$).
- $S^{\text{setup}}_j \ge r_j$: Setup start time (and start of machine occupation) for job $j$.
- $\Delta^{\text{setup}}_j \ge 0$: Sequence-dependent setup duration for job $j$.
- $S^{\text{proc}}_j = S^{\text{setup}}_j + \Delta^{\text{setup}}_j$: Processing start time.
- $C_j = S^{\text{proc}}_j + \sum_{m \in M_j} p_{jm} x_{jm}$: Completion time.
- $T_j = \max(0, C_j - d_j)$: Tardiness of job $j$.
- $C_{\max} = \max_{j \in J} C_j$: Makespan.

### Machine Assignment & Flow Constraints

Each job must be assigned to exactly one eligible production line:

$$\sum_{m \in M_j} x_{jm} = 1 \quad \forall j \in J$$

On each machine $m$, flow conservation links assigned jobs into a single contiguous sequence:

$$\sum_{j \in J_m} f_{jm} = \sum_{j \in J_m} l_{jm} \le 1$$

$$f_{jm} + \sum_{i \in J_m \setminus \{j\}} y_{ijm} = x_{jm}, \qquad l_{jm} + \sum_{k \in J_m \setminus \{j\}} y_{jkm} = x_{jm} \quad \forall j \in J_m$$

### Sequence-Dependent Changeover & Capacity Constraints

Immediate-predecessor transitions determine the realized setup duration, including the machine's initial setup state $p^0_m$:

$$\Delta^{\text{setup}}_j = \sum_{m \in M_j} \left( s_{p^0_m, p(j)} f_{jm} + \sum_{i \in J_m \setminus \{j\}} s_{p(i), p(j)} y_{ijm} \right) \quad \forall j \in J$$

Machine non-overlap ensures $C_i \le S^{\text{setup}}_j$ whenever $y_{ijm} = 1$, and job intervals $[S^{\text{setup}}_j, C_j)$ cannot overlap any machine downtime window $[\underline{\delta}_{mk}, \overline{\delta}_{mk})$ or fall outside $[A_m, U_m]$.

### Objective Functions

PlantSched supports configurable weights $(\alpha, \beta, \gamma)$ via `ObjectiveWeights`:

$$\min \; \alpha \, C_{\max} + \beta \sum_{j \in J} w_j T_j + \gamma \sum_{j \in J} \Delta^{\text{setup}}_j$$

Presets include `makespan_only()`, `weighted_tardiness_only()`, `changeover_only()`, and `balanced()` ($\alpha=1.0, \beta=1.0, \gamma=0.5$).

---

## 5. Optimization & Baseline Methods

### 5.1 FCFS Baseline (`plantsched/baselines/fcfs.py`)
Schedules orders sorted by `(arrival_time, job_id)` onto the eligible machine offering the earliest feasible completion time via `compute_earliest_slot`, strictly enforcing arrival times, machine eligibility, initial setup states, sequence-dependent setups, and downtime windows.

### 5.2 Exact Optimization — OR-Tools CP-SAT (`plantsched/optimization/cp_sat.py`)
- Uses `AddExactlyOne` for machine assignment, `NewOptionalIntervalVar` + `AddNoOverlap` (including fixed downtime intervals), and per-machine `AddCircuit` to enforce immediate-predecessor setup transitions without subtours.
- Warm-started with complete FCFS variable hints (`AddHint`).
- Automatically applies integer scaling (1× for integer instances, 100× when fractional times/weights exist).
- Explicitly separates solver status into `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `UNKNOWN`, and `MODEL_INVALID`.

### 5.3 MILP Formulation — PuLP / CBC (`plantsched/optimization/milp.py`)
- Formulates the arc-flow precedence MILP with Big-$M$ (`M = problem.compute_horizon()`) and optional binary disjunctive downtime constraints (`include_downtime=True`).
- Verified on small instances to match CP-SAT's proven optimal objective exactly (`tests/test_milp.py`).
- **Key Difference & Limitation vs. CP-SAT**: Because $O(N^2 |M|)$ binary `y[i,j,m]` variables and Big-$M$ precedence produce weak LP relaxations, CBC's branch-and-bound scales only to small instances ($N \le 20\text{--}25$). In addition, PlantSched explicitly checks `model.sol_status` (`LpSolutionOptimal` vs. `LpSolutionIntegerFeasible`) and variable integrality so time-limited CBC incumbents are never mislabeled `OPTIMAL`.

### 5.4 Genetic Algorithm (`plantsched/heuristics/genetic_algorithm.py`)
- Encodes solutions as a dual-vector `Chromosome(job_sequence, machine_choices)` so the search controls both dispatch ordering and line assignment (allowing intentional line waiting to preserve product campaigns).
- Seeded with FCFS, EDD, SPT, product-grouped, and priority-ordered chromosomes alongside random permutations.
- Uses **Order Crossover (OX1)** + **Uniform Machine Crossover**, tournament selection, elitism, and swap/insert/product-cluster/machine-reassignment mutations—preserving 100% permutation and eligibility validity.

### 5.5 Simulated Annealing (`plantsched/heuristics/simulated_annealing.py`)
- Starts from the best greedy heuristic seed and explores `swap`, `insert`, `product_cluster`, and eligible-machine `reassign` neighborhoods under a geometric cooling schedule (`T <- T * cooling_rate`), tracking the global best schedule independently of the Markov chain state.

---

## 6. Schedule Validation & KPI Engine

Every algorithm output passes through `ScheduleValidator.validate()` (`plantsched/core/validator.py`), which checks:
- Exact job completeness (no missing, duplicate, or unknown jobs)
- Machine eligibility and product identity
- Arrival time, `available_from`, `available_until`, and downtime non-overlap
- Timing invariants (`start_time == setup_start_time`, `setup_start + setup_duration == processing_start`, `processing_start + processing_duration == completion_time`, `tardiness == max(0, completion - due_date)`)
- Chronological machine non-overlap and exact sequence-dependent setup transition durations

`evaluate_schedule()` (`plantsched/evaluation/metrics.py`) computes:
- **Makespan** ($\max_j C_j$), **Total Changeover Time**, **Total & Weighted Tardiness**, **Max Tardiness**, **Late Orders**, **OTD %**
- **Machine-Level KPIs**: Processing time, setup time, busy time (`processing + setup`), available time, idle time, **Total Utilization %** (`busy / available`), and **Processing Utilization %** (`processing / available`) reported separately
- **Approximate OEE**: $\text{Availability} \times \text{Performance} \times 1.0$ (explicitly noting that Quality = 100% is assumed because defect/scrap rates are not modeled)

---

## 7. Discrete-Event Simulation & Robustness Analysis

`plantsched/simulation/` executes any deterministic `Schedule` inside a **SimPy** discrete-event plant (`simpy.Resource` per machine):
- **Stochastic Processing Times**: `max(0.25 * nominal, Normal(nominal, cv * nominal))`
- **Stochastic Job Arrivals**: Probabilistic release delays
- **Planned Downtime & Unplanned Breakdowns**: Exponential repair times (`MTTR`) triggered by Poisson failure hazard (`MTBF`)

`run_monte_carlo()` executes $R$ seeded replications to measure mean/std/P95/worst-case makespan, expected tardiness, probability of 100% OTD, and schedule deviations.

---

## 8. Actual Experimental & Benchmark Results

All results below were measured directly by running the PlantSched CLI suite with `ObjectiveWeights(alpha=1.0, beta=1.0, gamma=0.5)` and `seed=42` (`results/optimization_comparison.csv`, `results/scaling_benchmark.csv`, `results/monte_carlo_summary.csv`).

### 8.1 Single-Instance Comparison (20 Jobs, 3 Machines, 6 Products)

Command: `python scripts/run_optimization.py --jobs 20 --machines 3 --products 6 --seed 42`

| Algorithm | Status | Valid | Makespan (min) | Changeover (min) | Total Tardiness | OTD (%) | Utilization (%) | Proc Util (%) | Objective | Best Bound | Gap (%) | Runtime (s) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | FEASIBLE | True | 369.0 | 340.0 | 0.0 | 100.0 | 96.75 | 66.03 | 539.0 | — | — | 0.0001 |
| CP-SAT | FEASIBLE | True | **297.0** | **94.0** | 0.0 | 100.0 | 92.59 | **82.04** | **344.0** | 246.5 | 28.34 | 20.0521 |
| MILP | FEASIBLE | True | 484.0 | 179.0 | 581.0 | 65.0 | 62.67 | 50.34 | 1496.0 | — | — | 19.8999 |
| GeneticAlgorithm | FEASIBLE | True | 331.0 | 139.0 | 0.0 | 100.0 | 87.61 | 73.62 | 400.5 | — | — | 3.1864 |
| SimulatedAnnealing | FEASIBLE | True | 310.0 | 112.0 | 0.0 | 100.0 | 90.65 | 78.60 | 366.0 | — | — | 0.4444 |

**Key Observations**:
- **CP-SAT** reduced changeover time by **72.4%** (340 → 94 min) and makespan by **19.5%** (369 → 297 min) vs. FCFS, raising value-adding processing utilization from 66.0% to 82.0%.
- **Simulated Annealing** achieved within 6.4% of CP-SAT's objective (`366.0` vs. `344.0`) in **0.44 s**.
- **MILP (CBC)** struggled with Big-$M$ LP relaxations at 20 jobs (`1496.0` at the 20 s limit), highlighting CP-SAT's advantage on disjunctive setup scheduling.

### 8.2 Scaling Benchmark (10 to 500 Jobs)

Command: `python scripts/run_benchmarks.py --sizes 10 25 50 100 250 500 --cp-time 15 --milp-time 15 --seed 42`

*(Note: MILP is capped at 25 jobs and CP-SAT at 100 jobs because their $O(N^2 |M|)$ sequence-arc formulations exceed practical exact-solver scale at 250–500 jobs.)*

| Jobs | Algorithm | Status | Makespan (min) | Changeover (min) | OTD (%) | Objective | Gap (%) | Runtime (s) |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 10 | FCFS | FEASIBLE | 114.0 | 138.0 | 100.0 | 183.0 | — | 0.0001 |
| 10 | **CP-SAT** | **OPTIMAL** | **103.0** | 65.0 | 100.0 | **135.5** | 0.00 | 1.0084 |
| 10 | MILP | FEASIBLE | 117.0 | 51.0 | 100.0 | 142.5 | — | 14.9610 |
| 10 | GA | FEASIBLE | 103.0 | 75.0 | 100.0 | 140.5 | — | 1.7633 |
| 10 | SA | FEASIBLE | 103.0 | 87.0 | 100.0 | 146.5 | — | 0.2882 |
| 25 | FCFS | FEASIBLE | 371.0 | 418.0 | 100.0 | 580.0 | — | 0.0011 |
| 25 | CP-SAT | FEASIBLE | 337.0 | 174.0 | 100.0 | 424.0 | 45.05 | 15.5117 |
| 25 | MILP | UNKNOWN | — | — | — | — | — | 14.0916 |
| 25 | **GA** | FEASIBLE | **305.0** | 232.0 | 100.0 | **421.0** | — | 3.0929 |
| 25 | SA | FEASIBLE | 323.0 | 211.0 | 100.0 | 428.5 | — | 0.6017 |
| 50 | FCFS | FEASIBLE | 701.0 | 791.0 | 100.0 | 1096.5 | — | 0.0027 |
| 50 | CP-SAT | FEASIBLE | 611.0 | 412.0 | 100.0 | 817.0 | 41.13 | 16.3966 |
| 50 | **GA** | FEASIBLE | 617.0 | **268.0** | 100.0 | **751.0** | — | 5.7869 |
| 50 | SA | FEASIBLE | **610.0** | 366.0 | 100.0 | 793.0 | — | 1.1407 |
| 100 | FCFS | FEASIBLE | 1301.0 | 1338.0 | 100.0 | 1970.0 | — | 0.0040 |
| 100 | CP-SAT | UNKNOWN | — | — | — | — | — | 19.0042 |
| 100 | **GA** | FEASIBLE | **1152.0** | **403.0** | 100.0 | **1353.5** | — | 11.3046 |
| 100 | SA | FEASIBLE | 1180.0 | 454.0 | 99.0 | 1429.5 | — | 2.3018 |
| 250 | FCFS | FEASIBLE | 1603.0 | 3028.0 | 100.0 | 3117.0 | — | 0.0239 |
| 250 | **GA** | FEASIBLE | 1607.0 | **2923.0** | 100.0 | **3068.5** | — | 16.8793 |
| 250 | SA | FEASIBLE | 1607.0 | 2927.0 | 100.0 | 3070.5 | — | 6.3491 |
| 500 | FCFS | FEASIBLE | 3289.0 | 6903.0 | 98.6 | 7386.0 | — | 0.0384 |
| 500 | **GA** | FEASIBLE | **3247.0** | **6315.0** | **100.0** | **6404.5** | — | 33.4785 |
| 500 | **SA** | FEASIBLE | **3247.0** | **6315.0** | **100.0** | **6404.5** | — | 12.0584 |

### 8.3 Monte Carlo SimPy Simulation (30 Jobs, 30 Replications, CV = 0.12)

Command: `python scripts/run_simulation.py --jobs 30 --machines 3 --products 6 --replications 30 --cv 0.12 --seed 42`

| Algorithm | Planned Makespan | Avg Sim Makespan | Std Sim Makespan | P95 Makespan | Worst Makespan | Planned OTD (%) | Avg Sim OTD (%) | Prob(All On-Time) | Prob(OTD ≥ 90%) | Avg Wait (min) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FCFS | 565.0 | 604.02 | 41.45 | 683.67 | 745.46 | 96.67 | 95.33 | 0.00% | 96.67% | 195.25 |
| **CP-SAT** | **438.0** | **491.57** | 42.39 | **549.83** | 660.02 | 100.00 | **97.22** | **60.00%** | **96.67%** | **180.62** |
| GeneticAlgorithm | 484.0 | 548.03 | 41.35 | 616.07 | 690.56 | 100.00 | 93.56 | 13.33% | 90.00% | 220.61 |
| SimulatedAnnealing | 455.0 | 508.90 | **39.10** | 595.73 | **621.72** | 100.00 | 94.67 | 16.67% | 93.33% | 184.31 |

Under stochastic processing variability, delayed arrivals, and machine breakdowns, **CP-SAT's tighter deterministic schedule retained 60.0% probability of 100% on-time delivery** (vs. 0.0% for FCFS), while **Simulated Annealing achieved the lowest worst-case makespan (621.72 min)**.

---

## 9. Project Structure

```text
PlantSched/
├── data/
│   ├── raw/
│   ├── processed/
│   ├── generated/
│   └── benchmarks/
├── plantsched/
│   ├── __init__.py
│   ├── core/
│   │   ├── config.py             # SolverStatus, ObjectiveWeights, solver/sim configs
│   │   ├── models.py             # Product, DowntimeWindow, Machine, Job
│   │   ├── problem.py            # ChangeoverMatrix, SchedulingProblem
│   │   ├── schedule.py           # ScheduledJob, Schedule
│   │   ├── scheduling_utils.py   # Shared compute_earliest_slot helper
│   │   └── validator.py          # ScheduleValidator
│   ├── data/
│   │   ├── generator.py          # Configurable synthetic instance generator
│   │   ├── loader.py             # JSON and CSV serialization
│   │   └── preprocessing.py      # Validation & feature extraction
│   ├── baselines/
│   │   └── fcfs.py               # First-Come First-Served baseline
│   ├── optimization/
│   │   ├── constraints.py        # Integer scaling & horizon helpers
│   │   ├── objectives.py         # Objective & optimality gap helpers
│   │   ├── cp_sat.py             # OR-Tools CP-SAT model (AddCircuit + AddNoOverlap)
│   │   └── milp.py               # PuLP / CBC MILP model
│   ├── heuristics/
│   │   ├── decoder.py            # Chromosome & feasible schedule decoder
│   │   ├── genetic_algorithm.py  # OX1 + Uniform Crossover GA
│   │   └── simulated_annealing.py
│   ├── evaluation/
│   │   ├── metrics.py            # Plant & machine-level KPI engine
│   │   ├── comparison.py         # Fair single-instance comparison
│   │   └── benchmark.py          # Multi-scale experiment runner
│   ├── simulation/
│   │   ├── events.py             # Stochastic processing, arrival, breakdown sampling
│   │   ├── machine.py            # SimPy machine resource wrapper
│   │   ├── plant.py              # Discrete-event SimPy plant executor
│   │   └── monte_carlo.py        # Multi-replication robustness analyzer
│   └── visualization/
│       ├── gantt.py              # Matplotlib PNG & Plotly HTML Gantt charts
│       └── kpi_plots.py          # KPI, scaling, convergence, and Monte Carlo plots
├── scripts/
│   ├── generate_data.py
│   ├── run_baseline.py
│   ├── run_optimization.py
│   ├── run_benchmarks.py
│   └── run_simulation.py
├── tests/                        # Pytest unit & end-to-end integration tests
├── docs/                         # Architecture, math model, algorithms, simulation, design docs
├── notebooks/                    # 4 exploratory Jupyter notebooks
├── results/                      # Generated charts & CSV exports (gitignored except .gitkeep)
├── pyproject.toml
├── requirements.txt
├── LICENSE
└── README.md
```

---

## 10. Installation & Execution

### Setup Virtual Environment

```bash
python -m venv .venv
```

Activate on Windows:

```bash
.venv\Scripts\activate
```

Activate on Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Run CLI Workflows

```bash
# 1. Generate synthetic datasets (JSON & CSV)
python scripts/generate_data.py

# 2. Run FCFS baseline and export Gantt charts
python scripts/run_baseline.py

# 3. Compare FCFS, CP-SAT, MILP, GA, and SA + generate Gantt & KPI plots
python scripts/run_optimization.py

# 4. Run 10–500 job scaling benchmarks
python scripts/run_benchmarks.py

# 5. Run SimPy discrete-event simulation & Monte Carlo robustness analysis
python scripts/run_simulation.py
```

### Run Tests

```bash
pytest -v
```

---

## 11. Design Trade-offs, Limitations & Future Work

### Design Trade-offs
- **CP-SAT `AddCircuit` vs. MILP Big-$M$**: CP-SAT's circuit + optional-interval propagation finds high-quality schedules within 15–20 s up to ~50 jobs and proves optimality on small instances, whereas MILP's LP relaxation weakens rapidly beyond ~10–15 jobs.
- **Dual-Vector Heuristic Encoding**: Encoding both `job_sequence` and `machine_choices` increases chromosome search space slightly compared to greedy list-scheduling alone, but unlocks changeover-saving assignments that wait on a dedicated line rather than switching immediately to an idle line with a high setup penalty.

### Current Limitations
- Exact models (`CP-SAT` and `MILP`) build $O(N^2 |M|)$ sequence transition arcs, limiting practical exact solving to roughly $N \le 50\text{--}100$ for CP-SAT and $N \le 20$ for CBC MILP.
- Operations are currently single-stage (parallel lines with eligibility) rather than multi-operation job-shop routing, and quality/scrap defects are not modeled in OEE.
- The SimPy simulator executes a fixed planned sequence per machine without dynamic online re-dispatching upon breakdowns.

### Future Improvements
- Multi-stage flexible job-shop (FJSSP) routing with precedence graphs
- Dynamic rescheduling / rolling-horizon simulation policies when breakdowns occur
- Workforce and setup-crew resource constraints
- Public Taillard / OR-Library FJSSP benchmark parsers
- Two-stage stochastic optimization for robust changeover campaigns

---

## Author

**Ashish Rawal** — Operations Research, Production Scheduling, Mathematical Optimization & Discrete-Event Simulation.
