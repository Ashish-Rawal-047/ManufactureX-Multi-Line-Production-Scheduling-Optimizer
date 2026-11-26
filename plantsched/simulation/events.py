"""Stochastic event models and operational disturbances for SimPy simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class SimulationEvent:
    """Discrete-event log entry emitted during SimPy plant execution."""

    event_type: str
    time: float
    machine_id: str
    job_id: str | None = None
    product_id: str | None = None
    duration: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


def sample_processing_time(
    nominal_time: float,
    cv: float,
    rng: np.random.Generator,
    min_factor: float = 0.25,
) -> float:
    """Sample a physically valid non-negative processing time ~ Normal(mean, std)."""
    if cv <= 0.0:
        return float(nominal_time)
    std = nominal_time * cv
    sample = float(rng.normal(nominal_time, std))
    return max(nominal_time * min_factor, sample)


def sample_arrival_delay(
    delay_prob: float,
    max_delay: float,
    rng: np.random.Generator,
) -> float:
    """Sample a random job arrival delay (0 if on time)."""
    if delay_prob <= 0.0 or max_delay <= 0.0:
        return 0.0
    if rng.random() < delay_prob:
        return float(rng.uniform(0.5, max_delay))
    return 0.0


def sample_breakdown_delay(
    operation_duration: float,
    mtbf: float,
    mttr: float,
    rng: np.random.Generator,
) -> float:
    """Sample random unplanned machine breakdown repair duration occurring during an operation."""
    if mtbf <= 0.0 or mttr <= 0.0 or operation_duration <= 0.0:
        return 0.0
    # Poisson failure probability over operation_duration: 1 - exp(-dur / mtbf)
    fail_prob = 1.0 - float(np.exp(-operation_duration / mtbf))
    if rng.random() < fail_prob:
        return float(rng.exponential(mttr))
    return 0.0
