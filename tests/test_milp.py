"""Tests for PuLP MILP formulation and exact parity with CP-SAT."""

import pytest

from plantsched.core import (
    CPSATConfig,
    MILPConfig,
    ObjectiveWeights,
    ScheduleValidator,
    SolverStatus,
)
from plantsched.data import InstanceGeneratorConfig, generate_instance
from plantsched.optimization import solve_cp_sat, solve_milp


def test_milp_matches_cp_sat_optimum_on_small_instance():
    problem = generate_instance(
        InstanceGeneratorConfig(
            num_jobs=5,
            num_machines=2,
            num_products=3,
            seed=21,
            include_downtime=True,
        )
    )
    weights = ObjectiveWeights(alpha=1.0, beta=1.0, gamma=0.5)

    cp_sched = solve_cp_sat(
        problem,
        CPSATConfig(max_time_seconds=20.0, weights=weights),
    )
    milp_sched = solve_milp(
        problem,
        MILPConfig(max_time_seconds=20.0, weights=weights, include_downtime=True),
    )

    assert cp_sched.solver_status == SolverStatus.OPTIMAL
    assert milp_sched.solver_status == SolverStatus.OPTIMAL
    assert ScheduleValidator.validate(problem, cp_sched).is_valid
    assert ScheduleValidator.validate(problem, milp_sched).is_valid
    assert milp_sched.objective_value == pytest.approx(cp_sched.objective_value, abs=1e-4)


def test_milp_time_limit_never_mislabels_optimal():
    problem = generate_instance(InstanceGeneratorConfig(num_jobs=20, num_machines=3, num_products=6, seed=42))
    milp_sched = solve_milp(problem, MILPConfig(max_time_seconds=2.0))
    assert milp_sched.solver_status in (SolverStatus.FEASIBLE, SolverStatus.UNKNOWN)
    if milp_sched.has_solution:
        assert ScheduleValidator.validate(problem, milp_sched).is_valid

