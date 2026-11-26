"""First-Come First-Served (FCFS) baseline scheduler."""

from __future__ import annotations

import time

from plantsched.core.config import ObjectiveWeights, SolverStatus
from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule, ScheduledJob
from plantsched.core.scheduling_utils import compute_earliest_slot


def solve_fcfs(
    problem: SchedulingProblem,
    weights: ObjectiveWeights | None = None,
) -> Schedule:
    """Schedule jobs in arrival order onto the earliest-completing eligible machine.

    Respects:
    - Arrival order (tie-broken by job_id)
    - Machine eligibility
    - Machine availability and downtime windows
    - Sequence-dependent changeover times
    """
    t0 = time.perf_counter()
    obj_weights = weights or ObjectiveWeights()

    machine_free_time: dict[str, float] = {
        m_id: m.available_from for m_id, m in problem.machines.items()
    }
    machine_curr_prod: dict[str, str | None] = {
        m_id: m.initial_product for m_id, m in problem.machines.items()
    }

    sorted_jobs = sorted(problem.jobs.values(), key=lambda j: (j.arrival_time, j.job_id))
    scheduled: list[ScheduledJob] = []

    for job in sorted_jobs:
        eligible = problem.get_eligible_machines(job.job_id)
        best_op: ScheduledJob | None = None
        best_key: tuple[float, float, str] | None = None

        for m_id in eligible:
            op = compute_earliest_slot(
                problem=problem,
                job_id=job.job_id,
                machine_id=m_id,
                machine_free_time=machine_free_time[m_id],
                machine_current_product=machine_curr_prod[m_id],
            )
            if op is None:
                continue
            key = (op.completion_time, op.setup_duration, m_id)
            if best_key is None or key < best_key:
                best_key = key
                best_op = op

        if best_op is None:
            runtime = time.perf_counter() - t0
            return Schedule(
                problem_name=problem.name,
                algorithm="FCFS",
                scheduled_jobs=[],
                solver_status=SolverStatus.INFEASIBLE,
                runtime_seconds=runtime,
                metadata={"reason": f"No eligible machine could accommodate job {job.job_id}."},
            )

        scheduled.append(best_op)
        machine_free_time[best_op.machine_id] = best_op.completion_time
        machine_curr_prod[best_op.machine_id] = best_op.product_id

    runtime = time.perf_counter() - t0
    schedule = Schedule(
        problem_name=problem.name,
        algorithm="FCFS",
        scheduled_jobs=scheduled,
        solver_status=SolverStatus.FEASIBLE,
        runtime_seconds=runtime,
    )
    schedule.objective_value = schedule.compute_objective(obj_weights)
    return schedule
