# Scheduling Algorithms Implemented

## 1. Baseline — First-Come First-Served (FCFS)
- Orders jobs chronologically by `(arrival_time, job_id)`.
- Assigns each job to the eligible machine yielding the earliest feasible completion time (`compute_earliest_slot`), accounting for sequence-dependent changeovers, `available_from`, `available_until`, and `downtime_windows`.
- Complexity: $O(N \log N + N \cdot |M| \cdot |W|)$. Always returns `FEASIBLE` (or `INFEASIBLE` if `available_until` cannot be satisfied).

## 2. Exact Solver — OR-Tools CP-SAT
- Uses `AddExactlyOne` for eligible machine selection, `AddNoOverlap` over optional `[setup_start, completion]` intervals and fixed downtime intervals, and per-machine `AddCircuit` for immediate-predecessor setup tracking.
- Warm-started with FCFS solution hints (`AddHint`) when FCFS is feasible.
- Automatically scales fractional inputs (100x) into integer arithmetic when needed, and divides back for exact `objective_value` and `best_bound`.
- Strictly distinguishes `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `UNKNOWN`, and `MODEL_INVALID`.

## 3. Exact Solver — PuLP / CBC MILP
- Implements the arc-flow immediate-predecessor MILP with Big-$M$ precedence (`M = problem.compute_horizon()`) and optional binary disjunctive downtime constraints.
- Mathematically equivalent to CP-SAT on small instances (verified by unit tests checking exact objective parity when both prove `OPTIMAL`).
- Computational limitation: $O(N^2 |M|)$ binary `y[i,j,m]` variables and Big-$M$ relaxations make MILP suitable mainly for small instances ($N \le 20\text{--}25$).

## 4. Genetic Algorithm (GA)
- Dual-vector `Chromosome(job_sequence, machine_choices)` encoding both job dispatch order and eligible machine assignment.
- Seeded with domain heuristics (FCFS, EDD, SPT, product-grouped, priority-weighted) plus randomized individuals.
- Uses **Order Crossover (OX1)** on `job_sequence` and **Uniform Crossover** on `machine_choices`, guaranteeing 100% valid permutations and eligible machines without duplicate or missing jobs.
- Mutation applies swap, insert, product-clustering moves, and eligible-machine reassignments, followed by tournament selection and elitism.

## 5. Simulated Annealing (SA)
- Operates on the same `Chromosome` representation, initialized from the best greedy heuristic seed.
- Neighborhood moves: `swap`, `insert`, `product_cluster` (moves a job next to same-product jobs), and `reassign` (changes eligible machine).
- Geometric cooling schedule (`T <- T * cooling_rate`) with Boltzmann acceptance $\exp(-\Delta / T)$ and independent best-solution tracking.
