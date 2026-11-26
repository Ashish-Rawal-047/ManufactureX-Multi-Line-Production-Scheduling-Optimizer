"""SimPy machine resource and state wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field

import simpy

from plantsched.core.models import Machine


@dataclass
class SimulatedMachine:
    """Wraps a SimPy single-capacity machine resource and tracks operational state."""

    env: simpy.Environment
    machine: Machine
    resource: simpy.Resource = field(init=False)
    current_product: str | None = field(init=False)
    total_setup_time: float = 0.0
    total_processing_time: float = 0.0
    total_breakdown_time: float = 0.0
    total_planned_downtime: float = 0.0
    jobs_completed: int = 0

    def __post_init__(self) -> None:
        self.resource = simpy.Resource(self.env, capacity=1)
        self.current_product = self.machine.initial_product

    def advance_past_planned_downtime(self, current_time: float, duration: float) -> float:
        """Return earliest start >= current_time that avoids planned downtime windows."""
        t = max(current_time, self.machine.available_from)
        for dt in self.machine.downtime_windows:
            if t + duration <= dt.start + 1e-9:
                break
            if t < dt.end - 1e-9:
                t = dt.end
        return t
