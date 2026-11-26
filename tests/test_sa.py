"""Tests for the Simulated Annealing (SA) optimizer."""

from plantsched.core import ObjectiveWeights, SAConfig, ScheduleValidator, SolverStatus
from plantsched.data import InstanceGeneratorConfig, generate_instance
from plantsched.heuristics import solve_simulated_annealing


def test_sa_solves_reproducibly_and_tracks_best():
    problem = generate_instance(
        InstanceGeneratorConfig(num_jobs=20, num_machines=3, num_products=6, seed=17, include_downtime=True)
    )
    cfg = SAConfig(
        initial_temp=150.0,
        cooling_rate=0.98,
        min_temp=0.5,
        max_iterations=500,
        random_seed=42,
        weights=ObjectiveWeights(),
    )
    s1 = solve_simulated_annealing(problem, cfg)
    s2 = solve_simulated_annealing(problem, cfg)

    assert s1.solver_status == SolverStatus.FEASIBLE
    val = ScheduleValidator.validate(problem, s1)
    assert val.is_valid, val.errors
    assert s1.objective_value == s2.objective_value

    history = s1.metadata["convergence_history"]
    assert len(history) >= 2
    # Best objective must be monotonically non-increasing
    best_series = [h["best_objective"] for h in history]
    assert all(best_series[i] <= best_series[i - 1] + 1e-9 for i in range(1, len(best_series)))
