"""Monte Carlo robustness analysis over stochastic SimPy plant simulations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from plantsched.core.config import SimulationConfig
from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule
from plantsched.simulation.plant import simulate_schedule


@dataclass
class MonteCarloResult:
    """Statistical robustness summary across Monte Carlo simulation replications."""

    problem_name: str
    algorithm: str
    num_replications: int
    planned_makespan: float
    avg_makespan: float
    std_makespan: float
    min_makespan: float
    p95_makespan: float
    worst_case_makespan: float
    planned_total_tardiness: float
    avg_tardiness: float
    std_tardiness: float
    worst_case_tardiness: float
    planned_otd_pct: float
    avg_otd_pct: float
    prob_all_on_time: float
    prob_otd_above_90: float
    avg_utilization_pct: float
    avg_waiting_time: float
    avg_schedule_deviation: float
    replications_df: pd.DataFrame

    def to_summary_dict(self) -> dict:
        return {
            "Algorithm": self.algorithm,
            "Replications": self.num_replications,
            "PlannedMakespan": round(self.planned_makespan, 2),
            "AvgSimMakespan": round(self.avg_makespan, 2),
            "StdSimMakespan": round(self.std_makespan, 2),
            "P95Makespan": round(self.p95_makespan, 2),
            "WorstMakespan": round(self.worst_case_makespan, 2),
            "PlannedTardiness": round(self.planned_total_tardiness, 2),
            "AvgSimTardiness": round(self.avg_tardiness, 2),
            "WorstTardiness": round(self.worst_case_tardiness, 2),
            "PlannedOTD_pct": round(self.planned_otd_pct, 2),
            "AvgSimOTD_pct": round(self.avg_otd_pct, 2),
            "ProbAllOnTime_pct": round(self.prob_all_on_time * 100.0, 2),
            "ProbOTD_ge_90_pct": round(self.prob_otd_above_90 * 100.0, 2),
            "AvgUtilization_pct": round(self.avg_utilization_pct, 2),
            "AvgWaitTime": round(self.avg_waiting_time, 2),
            "AvgDeviation": round(self.avg_schedule_deviation, 2),
        }


def run_monte_carlo(
    problem: SchedulingProblem,
    schedule: Schedule,
    config: SimulationConfig | None = None,
) -> MonteCarloResult:
    """Evaluate schedule robustness across multiple stochastic simulation scenarios."""
    cfg = config or SimulationConfig()
    rows: list[dict] = []

    for rep in range(cfg.num_replications):
        rep_seed = cfg.random_seed + rep
        res = simulate_schedule(problem, schedule, config=cfg, seed=rep_seed)
        rows.append(
            {
                "replication": rep,
                "seed": rep_seed,
                "simulated_makespan": res.simulated_makespan,
                "simulated_total_tardiness": res.simulated_total_tardiness,
                "simulated_otd_pct": res.simulated_otd_pct,
                "simulated_utilization_pct": res.simulated_utilization_pct,
                "mean_waiting_time": res.mean_waiting_time,
                "mean_schedule_deviation": res.mean_schedule_deviation,
                "max_schedule_deviation": res.max_schedule_deviation,
            }
        )

    df = pd.DataFrame(rows)
    makespans = df["simulated_makespan"].to_numpy()
    tardiness = df["simulated_total_tardiness"].to_numpy()
    otds = df["simulated_otd_pct"].to_numpy()

    return MonteCarloResult(
        problem_name=problem.name,
        algorithm=schedule.algorithm,
        num_replications=cfg.num_replications,
        planned_makespan=schedule.makespan,
        avg_makespan=float(np.mean(makespans)),
        std_makespan=float(np.std(makespans, ddof=1)) if len(makespans) > 1 else 0.0,
        min_makespan=float(np.min(makespans)),
        p95_makespan=float(np.percentile(makespans, 95)),
        worst_case_makespan=float(np.max(makespans)),
        planned_total_tardiness=schedule.total_tardiness,
        avg_tardiness=float(np.mean(tardiness)),
        std_tardiness=float(np.std(tardiness, ddof=1)) if len(tardiness) > 1 else 0.0,
        worst_case_tardiness=float(np.max(tardiness)),
        planned_otd_pct=(
            sum(1 for sj in schedule.scheduled_jobs if sj.tardiness <= 1e-6)
            / len(problem.jobs)
            * 100.0
        ),
        avg_otd_pct=float(np.mean(otds)),
        prob_all_on_time=float(np.mean(otds >= 100.0 - 1e-9)),
        prob_otd_above_90=float(np.mean(otds >= 90.0 - 1e-9)),
        avg_utilization_pct=float(df["simulated_utilization_pct"].mean()),
        avg_waiting_time=float(df["mean_waiting_time"].mean()),
        avg_schedule_deviation=float(df["mean_schedule_deviation"].mean()),
        replications_df=df,
    )
