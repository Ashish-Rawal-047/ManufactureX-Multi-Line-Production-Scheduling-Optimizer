"""Objective calculation helpers shared across optimization models."""

from __future__ import annotations

from plantsched.core.config import ObjectiveWeights
from plantsched.core.schedule import Schedule


def evaluate_schedule_objective(schedule: Schedule, weights: ObjectiveWeights) -> float:
    """Compute weighted multi-objective value from a Schedule."""
    return schedule.compute_objective(weights)


def compute_optimality_gap(objective: float | None, best_bound: float | None) -> float | None:
    """Compute relative MIP/CP optimality gap: |obj - bound| / max(1e-9, |obj|)."""
    if objective is None or best_bound is None:
        return None
    denom = max(1e-9, abs(objective))
    gap = max(0.0, (objective - best_bound) / denom)
    return gap
