"""Shared schedule construction utilities used by FCFS, GA, and SA."""

from __future__ import annotations

from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import ScheduledJob


def compute_earliest_slot(
    problem: SchedulingProblem,
    job_id: str,
    machine_id: str,
    machine_free_time: float,
    machine_current_product: str | None,
) -> ScheduledJob | None:
    """Compute the earliest feasible ScheduledJob placement on `machine_id`.

    Respects job arrival time, machine availability window, sequence-dependent
    setup duration, processing duration, and machine downtime windows.
    Returns None if the operation cannot complete before `machine.available_until`.
    """
    job = problem.jobs[job_id]
    machine = problem.machines[machine_id]

    setup_dur = problem.get_setup_time(machine_current_product, job.product_id)
    proc_dur = problem.get_processing_time(job_id, machine_id)
    total_dur = setup_dur + proc_dur

    start = max(machine_free_time, job.arrival_time, machine.available_from)

    # Shift past any overlapping downtime window (windows are sorted by start)
    for dt in machine.downtime_windows:
        if start + total_dur <= dt.start + 1e-9:
            break
        if start < dt.end - 1e-9:
            start = dt.end

    proc_start = start + setup_dur
    completion = proc_start + proc_dur

    if machine.available_until is not None and completion > machine.available_until + 1e-9:
        return None

    tardiness = max(0.0, completion - job.due_date)
    return ScheduledJob(
        job_id=job.job_id,
        product_id=job.product_id,
        machine_id=machine_id,
        start_time=start,
        setup_start_time=start,
        setup_duration=setup_dur,
        processing_start_time=proc_start,
        processing_duration=proc_dur,
        completion_time=completion,
        due_date=job.due_date,
        tardiness=tardiness,
        priority=job.priority,
        predecessor_product=machine_current_product,
    )
