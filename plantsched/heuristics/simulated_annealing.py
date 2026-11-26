"""Simulated Annealing (SA) optimizer for multi-line production scheduling."""

from __future__ import annotations

import math
import random
import time

from plantsched.core.config import SAConfig, SolverStatus
from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule
from plantsched.heuristics.decoder import (
    Chromosome,
    build_greedy_chromosome,
    decode_chromosome,
)


def _generate_neighbor(
    problem: SchedulingProblem,
    current: Chromosome,
    rng: random.Random,
) -> Chromosome:
    """Create a neighboring feasible chromosome using sequence or machine moves."""
    seq = list(current.job_sequence)
    machines = dict(current.machine_choices)
    n = len(seq)

    multi_elig = [j for j in seq if len(problem.get_eligible_machines(j)) > 1]
    moves = ["swap", "insert", "product_cluster"]
    if multi_elig:
        moves.append("reassign")

    move = rng.choice(moves)
    if move == "swap" and n >= 2:
        i, j = rng.sample(range(n), 2)
        seq[i], seq[j] = seq[j], seq[i]
    elif move == "insert" and n >= 2:
        i, j = rng.sample(range(n), 2)
        gene = seq.pop(i)
        seq.insert(j, gene)
    elif move == "product_cluster" and n >= 2:
        idx = rng.randrange(n)
        prod = problem.jobs[seq[idx]].product_id
        same_prod = [k for k in range(n) if k != idx and problem.jobs[seq[k]].product_id == prod]
        if same_prod:
            target = rng.choice(same_prod)
            gene = seq.pop(idx)
            seq.insert(target, gene)
        else:
            i, j = rng.sample(range(n), 2)
            seq[i], seq[j] = seq[j], seq[i]
    elif move == "reassign" and multi_elig:
        j_id = rng.choice(multi_elig)
        alts = [m for m in problem.get_eligible_machines(j_id) if m != machines[j_id]]
        if alts:
            machines[j_id] = rng.choice(alts)

    return Chromosome(job_sequence=seq, machine_choices=machines)


def solve_simulated_annealing(
    problem: SchedulingProblem,
    config: SAConfig | None = None,
) -> Schedule:
    """Optimize schedule using Simulated Annealing with independent best tracking."""
    t0 = time.perf_counter()
    cfg = config or SAConfig()
    rng = random.Random(cfg.random_seed)

    jobs = list(problem.jobs.values())
    candidate_sequences = [
        [j.job_id for j in sorted(jobs, key=lambda j: (j.arrival_time, j.job_id))],
        [j.job_id for j in sorted(jobs, key=lambda j: (j.due_date, -j.priority, j.job_id))],
        [j.job_id for j in sorted(jobs, key=lambda j: (j.product_id, j.due_date, j.job_id))],
    ]

    best_init_chrom: Chromosome | None = None
    best_init_obj = float("inf")
    for seq in candidate_sequences:
        ch = build_greedy_chromosome(problem, seq, weights=cfg.weights)
        _, obj = decode_chromosome(problem, ch, cfg.weights, algorithm_name="SimulatedAnnealing")
        if obj < best_init_obj:
            best_init_obj = obj
            best_init_chrom = ch

    assert best_init_chrom is not None
    current = best_init_chrom.copy()
    current_obj = best_init_obj

    best = current.copy()
    best_obj = current_obj

    temp = float(cfg.initial_temp)
    history: list[dict[str, float]] = [
        {
            "iteration": 0,
            "temperature": temp,
            "current_objective": current_obj,
            "best_objective": best_obj,
        }
    ]

    record_stride = max(1, cfg.max_iterations // 200)
    iterations_run = 0

    for it in range(1, cfg.max_iterations + 1):
        if temp < cfg.min_temp:
            break
        iterations_run = it

        neighbor = _generate_neighbor(problem, current, rng)
        _, neighbor_obj = decode_chromosome(
            problem, neighbor, cfg.weights, algorithm_name="SimulatedAnnealing"
        )

        if neighbor_obj < float("inf"):
            delta = neighbor_obj - current_obj
            if delta <= 0 or (temp > 0 and rng.random() < math.exp(-delta / temp)):
                current = neighbor
                current_obj = neighbor_obj

                if current_obj < best_obj - 1e-9:
                    best = current.copy()
                    best_obj = current_obj

        temp *= cfg.cooling_rate
        if it % record_stride == 0 or it == cfg.max_iterations or temp < cfg.min_temp:
            history.append(
                {
                    "iteration": it,
                    "temperature": temp,
                    "current_objective": current_obj,
                    "best_objective": best_obj,
                }
            )

    runtime = time.perf_counter() - t0
    best_schedule, final_obj = decode_chromosome(
        problem,
        best,
        cfg.weights,
        algorithm_name="SimulatedAnnealing",
        runtime_seconds=runtime,
    )
    if best_schedule.solver_status == SolverStatus.INFEASIBLE:
        return best_schedule

    best_schedule.objective_value = final_obj
    best_schedule.metadata = {
        "iterations_run": iterations_run,
        "initial_temp": cfg.initial_temp,
        "final_temp": temp,
        "cooling_rate": cfg.cooling_rate,
        "random_seed": cfg.random_seed,
        "convergence_history": history,
    }
    return best_schedule
