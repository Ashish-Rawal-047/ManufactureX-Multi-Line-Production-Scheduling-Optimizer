"""Constraint modeling utilities and integer scaling helpers for exact solvers."""

from __future__ import annotations

import math

from plantsched.core.config import ObjectiveWeights
from plantsched.core.problem import SchedulingProblem


def compute_time_scale(problem: SchedulingProblem) -> int:
    """Determine integer scaling factor for CP-SAT time variables.

    Returns 1 when all problem time parameters are exact integers,
    or 100 when fractional processing/setup/arrival/due times exist.
    """
    values: list[float] = []
    for j_id, job in problem.jobs.items():
        values.extend([job.arrival_time, job.due_date])
        for m_id in problem.get_eligible_machines(j_id):
            values.append(problem.get_processing_time(j_id, m_id))
    for m in problem.machines.values():
        values.append(m.available_from)
        if m.available_until is not None:
            values.append(m.available_until)
        for dt in m.downtime_windows:
            values.extend([dt.start, dt.end])
    values.extend(problem.changeover_matrix.matrix.values())

    for v in values:
        if abs(v - round(v)) > 1e-6:
            return 100
    return 1


def compute_weight_scale(problem: SchedulingProblem, weights: ObjectiveWeights) -> int:
    """Determine integer scaling factor for objective weights and job priorities."""
    values = [weights.alpha, weights.beta, weights.gamma] + [
        j.priority for j in problem.jobs.values()
    ]
    for v in values:
        if abs(v - round(v)) > 1e-6:
            return 100
    return 1


def scale_int(value: float, scale: int) -> int:
    """Convert a float value to scaled integer."""
    return int(round(value * scale))


def compute_scaled_horizon(problem: SchedulingProblem, time_scale: int) -> int:
    """Compute a safe integer horizon for CP-SAT variable bounds."""
    return int(math.ceil(problem.compute_horizon() * time_scale))
