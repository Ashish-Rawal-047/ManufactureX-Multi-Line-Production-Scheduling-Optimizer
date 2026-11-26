"""Fair multi-algorithm comparison framework on identical instances."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from plantsched.baselines.fcfs import solve_fcfs
from plantsched.core.config import (
    CPSATConfig,
    GAConfig,
    MILPConfig,
    ObjectiveWeights,
    SAConfig,
)
from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule
from plantsched.evaluation.metrics import ScheduleKPIs, evaluate_schedule
from plantsched.heuristics.genetic_algorithm import solve_genetic_algorithm
from plantsched.heuristics.simulated_annealing import solve_simulated_annealing
from plantsched.optimization.cp_sat import solve_cp_sat
from plantsched.optimization.milp import solve_milp


@dataclass
class ComparisonResult:
    """Schedules, KPIs, and summary table from comparing algorithms on one instance."""

    problem_name: str
    schedules: dict[str, Schedule]
    kpis: dict[str, ScheduleKPIs]
    summary_table: pd.DataFrame


def compare_algorithms(
    problem: SchedulingProblem,
    algorithms: tuple[str, ...] = ("FCFS", "CP-SAT", "MILP", "GA", "SA"),
    weights: ObjectiveWeights | None = None,
    cp_sat_config: CPSATConfig | None = None,
    milp_config: MILPConfig | None = None,
    ga_config: GAConfig | None = None,
    sa_config: SAConfig | None = None,
) -> ComparisonResult:
    """Run selected algorithms on the identical `problem` and `weights`."""
    w = weights or ObjectiveWeights()
    schedules: dict[str, Schedule] = {}
    kpis: dict[str, ScheduleKPIs] = {}
    rows: list[dict] = []

    for algo in algorithms:
        key = algo.upper()
        if key == "FCFS":
            sched = solve_fcfs(problem, weights=w)
        elif key in ("CP-SAT", "CPSAT"):
            cfg = cp_sat_config or CPSATConfig(weights=w)
            cfg = CPSATConfig(
                max_time_seconds=cfg.max_time_seconds,
                num_workers=cfg.num_workers,
                random_seed=cfg.random_seed,
                weights=w,
                log_search_progress=cfg.log_search_progress,
            )
            sched = solve_cp_sat(problem, config=cfg)
        elif key == "MILP":
            cfg_m = milp_config or MILPConfig(weights=w)
            cfg_m = MILPConfig(
                max_time_seconds=cfg_m.max_time_seconds,
                msg=cfg_m.msg,
                weights=w,
                include_downtime=cfg_m.include_downtime,
            )
            sched = solve_milp(problem, config=cfg_m)
        elif key in ("GA", "GENETICALGORITHM"):
            cfg_g = ga_config or GAConfig(weights=w)
            cfg_g = GAConfig(
                population_size=cfg_g.population_size,
                generations=cfg_g.generations,
                crossover_prob=cfg_g.crossover_prob,
                mutation_prob=cfg_g.mutation_prob,
                tournament_size=cfg_g.tournament_size,
                elitism_count=cfg_g.elitism_count,
                random_seed=cfg_g.random_seed,
                weights=w,
                early_stop_generations=cfg_g.early_stop_generations,
            )
            sched = solve_genetic_algorithm(problem, config=cfg_g)
        elif key in ("SA", "SIMULATEDANNEALING"):
            cfg_s = sa_config or SAConfig(weights=w)
            cfg_s = SAConfig(
                initial_temp=cfg_s.initial_temp,
                cooling_rate=cfg_s.cooling_rate,
                min_temp=cfg_s.min_temp,
                max_iterations=cfg_s.max_iterations,
                random_seed=cfg_s.random_seed,
                weights=w,
            )
            sched = solve_simulated_annealing(problem, config=cfg_s)
        else:
            raise ValueError(f"Unknown algorithm: {algo!r}")

        kpi = evaluate_schedule(problem, sched, weights=w)
        schedules[sched.algorithm] = sched
        kpis[sched.algorithm] = kpi
        rows.append(kpi.to_summary_dict())

    summary_df = pd.DataFrame(rows)
    return ComparisonResult(
        problem_name=problem.name,
        schedules=schedules,
        kpis=kpis,
        summary_table=summary_df,
    )
