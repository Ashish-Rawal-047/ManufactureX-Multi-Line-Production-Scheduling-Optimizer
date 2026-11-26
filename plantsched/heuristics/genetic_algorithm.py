"""Genetic Algorithm (GA) optimizer for multi-line production scheduling."""

from __future__ import annotations

import random
import time

from plantsched.core.config import GAConfig, SolverStatus
from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule
from plantsched.heuristics.decoder import (
    Chromosome,
    build_greedy_chromosome,
    decode_chromosome,
)


def order_crossover(parent1: list[str], parent2: list[str], rng: random.Random) -> list[str]:
    """Order Crossover (OX1) preserving permutation validity with zero duplicates."""
    n = len(parent1)
    if n <= 2:
        return list(parent1)
    i, j = sorted(rng.sample(range(n), 2))
    child: list[str | None] = [None] * n
    child[i : j + 1] = parent1[i : j + 1]
    in_slice = set(parent1[i : j + 1])

    fill_items = [gene for gene in parent2 if gene not in in_slice]
    fill_idx = 0
    for pos in list(range(j + 1, n)) + list(range(0, i)):
        child[pos] = fill_items[fill_idx]
        fill_idx += 1
    return [g for g in child if g is not None]


def uniform_machine_crossover(
    m1: dict[str, str], m2: dict[str, str], rng: random.Random
) -> dict[str, str]:
    """Uniform crossover over eligible machine assignments."""
    return {
        j_id: (m1[j_id] if rng.random() < 0.5 else m2[j_id])
        for j_id in m1
    }


def mutate_chromosome(
    problem: SchedulingProblem,
    chrom: Chromosome,
    mutation_prob: float,
    rng: random.Random,
) -> Chromosome:
    """Apply swap/insert sequence mutation and eligible-machine reassignment mutation."""
    seq = list(chrom.job_sequence)
    machines = dict(chrom.machine_choices)
    n = len(seq)

    if rng.random() < mutation_prob and n >= 2:
        move_type = rng.choice(["swap", "insert", "product_group"])
        if move_type == "swap":
            i, j = rng.sample(range(n), 2)
            seq[i], seq[j] = seq[j], seq[i]
        elif move_type == "insert":
            i, j = rng.sample(range(n), 2)
            gene = seq.pop(i)
            seq.insert(j, gene)
        else:
            # Move a random job adjacent to another job with the same product
            idx = rng.randrange(n)
            prod = problem.jobs[seq[idx]].product_id
            same_prod = [k for k in range(n) if k != idx and problem.jobs[seq[k]].product_id == prod]
            if same_prod:
                target = rng.choice(same_prod)
                gene = seq.pop(idx)
                insert_at = target if target < idx else target
                seq.insert(insert_at, gene)
            else:
                i, j = rng.sample(range(n), 2)
                seq[i], seq[j] = seq[j], seq[i]

    if rng.random() < mutation_prob:
        multi_elig = [j for j in seq if len(problem.get_eligible_machines(j)) > 1]
        if multi_elig:
            k_mut = min(len(multi_elig), max(1, n // 15))
            for j_id in rng.sample(multi_elig, k_mut):
                alts = [m for m in problem.get_eligible_machines(j_id) if m != machines[j_id]]
                if alts:
                    machines[j_id] = rng.choice(alts)

    return Chromosome(job_sequence=seq, machine_choices=machines)


def _seed_sequences(problem: SchedulingProblem, rng: random.Random, count: int) -> list[list[str]]:
    jobs = list(problem.jobs.values())
    seeds: list[list[str]] = [
        [j.job_id for j in sorted(jobs, key=lambda j: (j.arrival_time, j.job_id))],
        [j.job_id for j in sorted(jobs, key=lambda j: (j.due_date, -j.priority, j.job_id))],
        [j.job_id for j in sorted(jobs, key=lambda j: (j.processing_time, j.due_date, j.job_id))],
        [j.job_id for j in sorted(jobs, key=lambda j: (j.product_id, j.due_date, j.job_id))],
        [j.job_id for j in sorted(jobs, key=lambda j: (-j.priority, j.due_date, j.job_id))],
    ]
    base = [j.job_id for j in jobs]
    while len(seeds) < count:
        perm = list(base)
        rng.shuffle(perm)
        seeds.append(perm)
    return seeds[:count]


def solve_genetic_algorithm(
    problem: SchedulingProblem,
    config: GAConfig | None = None,
) -> Schedule:
    """Optimize schedule using a permutation + machine-assignment Genetic Algorithm."""
    t0 = time.perf_counter()
    cfg = config or GAConfig()
    rng = random.Random(cfg.random_seed)

    # 1. Initialize population with domain-informed seeds + random individuals
    sequences = _seed_sequences(problem, rng, cfg.population_size)
    population: list[Chromosome] = []
    for idx, seq in enumerate(sequences):
        if idx < min(8, cfg.population_size):
            chrom = build_greedy_chromosome(problem, seq, weights=cfg.weights)
        else:
            m_choices = {
                j_id: rng.choice(problem.get_eligible_machines(j_id))
                for j_id in seq
            }
            chrom = Chromosome(job_sequence=seq, machine_choices=m_choices)
        population.append(chrom)

    def evaluate(ch: Chromosome) -> float:
        _, obj = decode_chromosome(problem, ch, cfg.weights, algorithm_name="GeneticAlgorithm")
        return obj

    fitness = [evaluate(ind) for ind in population]
    best_idx = min(range(len(population)), key=lambda i: fitness[i])
    best_chrom = population[best_idx].copy()
    best_obj = fitness[best_idx]

    history: list[dict[str, float]] = [
        {"generation": 0, "best_objective": best_obj, "mean_objective": sum(fitness) / len(fitness)}
    ]
    no_improve = 0

    # 2. Evolutionary loop
    for gen in range(1, cfg.generations + 1):
        ranked_indices = sorted(range(len(population)), key=lambda i: fitness[i])
        next_pop: list[Chromosome] = [
            population[i].copy() for i in ranked_indices[: max(1, cfg.elitism_count)]
        ]

        def tournament_select() -> Chromosome:
            k = min(cfg.tournament_size, len(population))
            contestants = rng.sample(range(len(population)), k)
            winner = min(contestants, key=lambda idx: fitness[idx])
            return population[winner]

        while len(next_pop) < cfg.population_size:
            p1 = tournament_select()
            p2 = tournament_select()
            if rng.random() < cfg.crossover_prob:
                c_seq = order_crossover(p1.job_sequence, p2.job_sequence, rng)
                c_mach = uniform_machine_crossover(p1.machine_choices, p2.machine_choices, rng)
                child = Chromosome(job_sequence=c_seq, machine_choices=c_mach)
            else:
                child = p1.copy()

            child = mutate_chromosome(problem, child, cfg.mutation_prob, rng)
            next_pop.append(child)

        population = next_pop
        fitness = [evaluate(ind) for ind in population]
        gen_best_idx = min(range(len(population)), key=lambda i: fitness[i])
        gen_best_obj = fitness[gen_best_idx]

        if gen_best_obj < best_obj - 1e-9:
            best_obj = gen_best_obj
            best_chrom = population[gen_best_idx].copy()
            no_improve = 0
        else:
            no_improve += 1

        finite_vals = [f for f in fitness if f < float("inf")]
        mean_val = sum(finite_vals) / len(finite_vals) if finite_vals else float("inf")
        history.append(
            {"generation": gen, "best_objective": best_obj, "mean_objective": mean_val}
        )

        if cfg.early_stop_generations is not None and no_improve >= cfg.early_stop_generations:
            break

    runtime = time.perf_counter() - t0
    best_schedule, final_obj = decode_chromosome(
        problem,
        best_chrom,
        cfg.weights,
        algorithm_name="GeneticAlgorithm",
        runtime_seconds=runtime,
    )
    if best_schedule.solver_status == SolverStatus.INFEASIBLE:
        return best_schedule

    best_schedule.objective_value = final_obj
    best_schedule.metadata = {
        "generations_run": len(history) - 1,
        "population_size": cfg.population_size,
        "random_seed": cfg.random_seed,
        "convergence_history": history,
    }
    return best_schedule
