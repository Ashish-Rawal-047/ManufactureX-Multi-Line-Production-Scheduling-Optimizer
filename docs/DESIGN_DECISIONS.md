# Key Engineering Design Decisions

1. **Immediate-Predecessor `AddCircuit` vs. Pairwise Big-M in CP-SAT**
   - *Decision*: Modeled setups via per-machine `AddCircuit` combined with `AddNoOverlap`.
   - *Why*: Pairwise precedence variables $y_{ij}$ cannot easily distinguish *immediate* predecessors from *transitive* predecessors without additional flow constraints. `AddCircuit` enforces a single Hamiltonian path per machine, directly binding each job's `setup_duration` to its immediate predecessor (or `machine.initial_product` for the first job) while `AddNoOverlap` handles downtime intervals cleanly.

2. **Dual-Vector Chromosome `(job_sequence, machine_choices)` for GA & SA**
   - *Decision*: Explicit machine choices alongside job permutation rather than permutation-only greedy assignment.
   - *Why*: Greedy machine selection cannot intentionally delay a job on a busy line to preserve a same-product campaign (`A -> A -> A`). Explicit machine choices enable metaheuristics to discover changeover-saving assignments while remaining 100% valid under OX1 + uniform crossover.

3. **Shared `compute_earliest_slot` & `ScheduleValidator`**
   - *Decision*: Centralized slot placement in `core/scheduling_utils.py` and independent validation in `core/validator.py`.
   - *Why*: Eliminates duplicated feasibility logic across FCFS, GA, and SA, and guarantees every reported KPI comes from a schedule verified against all eligibility, setup, overlap, arrival, and downtime rules.

4. **Strict Status & OEE Reporting**
   - *Decision*: `SolverStatus` distinguishes `OPTIMAL` from `FEASIBLE`; `MachineKPI` reports total utilization (`setup + processing`) separately from processing-only utilization; OEE notes explicitly that Quality = 100% is assumed.
   - *Why*: Prevents misrepresenting time-limited incumbents as mathematical optima or conflating machine utilization with OEE.
