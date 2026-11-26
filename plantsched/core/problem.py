"""Scheduling problem definition and directional changeover matrix."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from plantsched.core.models import Job, Machine, Product


@dataclass
class ChangeoverMatrix:
    """Directional sequence-dependent setup/changeover time matrix.

    Setup(A, B) does not necessarily equal Setup(B, A).
    Diagonal entries Setup(A, A) must be 0.
    """

    product_ids: list[str]
    matrix: dict[tuple[str, str], float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.product_ids:
            raise ValueError("product_ids must be non-empty.")
        if len(set(self.product_ids)) != len(self.product_ids):
            raise ValueError("product_ids must be unique.")

        normalized: dict[tuple[str, str], float] = {}
        for p_from in self.product_ids:
            for p_to in self.product_ids:
                val = float(self.matrix.get((p_from, p_to), 0.0))
                if val < 0:
                    raise ValueError(
                        f"Changeover time ({p_from} -> {p_to}) cannot be negative: {val}."
                    )
                if p_from == p_to and abs(val) > 1e-9:
                    raise ValueError(
                        f"Diagonal changeover time ({p_from} -> {p_to}) must be 0, got {val}."
                    )
                normalized[(p_from, p_to)] = 0.0 if p_from == p_to else val
        self.matrix = normalized

    def get_setup(self, from_product: str, to_product: str) -> float:
        """Return setup duration when switching from `from_product` to `to_product`."""
        if (from_product, to_product) not in self.matrix:
            raise KeyError(
                f"Unknown product pair ({from_product!r}, {to_product!r}) in ChangeoverMatrix."
            )
        return self.matrix[(from_product, to_product)]

    def max_setup(self) -> float:
        """Return maximum setup duration in the matrix."""
        return max(self.matrix.values(), default=0.0)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert matrix to a labeled pandas DataFrame (rows=from, cols=to)."""
        data = {
            p_to: [self.matrix[(p_from, p_to)] for p_from in self.product_ids]
            for p_to in self.product_ids
        }
        return pd.DataFrame(data, index=self.product_ids)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> ChangeoverMatrix:
        """Construct a ChangeoverMatrix from a square DataFrame."""
        product_ids = [str(idx) for idx in df.index]
        col_ids = [str(col) for col in df.columns]
        if product_ids != col_ids:
            raise ValueError(
                "DataFrame index and columns must match in the exact same order."
            )
        matrix: dict[tuple[str, str], float] = {}
        for p_from in product_ids:
            for p_to in product_ids:
                matrix[(p_from, p_to)] = float(df.loc[p_from, p_to])
        return cls(product_ids=product_ids, matrix=matrix)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_ids": list(self.product_ids),
            "matrix": {
                p_from: {p_to: self.matrix[(p_from, p_to)] for p_to in self.product_ids}
                for p_from in self.product_ids
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChangeoverMatrix:
        product_ids = [str(p) for p in data["product_ids"]]
        raw_matrix = data["matrix"]
        matrix: dict[tuple[str, str], float] = {}
        for p_from in product_ids:
            row = raw_matrix[p_from]
            for p_to in product_ids:
                matrix[(p_from, p_to)] = float(row[p_to])
        return cls(product_ids=product_ids, matrix=matrix)


@dataclass
class SchedulingProblem:
    """Complete multi-line production scheduling problem instance."""

    name: str
    products: dict[str, Product]
    machines: dict[str, Machine]
    jobs: dict[str, Job]
    changeover_matrix: ChangeoverMatrix
    horizon: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate structural consistency, eligibility, and constraints."""
        if not self.name:
            raise ValueError("Problem name must be non-empty.")
        if not self.products:
            raise ValueError("Problem must contain at least one product.")
        if not self.machines:
            raise ValueError("Problem must contain at least one machine.")
        if not self.jobs:
            raise ValueError("Problem must contain at least one job.")

        if set(self.changeover_matrix.product_ids) != set(self.products.keys()):
            raise ValueError(
                "ChangeoverMatrix product_ids must match the problem's product IDs."
            )

        for m_id, machine in self.machines.items():
            if m_id != machine.machine_id:
                raise ValueError(f"Machine key {m_id!r} != machine.machine_id {machine.machine_id!r}.")
            if machine.initial_product is not None and machine.initial_product not in self.products:
                raise ValueError(
                    f"Machine {m_id} initial_product {machine.initial_product!r} is unknown."
                )
            if machine.eligible_products is not None:
                unknown = machine.eligible_products - set(self.products.keys())
                if unknown:
                    raise ValueError(
                        f"Machine {m_id} references unknown eligible_products: {sorted(unknown)}."
                    )
            for idx in range(len(machine.downtime_windows) - 1):
                curr_dt = machine.downtime_windows[idx]
                next_dt = machine.downtime_windows[idx + 1]
                if curr_dt.end > next_dt.start:
                    raise ValueError(
                        f"Machine {m_id} has overlapping downtime windows: {curr_dt} and {next_dt}."
                    )

        for j_id, job in self.jobs.items():
            if j_id != job.job_id:
                raise ValueError(f"Job key {j_id!r} != job.job_id {job.job_id!r}.")
            if job.product_id not in self.products:
                raise ValueError(f"Job {j_id} references unknown product {job.product_id!r}.")
            if job.eligible_machines is not None:
                unknown_m = set(job.eligible_machines) - set(self.machines.keys())
                if unknown_m:
                    raise ValueError(
                        f"Job {j_id} references unknown eligible_machines: {sorted(unknown_m)}."
                    )
            eligible = self.get_eligible_machines(j_id)
            if not eligible:
                raise ValueError(
                    f"Job {j_id} (product {job.product_id}) has no eligible machines."
                )

    def get_eligible_machines(self, job_id: str) -> list[str]:
        """Return ordered list of machine IDs eligible to process `job_id`."""
        job = self.jobs[job_id]
        eligible: list[str] = []
        for m_id, machine in self.machines.items():
            if job.eligible_machines is not None and m_id not in job.eligible_machines:
                continue
            if (
                machine.eligible_products is not None
                and job.product_id not in machine.eligible_products
            ):
                continue
            eligible.append(m_id)
        return eligible

    def get_processing_time(self, job_id: str, machine_id: str) -> float:
        """Return effective processing time of `job_id` on `machine_id`."""
        job = self.jobs[job_id]
        machine = self.machines[machine_id]
        if machine.capacity == 1.0:
            return float(job.processing_time)
        return round(float(job.processing_time) / float(machine.capacity), 4)

    def get_setup_time(self, from_product: str | None, to_product: str) -> float:
        """Return changeover duration from `from_product` (or None) to `to_product`."""
        if from_product is None:
            return 0.0
        return self.changeover_matrix.get_setup(from_product, to_product)

    def compute_horizon(self) -> float:
        """Compute a safe upper bound on completion time if horizon is unset."""
        if self.horizon is not None:
            return float(self.horizon)
        max_arrival = max((j.arrival_time for j in self.jobs.values()), default=0.0)
        max_avail = max((m.available_from for m in self.machines.values()), default=0.0)
        total_proc = sum(
            max(self.get_processing_time(j_id, m_id) for m_id in self.get_eligible_machines(j_id))
            for j_id in self.jobs
        )
        max_setup = self.changeover_matrix.max_setup()
        total_downtime = sum(
            sum(dt.duration for dt in m.downtime_windows) for m in self.machines.values()
        )
        return max_arrival + max_avail + total_proc + len(self.jobs) * max_setup + total_downtime + 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "products": [p.to_dict() for p in self.products.values()],
            "machines": [m.to_dict() for m in self.machines.values()],
            "jobs": [j.to_dict() for j in self.jobs.values()],
            "changeover_matrix": self.changeover_matrix.to_dict(),
            "horizon": self.horizon,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SchedulingProblem:
        products = {p["product_id"]: Product.from_dict(p) for p in data["products"]}
        machines = {m["machine_id"]: Machine.from_dict(m) for m in data["machines"]}
        jobs = {j["job_id"]: Job.from_dict(j) for j in data["jobs"]}
        changeover = ChangeoverMatrix.from_dict(data["changeover_matrix"])
        return cls(
            name=str(data["name"]),
            products=products,
            machines=machines,
            jobs=jobs,
            changeover_matrix=changeover,
            horizon=float(data["horizon"]) if data.get("horizon") is not None else None,
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def from_json(cls, path: str | Path) -> SchedulingProblem:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
