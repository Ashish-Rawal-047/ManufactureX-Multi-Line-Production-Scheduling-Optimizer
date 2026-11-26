"""Tests for the centralized KPI evaluation engine."""

import pytest

from plantsched.core import (
    ChangeoverMatrix,
    Job,
    Machine,
    ObjectiveWeights,
    Product,
    Schedule,
    ScheduledJob,
    SchedulingProblem,
    SolverStatus,
)
from plantsched.evaluation import evaluate_schedule


def test_kpi_calculations_exact():
    products = {"A": Product("A"), "B": Product("B")}
    cm = ChangeoverMatrix(["A", "B"], {("A", "B"): 10.0, ("B", "A"): 10.0})
    machines = {"M1": Machine("M1", initial_product="A"), "M2": Machine("M2", initial_product="B")}
    jobs = {
        "J1": Job("J1", "A", 10, 20.0, due_date=25.0, priority=2.0),
        "J2": Job("J2", "B", 10, 30.0, due_date=25.0, priority=1.0),
    }
    prob = SchedulingProblem("kpi_test", products, machines, jobs, cm)
    sched = Schedule(
        problem_name="kpi_test",
        algorithm="Manual",
        scheduled_jobs=[
            ScheduledJob("J1", "A", "M1", 0.0, 0.0, 0.0, 0.0, 20.0, 20.0, 25.0, 0.0, 2.0, "A"),
            ScheduledJob("J2", "B", "M2", 0.0, 0.0, 0.0, 0.0, 30.0, 30.0, 25.0, 5.0, 1.0, "B"),
        ],
        solver_status=SolverStatus.FEASIBLE,
        runtime_seconds=0.01,
    )
    kpis = evaluate_schedule(prob, sched, weights=ObjectiveWeights())
    assert kpis.is_valid
    assert kpis.makespan == pytest.approx(30.0)
    assert kpis.total_changeover_time == pytest.approx(0.0)
    assert kpis.total_tardiness == pytest.approx(5.0)
    assert kpis.weighted_tardiness == pytest.approx(5.0)
    assert kpis.num_late_orders == 1
    assert kpis.on_time_delivery_pct == pytest.approx(50.0)
    # M1 busy=20/30 -> 66.67%, M2 busy=30/30 -> 100%, mean=83.33%
    assert kpis.mean_utilization_pct == pytest.approx((20.0 / 30.0 * 100.0 + 100.0) / 2.0, rel=1e-3)
    assert kpis.total_idle_time == pytest.approx(10.0)
