"""Tests for Google OR-Tools CP-SAT exact scheduling model."""

from plantsched.core import (
    CPSATConfig,
    ChangeoverMatrix,
    DowntimeWindow,
    Job,
    Machine,
    ObjectiveWeights,
    Product,
    ScheduleValidator,
    SchedulingProblem,
    SolverStatus,
)
from plantsched.data import InstanceGeneratorConfig, generate_instance
from plantsched.optimization import solve_cp_sat


def test_cp_sat_groups_products_to_minimize_changeover():
    # Single machine with initial_product=A; jobs arrive at 0 for A, B, A, B.
    # Optimal changeover sequence is A -> A -> B -> B (only 1 setup A->B = 20)
    products = {"A": Product("A"), "B": Product("B")}
    cm = ChangeoverMatrix(["A", "B"], {("A", "B"): 20.0, ("B", "A"): 25.0})
    machines = {"M1": Machine("M1", initial_product="A")}
    jobs = {
        "J1": Job("J1", "B", 10, 10.0, due_date=200.0),
        "J2": Job("J2", "A", 10, 10.0, due_date=200.0),
        "J3": Job("J3", "B", 10, 10.0, due_date=200.0),
        "J4": Job("J4", "A", 10, 10.0, due_date=200.0),
    }
    problem = SchedulingProblem("campaign", products, machines, jobs, cm)
    sched = solve_cp_sat(
        problem,
        CPSATConfig(max_time_seconds=10.0, weights=ObjectiveWeights.makespan_only()),
    )
    assert sched.solver_status == SolverStatus.OPTIMAL
    assert ScheduleValidator.validate(problem, sched).is_valid
    assert sched.total_changeover == 20.0
    assert sched.makespan == 60.0


def test_cp_sat_weighted_tardiness_and_downtime():
    products = {"A": Product("A"), "B": Product("B")}
    cm = ChangeoverMatrix(["A", "B"], {("A", "B"): 10.0, ("B", "A"): 10.0})
    machines = {
        "M1": Machine("M1", downtime_windows=[DowntimeWindow(start=20.0, end=30.0)]),
        "M2": Machine("M2", eligible_products={"A"}),
    }
    jobs = {
        "J1": Job("J1", "A", 10, 15.0, due_date=20.0, priority=3.0),
        "J2": Job("J2", "B", 10, 15.0, due_date=25.0, priority=1.0),
        "J3": Job("J3", "A", 10, 10.0, due_date=30.0, priority=2.0),
    }
    problem = SchedulingProblem("tard_dt", products, machines, jobs, cm)
    sched = solve_cp_sat(
        problem,
        CPSATConfig(max_time_seconds=10.0, weights=ObjectiveWeights.weighted_tardiness_only()),
    )
    assert sched.solver_status == SolverStatus.OPTIMAL
    val = ScheduleValidator.validate(problem, sched)
    assert val.is_valid, val.errors


def test_cp_sat_infeasible_case():
    products = {"A": Product("A")}
    cm = ChangeoverMatrix(["A"])
    machines = {"M1": Machine("M1", available_until=25.0)}
    jobs = {
        "J1": Job("J1", "A", 10, 15.0, due_date=30.0),
        "J2": Job("J2", "A", 10, 15.0, due_date=30.0),
    }
    problem = SchedulingProblem("cp_infeas", products, machines, jobs, cm)
    sched = solve_cp_sat(problem, CPSATConfig(max_time_seconds=5.0))
    assert sched.solver_status == SolverStatus.INFEASIBLE


def test_cp_sat_medium_instance_with_time_limit():
    problem = generate_instance(InstanceGeneratorConfig(num_jobs=25, num_machines=3, num_products=6, seed=9))
    sched = solve_cp_sat(problem, CPSATConfig(max_time_seconds=2.0))
    assert sched.solver_status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    val = ScheduleValidator.validate(problem, sched)
    assert val.is_valid, val.errors
