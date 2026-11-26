"""Tests for the shared ScheduleValidator."""

import copy

from plantsched.baselines import solve_fcfs
from plantsched.core import (
    ChangeoverMatrix,
    DowntimeWindow,
    Job,
    Machine,
    Product,
    ScheduleValidator,
    SchedulingProblem,
)


def _base_problem_and_schedule():
    products = {"A": Product("A"), "B": Product("B")}
    cm = ChangeoverMatrix(["A", "B"], {("A", "B"): 10.0, ("B", "A"): 5.0})
    machines = {
        "M1": Machine("M1", initial_product="A", downtime_windows=[DowntimeWindow(50.0, 60.0)]),
        "M2": Machine("M2", eligible_products={"B"}),
    }
    jobs = {
        "J1": Job("J1", "A", 10, 20.0, due_date=30.0),
        "J2": Job("J2", "B", 10, 15.0, due_date=40.0),
    }
    prob = SchedulingProblem("val_test", products, machines, jobs, cm)
    sched = solve_fcfs(prob)
    assert ScheduleValidator.validate(prob, sched).is_valid
    return prob, sched


def test_validator_catches_all_error_classes():
    prob, valid_sched = _base_problem_and_schedule()

    # 1. Missing job
    s_missing = copy.deepcopy(valid_sched)
    s_missing.scheduled_jobs.pop()
    assert not ScheduleValidator.validate(prob, s_missing).is_valid

    # 2. Duplicate job
    s_dup = copy.deepcopy(valid_sched)
    s_dup.scheduled_jobs.append(copy.deepcopy(s_dup.scheduled_jobs[0]))
    assert not ScheduleValidator.validate(prob, s_dup).is_valid

    # 3. Ineligible machine
    s_inelig = copy.deepcopy(valid_sched)
    for sj in s_inelig.scheduled_jobs:
        if sj.job_id == "J1":
            sj.machine_id = "M2"
    assert not ScheduleValidator.validate(prob, s_inelig).is_valid

    # 4. Overlapping jobs on same machine
    s_overlap = copy.deepcopy(valid_sched)
    for sj in s_overlap.scheduled_jobs:
        sj.machine_id = "M1"
        sj.start_time = 0.0
        sj.setup_start_time = 0.0
        sj.setup_duration = 0.0
        sj.processing_start_time = 0.0
        sj.completion_time = sj.processing_duration
    assert not ScheduleValidator.validate(prob, s_overlap).is_valid

    # 5. Incorrect setup duration
    s_setup = copy.deepcopy(valid_sched)
    s_setup.scheduled_jobs[0].setup_duration = 99.0
    assert not ScheduleValidator.validate(prob, s_setup).is_valid

    # 6. Downtime overlap
    s_dt = copy.deepcopy(valid_sched)
    for sj in s_dt.scheduled_jobs:
        if sj.job_id == "J1":
            sj.start_time = 45.0
            sj.setup_start_time = 45.0
            sj.processing_start_time = 45.0
            sj.completion_time = 65.0
            sj.tardiness = 35.0
    assert not ScheduleValidator.validate(prob, s_dt).is_valid
