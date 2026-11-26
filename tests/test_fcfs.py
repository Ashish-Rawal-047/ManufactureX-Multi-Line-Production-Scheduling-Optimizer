"""Tests for the First-Come First-Served (FCFS) baseline scheduler."""

from plantsched.baselines import solve_fcfs
from plantsched.core import (
    ChangeoverMatrix,
    DowntimeWindow,
    Job,
    Machine,
    Product,
    ScheduleValidator,
    SchedulingProblem,
    SolverStatus,
)


def _make_sample_problem() -> SchedulingProblem:
    products = {"A": Product("A"), "B": Product("B")}
    cm = ChangeoverMatrix(product_ids=["A", "B"], matrix={("A", "B"): 10.0, ("B", "A"): 5.0})
    machines = {
        "M1": Machine(
            "M1",
            initial_product="A",
            downtime_windows=[DowntimeWindow(start=25.0, end=35.0)],
        ),
        "M2": Machine("M2", initial_product="B", eligible_products={"B"}),
    }
    jobs = {
        "J1": Job("J1", "B", 10, 15.0, arrival_time=0.0, due_date=30.0),
        "J2": Job("J2", "A", 10, 20.0, arrival_time=5.0, due_date=40.0),
        "J3": Job("J3", "A", 10, 10.0, arrival_time=8.0, due_date=60.0),
    }
    return SchedulingProblem("fcfs_test", products, machines, jobs, cm)


def test_fcfs_respects_arrival_eligibility_downtime_and_setups():
    problem = _make_sample_problem()
    sched = solve_fcfs(problem)
    assert sched.solver_status == SolverStatus.FEASIBLE
    val = ScheduleValidator.validate(problem, sched)
    assert val.is_valid, val.errors

    by_job = {sj.job_id: sj for sj in sched.scheduled_jobs}
    # J1 arrives first at 0, product B -> M2 has initial_product B (0 setup, completes at 15)
    assert by_job["J1"].machine_id == "M2"
    assert by_job["J1"].setup_duration == 0.0
    assert by_job["J1"].completion_time == 15.0

    # J2 (product A, dur 20) only eligible on M1; M1 downtime is [25, 35], so [5, 25] fits!
    assert by_job["J2"].machine_id == "M1"
    assert by_job["J2"].start_time == 5.0
    assert by_job["J2"].completion_time == 25.0

    # J3 (product A, dur 10) must wait past downtime [25, 35] -> starts at 35
    assert by_job["J3"].machine_id == "M1"
    assert by_job["J3"].start_time == 35.0
    assert by_job["J3"].completion_time == 45.0


def test_fcfs_infeasible_horizon():
    products = {"A": Product("A")}
    cm = ChangeoverMatrix(["A"])
    machines = {"M1": Machine("M1", available_until=15.0)}
    jobs = {"J1": Job("J1", "A", 10, 20.0, due_date=30.0)}
    problem = SchedulingProblem("infeas", products, machines, jobs, cm)
    sched = solve_fcfs(problem)
    assert sched.solver_status == SolverStatus.INFEASIBLE
