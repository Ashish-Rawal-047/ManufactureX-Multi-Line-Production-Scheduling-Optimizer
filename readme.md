# PlantSched — Multi-Line Production Scheduling & Changeover Optimization

> A constraint-based production scheduling system for optimizing multi-product, multi-line manufacturing operations under machine capacity, changeover, sequencing, and delivery constraints.

## Overview

**PlantSched** is a production scheduling and optimization project designed around a realistic manufacturing environment where multiple products must be scheduled across shared production lines.

In manufacturing plants, production sequencing is not simply about maximizing output. Switching between products introduces **setup/changeover time**, machines have limited capacity, and customer orders have delivery deadlines.

A poor schedule can result in:

* Excessive changeover time
* Machine idle time
* Increased makespan
* Late orders
* Reduced utilization
* Lower effective production capacity

PlantSched formulates the scheduling problem as a **constraint optimization problem** and compares an exact optimization approach against heuristic/metaheuristic scheduling as problem size increases.

---

# Problem Statement

Consider a plant with:

* Multiple production lines/machines
* Multiple products
* Different processing times
* Product-dependent setup/changeover times
* Different order quantities
* Customer due dates
* Machine availability constraints

The objective is to determine:

> **Which product should be produced, on which line, and in what sequence to minimize production loss while satisfying delivery requirements?**

A simplified production sequence might look like:

```text
Line 1

Product A → Product B → Product D → Product C
             ↑
       Changeover
```

The cost of changing from one product to another depends on the sequence:

```text
Setup Time:

          A     B     C     D
       ┌───────────────────────
   A   │  0    15    30    20
   B   │ 10     0    25    15
   C   │ 25    20     0    30
   D   │ 15    10    20     0
```

Therefore:

```text
Total Production Time
=
Processing Time
+
Changeover Time
+
Idle Time
```

The goal is to find a schedule that minimizes the relevant operational cost.

---

# Objectives

PlantSched supports optimization objectives such as:

### Primary Objective

**Minimize makespan**

```text
Makespan = Completion Time of the Last Job
```

### Alternative Objectives

* Minimize weighted tardiness
* Minimize total changeover time
* Maximize on-time delivery
* Maximize machine utilization
* Minimize production idle time
* Optimize a weighted combination of operational KPIs

---

# System Architecture

```text
                    Production Orders
                           │
                           ▼
                ┌─────────────────────┐
                │ Data Generation /   │
                │ Dataset Loader      │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ Preprocessing &      │
                │ Feature Engineering  │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ Scheduling Model     │
                │                     │
                │ Jobs                │
                │ Machines            │
                │ Processing Times    │
                │ Changeovers         │
                │ Due Dates           │
                └──────────┬──────────┘
                           │
             ┌─────────────┴─────────────┐
             │                           │
             ▼                           ▼
    ┌──────────────────┐       ┌──────────────────┐
    │ CP-SAT / MILP    │       │ Metaheuristic    │
    │ Exact Solver     │       │ GA / SA          │
    └────────┬─────────┘       └────────┬─────────┘
             │                          │
             └────────────┬─────────────┘
                          ▼
                ┌─────────────────────┐
                │ Schedule Evaluation │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ KPI Analysis        │
                │                     │
                │ Makespan            │
                │ Changeover Time     │
                │ OTD                 │
                │ Utilization / OEE   │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ Discrete Event      │
                │ Simulation          │
                └─────────────────────┘
```

---

# Mathematical Formulation

## Decision Variables

For each job `j`:

```text
x[j] = assigned production line
s[j] = start time
c[j] = completion time
```

For sequencing decisions, binary variables can represent whether job `i` precedes job `j`.

```text
y[i,j] = 1  if job i precedes job j
         0  otherwise
```

---

# Constraints

## 1. Machine Assignment

Each job must be assigned to an eligible production line.

```text
Σ x[j,m] = 1
```

for every job `j`.

---

## 2. Processing Time

Completion time must account for processing duration:

```text
c[j] = s[j] + processing_time[j]
```

---

## 3. Machine Capacity

Two jobs assigned to the same machine cannot overlap.

For jobs `i` and `j`:

```text
c[i] + setup[i,j] ≤ s[j]
```

or:

```text
c[j] + setup[j,i] ≤ s[i]
```

depending on their sequence.

---

## 4. Changeover Time

When the production sequence changes from product `A` to product `B`:

```text
Setup(A,B) > 0
```

The schedule explicitly incorporates this setup duration.

This allows PlantSched to distinguish between:

```text
A → A → A → B
```

and:

```text
A → B → A → B
```

even when the total production quantity is identical.

---

## 5. Due-Date Constraints

Each job has a target completion date:

```text
Completion[j] ≤ DueDate[j]
```

or tardiness is calculated as:

```text
Tardiness[j] =
max(0, Completion[j] - DueDate[j])
```

---

# Objective Functions

## Makespan Minimization

```text
Minimize:

Cmax
```

where:

```text
Cmax = max(completion[j])
```

---

## Weighted Tardiness

When delivery performance is more important:

```text
Minimize:

Σ w[j] × Tardiness[j]
```

where `w[j]` represents the importance of job `j`.

---

## Multi-Objective Optimization

A weighted objective can combine multiple plant KPIs:

```text
Objective =
α × Makespan
+
β × Total Tardiness
+
γ × Changeover Time
```

The weights can be adjusted according to business priorities.

---

# Optimization Approaches

## 1. Baseline — FCFS

The simplest baseline schedules jobs according to arrival order:

```text
First Come
     ↓
First Served
```

This provides a reference point for measuring optimization improvements.

---

# 2. Exact Optimization — CP-SAT

PlantSched uses **OR-Tools CP-SAT** to model scheduling constraints.

The solver searches for an optimal or near-optimal schedule while respecting:

* Machine constraints
* Job precedence
* Processing times
* Changeover times
* Due dates
* Resource availability

This approach is effective for small and medium-sized scheduling problems.

---

# 3. Mixed-Integer Optimization

The scheduling problem can also be represented as a MILP.

Binary variables determine:

* Machine assignment
* Job ordering
* Precedence
* Setup transitions

Continuous variables determine:

* Start times
* Completion times
* Tardiness

---

# 4. Genetic Algorithm

For larger instances, an exact solver may become computationally expensive.

A genetic algorithm represents a schedule as a chromosome:

```text
[A, C, B, D, A, B, C, D]
```

The algorithm iteratively applies:

* Selection
* Crossover
* Mutation
* Fitness evaluation

until an acceptable solution is found.

---

# 5. Simulated Annealing

An alternative metaheuristic can improve a schedule through local modifications:

```text
Current Schedule
       │
       ▼
Swap / Move Job
       │
       ▼
Evaluate Objective
       │
       ▼
Accept / Reject
```

This can provide good solutions when exact optimization becomes expensive.

---

# Solver vs Metaheuristic

One of the main experiments evaluates how optimization methods scale.

```text
Problem Size
     │
     ├── Small
     │     └── CP-SAT / MILP
     │
     ├── Medium
     │     └── CP-SAT
     │
     └── Large
           └── Genetic Algorithm / SA
```

The goal is not to claim that a heuristic is always better.

Instead, the project measures the trade-off between:

```text
Solution Quality
        vs.
Computation Time
```

---

# Manufacturing KPIs

## 1. Makespan

Total time required to complete all scheduled jobs.

```text
Makespan =
max(Job Completion Times)
```

Lower is better.

---

## 2. Total Changeover Time

```text
Total Changeover =
Σ Setup Time
```

Lower changeover time means more production capacity.

---

## 3. On-Time Delivery

```text
OTD % =
On-Time Jobs / Total Jobs × 100
```

Higher is better.

---

## 4. Machine Utilization

```text
Utilization =
Busy Time / Available Time × 100
```

---

## 5. Tardiness

```text
Tardiness =
max(0, Completion Time - Due Date)
```

---

## 6. Effective OEE Analysis

PlantSched can approximate operational efficiency using:

```text
Availability × Performance × Quality
```

The scheduling layer primarily affects **availability and performance**, while quality can be integrated when production data contains defect information.

---

# Example Scenario

Consider a plant with:

```text
Machines = 3
Products = 6
Orders = 30
```

Each product has:

```text
Processing Time
Demand Quantity
Due Date
Machine Eligibility
```

and a changeover matrix:

```text
Product A → B = 20 min
Product A → C = 35 min
Product B → C = 15 min
Product C → A = 30 min
```

A naive schedule might produce:

```text
A → C → B → A → C → B
```

creating frequent changeovers.

An optimized schedule might instead produce:

```text
A → A → A → B → B → C → C
```

reducing setup time while still meeting delivery requirements.

---

# Experimental Design

## Experiment 1 — Baseline vs Optimized

Compare:

```text
FCFS
  vs.
CP-SAT
```

Metrics:

* Makespan
* Total changeover time
* On-time delivery
* Machine utilization

---

## Experiment 2 — Exact Solver Scaling

Solve increasingly large instances:

```text
10 jobs
25 jobs
50 jobs
100 jobs
250 jobs
500 jobs
```

Track:

```text
Problem Size
     ↓
Solver Runtime
     ↓
Solution Quality
```

The goal is to identify the practical scale at which exact optimization becomes expensive.

---

## Experiment 3 — CP-SAT vs Genetic Algorithm

Compare:

| Metric           | CP-SAT | Genetic Algorithm |
| ---------------- | -----: | ----------------: |
| Makespan         |      — |                 — |
| Runtime          |      — |                 — |
| Changeover Time  |      — |                 — |
| On-Time Delivery |      — |                 — |
| Optimality Gap   |      — |                 — |

This demonstrates the trade-off between exact optimization and approximate optimization.

---

# Discrete-Event Simulation

An optimized schedule should not only look mathematically valid; it should behave correctly in a simulated production environment.

PlantSched can use **SimPy** to simulate:

```text
Job Arrival
     ↓
Machine Queue
     ↓
Setup / Changeover
     ↓
Production
     ↓
Machine Release
     ↓
Next Job
```

The simulation can incorporate realistic operational effects such as:

* Processing-time variability
* Machine downtime
* Delayed jobs
* Queue formation
* Random disturbances

This provides a bridge between:

```text
Optimization Model
        ↓
Realistic Plant Simulation
```

---

# Robustness Analysis

Real production systems rarely have deterministic processing times.

A future/extended version can model:

```text
Processing Time ~ Distribution
```

For example:

```text
Normal(μ, σ)
```

or empirical distributions obtained from historical production data.

The optimized schedule can then be evaluated under multiple random scenarios.

---

# Data Generation

When real production data is unavailable, PlantSched generates realistic synthetic instances.

Example:

```python
instance = {
    "jobs": 100,
    "machines": 5,
    "products": 12,
    "changeover_matrix": matrix,
    "processing_times": processing_times,
    "due_dates": due_dates
}
```

The simulator can vary:

* Number of jobs
* Number of machines
* Number of products
* Changeover complexity
* Processing-time variability
* Due-date tightness

This makes controlled benchmarking possible.

---

# Example Results

A typical experiment can produce results such as:

```text
                   FCFS       CP-SAT       GA

Makespan            920        710        735
Changeover (min)    260        125        140
OTD (%)              78         96         93
Runtime (sec)          1         48          7
```

The actual results depend on the generated or benchmark instance.

The important objective is to quantify the trade-off between **schedule quality and computational cost**.

---

# Benchmarking

PlantSched supports benchmarking across increasing problem sizes.

```text
              Solution Quality
                     ▲
                     │
          CP-SAT     │████████
                     │
                     │      ██████ GA
                     │
                     └──────────────────► Problem Size
```

The benchmark records:

* Solver runtime
* Makespan
* Optimality gap
* Changeover time
* Tardiness
* OTD
* Utilization

---

# Public Benchmark Support

The system can be extended to support standard job-shop benchmark datasets such as:

* Taillard instances
* OR-Library scheduling instances
* Other public JSSP/FJSSP benchmarks

This allows comparison against established scheduling problems instead of relying exclusively on synthetic data.

---

# Technology Stack

### Optimization

* Python
* OR-Tools CP-SAT
* MILP formulation
* PuLP / Gurobi (optional)

### Metaheuristics

* Genetic Algorithms
* Simulated Annealing

### Simulation

* SimPy
* Monte Carlo simulation

### Data Analysis

* Pandas
* NumPy
* Matplotlib
* Plotly

---

# Project Structure

```text
PlantSched/
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── benchmarks/
│
├── models/
│   ├── cp_sat.py
│   ├── milp.py
│   └── constraints.py
│
├── heuristics/
│   ├── genetic_algorithm.py
│   └── simulated_annealing.py
│
├── simulation/
│   ├── plant.py
│   ├── machine.py
│   └── events.py
│
├── evaluation/
│   ├── metrics.py
│   ├── benchmark.py
│   └── comparison.py
│
├── visualization/
│   ├── gantt.py
│   └── kpi_plots.py
│
├── notebooks/
│   ├── 01_data_generation.ipynb
│   ├── 02_cp_sat.ipynb
│   ├── 03_metaheuristic.ipynb
│   └── 04_simulation.ipynb
│
├── tests/
│
├── requirements.txt
└── README.md
```

---

# Installation

Clone the repository:

```bash
git clone https://github.com/<your-username>/PlantSched.git

cd PlantSched
```

Create a virtual environment:

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

---

# Running the Optimizer

Run a basic CP-SAT scheduling experiment:

```bash
python models/cp_sat.py
```

Run the genetic algorithm:

```bash
python heuristics/genetic_algorithm.py
```

Run the simulation:

```bash
python simulation/plant.py
```

Run the benchmark:

```bash
python evaluation/benchmark.py
```

Generate a Gantt chart:

```bash
python visualization/gantt.py
```

---

# Gantt Chart

The optimized schedule can be visualized using a production Gantt chart:

```text
Time ───────────────────────────────────────────────►

Line 1 | █████ A █████ | ██ B ██ | █████ C █████ |
Line 2 | ███ D ███ | █████ A █████ | ██ B ██       |
Line 3 | █████ B █████ | ███ C ███ | █████ D █████ |
```

This provides an intuitive way for production planners to inspect the resulting schedule.

---

# Practical Manufacturing Applications

PlantSched is applicable to environments such as:

* FMCG production
* Automotive manufacturing
* Consumer electronics
* Chemical processing
* Packaging
* Metal fabrication
* Food processing
* Discrete manufacturing

Typical use cases include:

```text
Product sequencing
       +
Changeover reduction
       +
Capacity planning
       +
Due-date management
       =
Production schedule optimization
```

---

# Key Engineering Questions

The project explores several practical operations-research questions:

### Why is job-shop scheduling difficult?

General job-shop scheduling is computationally hard because the number of possible job-machine sequences grows rapidly as the number of jobs and machines increases.

### When should exact optimization be used?

For smaller instances where solution quality is more important than runtime.

### When should heuristics be used?

For large instances where obtaining a high-quality solution quickly is more valuable than proving global optimality.

### Why minimize changeovers?

Changeovers consume production capacity without producing sellable output.

### What happens with stochastic processing times?

A schedule optimized for deterministic times may become infeasible or cause delays when actual processing times vary. Simulation and robust optimization can help evaluate this risk.

---

# Future Improvements

Potential extensions include:

* Flexible job-shop scheduling
* Multi-objective optimization
* Stochastic processing times
* Robust scheduling
* Predictive machine maintenance integration
* Dynamic rescheduling
* Real-time production events
* Reinforcement learning for scheduling
* Multi-plant optimization
* Energy-aware scheduling
* Inventory-aware scheduling
* Workforce constraints
* Setup crew availability
* Real-time dashboard for production planners

---

# Project Goal

PlantSched aims to bridge the gap between **operations research and practical manufacturing engineering**.

Instead of relying on simple sequencing rules such as FCFS or shortest-processing-time scheduling, the system explicitly models:

```text
Machines
+ Jobs
+ Processing Times
+ Changeovers
+ Due Dates
+ Capacity Constraints
```

and determines a schedule that improves measurable plant-level KPIs.

The project ultimately evaluates an important practical trade-off:

> **How much schedule quality can be gained from sophisticated optimization, and when does the computational cost of exact optimization justify switching to faster heuristic methods?**

---

## Author

**Ashish Rawal**

Project focused on **manufacturing systems, operations research, production scheduling, mathematical optimization, and discrete-event simulation**.
