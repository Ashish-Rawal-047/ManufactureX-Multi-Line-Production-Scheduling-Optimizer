"""Tests for the Genetic Algorithm (GA) optimizer."""

import random

from plantsched.core import GAConfig, ObjectiveWeights, ScheduleValidator, SolverStatus
from plantsched.data import InstanceGeneratorConfig, generate_instance
from plantsched.heuristics import (
    Chromosome,
    mutate_chromosome,
    order_crossover,
    solve_genetic_algorithm,
    uniform_machine_crossover,
    validate_chromosome,
)


def test_ga_operators_preserve_validity():
    problem = generate_instance(InstanceGeneratorConfig(num_jobs=15, num_machines=3, num_products=5, seed=3))
    rng = random.Random(42)
    jobs = list(problem.jobs.keys())
    p1_seq = list(jobs)
    p2_seq = list(reversed(jobs))
    rng.shuffle(p2_seq)

    child_seq = order_crossover(p1_seq, p2_seq, rng)
    assert len(child_seq) == len(jobs)
    assert set(child_seq) == set(jobs)

    m1 = {j: problem.get_eligible_machines(j)[0] for j in jobs}
    m2 = {j: problem.get_eligible_machines(j)[-1] for j in jobs}
    child_m = uniform_machine_crossover(m1, m2, rng)
    chrom = Chromosome(job_sequence=child_seq, machine_choices=child_m)
    assert validate_chromosome(problem, chrom)

    mutated = mutate_chromosome(problem, chrom, mutation_prob=1.0, rng=rng)
    assert validate_chromosome(problem, mutated)


def test_ga_solves_and_is_reproducible():
    problem = generate_instance(InstanceGeneratorConfig(num_jobs=20, num_machines=3, num_products=6, seed=11))
    cfg = GAConfig(
        population_size=30,
        generations=40,
        random_seed=99,
        weights=ObjectiveWeights(),
    )
    s1 = solve_genetic_algorithm(problem, cfg)
    s2 = solve_genetic_algorithm(problem, cfg)

    assert s1.solver_status == SolverStatus.FEASIBLE
    val = ScheduleValidator.validate(problem, s1)
    assert val.is_valid, val.errors
    assert s1.objective_value == s2.objective_value
    assert len(s1.metadata["convergence_history"]) == 41
