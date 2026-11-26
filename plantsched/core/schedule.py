"""Common schedule representation shared across all optimizers and simulators."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from plantsched.core.config import ObjectiveWeights, SolverStatus


@dataclass
class ScheduledJob:
    """Single scheduled job operation on a specific machine."""

    job_id: str
    product_id: str
    machine_id: str
    start_time: float
    setup_start_time: float
    setup_duration: float
    processing_start_time: float
    processing_duration: float
    completion_time: float
    due_date: float
    tardiness: float
    priority: float = 1.0
    predecessor_product: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "product_id": self.product_id,
            "machine_id": self.machine_id,
            "start_time": self.start_time,
            "setup_start_time": self.setup_start_time,
            "setup_duration": self.setup_duration,
            "processing_start_time": self.processing_start_time,
            "processing_duration": self.processing_duration,
            "completion_time": self.completion_time,
            "due_date": self.due_date,
            "tardiness": self.tardiness,
            "priority": self.priority,
            "predecessor_product": self.predecessor_product,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduledJob:
        return cls(
            job_id=str(data["job_id"]),
            product_id=str(data["product_id"]),
            machine_id=str(data["machine_id"]),
            start_time=float(data["start_time"]),
            setup_start_time=float(data["setup_start_time"]),
            setup_duration=float(data["setup_duration"]),
            processing_start_time=float(data["processing_start_time"]),
            processing_duration=float(data["processing_duration"]),
            completion_time=float(data["completion_time"]),
            due_date=float(data["due_date"]),
            tardiness=float(data["tardiness"]),
            priority=float(data.get("priority", 1.0)),
            predecessor_product=data.get("predecessor_product"),
        )


@dataclass
class Schedule:
    """Standardized schedule output returned by all PlantSched algorithms."""

    problem_name: str
    algorithm: str
    scheduled_jobs: list[ScheduledJob]
    solver_status: SolverStatus
    runtime_seconds: float
    objective_value: float | None = None
    best_bound: float | None = None
    optimality_gap: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_solution(self) -> bool:
        return bool(self.scheduled_jobs) and self.solver_status in (
            SolverStatus.OPTIMAL,
            SolverStatus.FEASIBLE,
        )

    @property
    def makespan(self) -> float:
        if not self.scheduled_jobs:
            return 0.0
        return max(sj.completion_time for sj in self.scheduled_jobs)

    @property
    def total_changeover(self) -> float:
        return sum(sj.setup_duration for sj in self.scheduled_jobs)

    @property
    def total_tardiness(self) -> float:
        return sum(sj.tardiness for sj in self.scheduled_jobs)

    @property
    def weighted_tardiness(self) -> float:
        return sum(sj.priority * sj.tardiness for sj in self.scheduled_jobs)

    def compute_objective(self, weights: ObjectiveWeights) -> float:
        """Evaluate weighted objective directly from scheduled jobs."""
        return (
            weights.alpha * self.makespan
            + weights.beta * self.weighted_tardiness
            + weights.gamma * self.total_changeover
        )

    def get_machine_sequence(self, machine_id: str) -> list[ScheduledJob]:
        """Return jobs assigned to `machine_id`, sorted chronologically."""
        return sorted(
            (sj for sj in self.scheduled_jobs if sj.machine_id == machine_id),
            key=lambda sj: (sj.start_time, sj.completion_time, sj.job_id),
        )

    def to_dataframe(self) -> pd.DataFrame:
        """Convert scheduled jobs to a pandas DataFrame."""
        if not self.scheduled_jobs:
            return pd.DataFrame(
                columns=[
                    "job_id",
                    "product_id",
                    "machine_id",
                    "start_time",
                    "setup_start_time",
                    "setup_duration",
                    "processing_start_time",
                    "processing_duration",
                    "completion_time",
                    "due_date",
                    "tardiness",
                    "priority",
                    "predecessor_product",
                ]
            )
        rows = [sj.to_dict() for sj in self.scheduled_jobs]
        return pd.DataFrame(rows).sort_values(["machine_id", "start_time", "job_id"]).reset_index(
            drop=True
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_name": self.problem_name,
            "algorithm": self.algorithm,
            "scheduled_jobs": [sj.to_dict() for sj in self.scheduled_jobs],
            "solver_status": self.solver_status.value,
            "runtime_seconds": self.runtime_seconds,
            "objective_value": self.objective_value,
            "best_bound": self.best_bound,
            "optimality_gap": self.optimality_gap,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Schedule:
        return cls(
            problem_name=str(data["problem_name"]),
            algorithm=str(data["algorithm"]),
            scheduled_jobs=[ScheduledJob.from_dict(j) for j in data["scheduled_jobs"]],
            solver_status=SolverStatus(data["solver_status"]),
            runtime_seconds=float(data["runtime_seconds"]),
            objective_value=float(data["objective_value"])
            if data.get("objective_value") is not None
            else None,
            best_bound=float(data["best_bound"])
            if data.get("best_bound") is not None
            else None,
            optimality_gap=float(data["optimality_gap"])
            if data.get("optimality_gap") is not None
            else None,
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def from_json(cls, path: str | Path) -> Schedule:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
