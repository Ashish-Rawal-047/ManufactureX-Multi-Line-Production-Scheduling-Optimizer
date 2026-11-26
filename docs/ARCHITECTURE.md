# PlantSched System Architecture

## Overview

PlantSched separates **domain modeling**, **exact optimization**, **metaheuristics**, **validation & KPIs**, **discrete-event simulation**, and **visualization** into independent layers communicating through two canonical contracts:

1. `SchedulingProblem` (`plantsched/core/problem.py`) — immutable problem specification (products, machines, jobs, directional changeover matrix, downtime windows).
2. `Schedule` (`plantsched/core/schedule.py`) — standardized output produced by every algorithm (FCFS, CP-SAT, MILP, GA, SA) and verified by `ScheduleValidator`.

## Data Flow

```text
Production Orders / Generator (plantsched/data/)
        │
        ▼
Validation & Preprocessing (plantsched/core/problem.py, data/preprocessing.py)
        │
        ▼
SchedulingProblem (Common Problem Contract)
        │
        ├──► FCFS Baseline (plantsched/baselines/fcfs.py)
        ├──► OR-Tools CP-SAT (plantsched/optimization/cp_sat.py)
        ├──► PuLP/CBC MILP (plantsched/optimization/milp.py)
        ├──► Genetic Algorithm (plantsched/heuristics/genetic_algorithm.py)
        └──► Simulated Annealing (plantsched/heuristics/simulated_annealing.py)
        │
        ▼
Schedule (Common Output Contract)
        │
        ▼
ScheduleValidator (plantsched/core/validator.py)
        │
        ▼
KPI Engine (plantsched/evaluation/metrics.py)
        │
        ├──► SimPy Discrete-Event Plant (plantsched/simulation/plant.py)
        │         └──► Monte Carlo Robustness (plantsched/simulation/monte_carlo.py)
        └──► Gantt & KPI Visualization (plantsched/visualization/)
```

## Package Layout

- `plantsched/core/`: Domain entities, configuration dataclasses, `SchedulingProblem`, `Schedule`, `ScheduleValidator`, and `compute_earliest_slot`.
- `plantsched/data/`: Reproducible synthetic instance generator, JSON/CSV serialization, and feature preprocessing.
- `plantsched/baselines/`: First-Come First-Served scheduler respecting all operational constraints.
- `plantsched/optimization/`: Exact CP-SAT and MILP models plus integer scaling and gap utilities.
- `plantsched/heuristics/`: Dual-vector `(job_sequence, machine_choices)` decoder, GA, and SA.
- `plantsched/evaluation/`: KPI engine, fair single-instance comparison, and multi-scale benchmarking.
- `plantsched/simulation/`: SimPy machine resources, stochastic disturbances, and Monte Carlo runner.
- `plantsched/visualization/`: Static Matplotlib and interactive Plotly Gantt and KPI charts.
