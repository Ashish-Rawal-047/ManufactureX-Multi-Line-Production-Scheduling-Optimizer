# Discrete-Event Simulation & Robustness Analysis

## Separation of Optimization and Simulation

Deterministic optimization models assume nominal processing times, exact arrival times, and zero unplanned breakdowns. PlantSched's `plantsched/simulation/` package executes any validated `Schedule` inside a stochastic **SimPy** discrete-event plant to test real-world schedule resilience.

## SimPy Plant Mechanics (`plantsched/simulation/plant.py`)

Each machine is modeled as a `simpy.Resource(env, capacity=1)` running a sequential dispatch process over its planned job queue:

1. **Stochastic Job Arrival**: Actual arrival is `job.arrival_time + delay`, where arrival delays occur with probability `arrival_delay_prob` drawn from `Uniform(0.5, max_arrival_delay)`.
2. **Resource Acquisition & Planned Downtime**: The job waits for both its actual arrival and the machine resource, then skips any overlapping planned `DowntimeWindow`.
3. **Sequence-Dependent Setup**: `env.timeout(setup_duration)` using the machine's live `current_product`.
4. **Stochastic Production**: Processing time is sampled as `max(0.25 * nominal, Normal(nominal, cv * nominal))` and executed via `env.timeout(proc_dur)`.
5. **Unplanned Breakdowns**: If `enable_downtime=True`, failure occurs with probability $1 - \exp(-\text{proc\_dur} / \text{MTBF})$ and adds an `Exponential(MTTR)` repair delay.

## Monte Carlo Robustness (`plantsched/simulation/monte_carlo.py`)

Runs $R$ independent replications (deterministic seeds `base_seed + r`) and quantifies:
- Mean, standard deviation, P95, and worst-case simulated makespan.
- Mean and worst-case simulated tardiness.
- Mean simulated OTD% and probability of achieving 100% or $\ge 90\%$ on-time delivery.
- Mean waiting time and schedule deviation (`actual_completion - planned_completion`).
