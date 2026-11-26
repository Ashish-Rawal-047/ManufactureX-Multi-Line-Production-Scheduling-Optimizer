"""Core manufacturing domain entities for PlantSched."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Product:
    """Represents a manufactured product type."""

    product_id: str
    name: str = ""
    family: str = "general"
    base_processing_rate: float = 1.0
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.product_id:
            raise ValueError("product_id must be non-empty.")
        if self.base_processing_rate <= 0:
            raise ValueError("base_processing_rate must be positive.")
        if not self.name:
            object.__setattr__(self, "name", f"Product {self.product_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "family": self.family,
            "base_processing_rate": self.base_processing_rate,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Product:
        return cls(
            product_id=str(data["product_id"]),
            name=str(data.get("name", "")),
            family=str(data.get("family", "general")),
            base_processing_rate=float(data.get("base_processing_rate", 1.0)),
            attributes=dict(data.get("attributes", {})),
        )


@dataclass(frozen=True)
class DowntimeWindow:
    """Represents a planned or known machine unavailability interval [start, end)."""

    start: float
    end: float
    reason: str = "planned_maintenance"

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError("DowntimeWindow start must be non-negative.")
        if self.end <= self.start:
            raise ValueError("DowntimeWindow end must be strictly greater than start.")

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DowntimeWindow:
        return cls(
            start=float(data["start"]),
            end=float(data["end"]),
            reason=str(data.get("reason", "planned_maintenance")),
        )


@dataclass
class Machine:
    """Represents a production line / machine."""

    machine_id: str
    name: str = ""
    available_from: float = 0.0
    available_until: float | None = None
    eligible_products: set[str] | None = None
    capacity: float = 1.0
    initial_product: str | None = None
    downtime_windows: list[DowntimeWindow] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.machine_id:
            raise ValueError("machine_id must be non-empty.")
        if self.available_from < 0:
            raise ValueError("available_from must be non-negative.")
        if self.available_until is not None and self.available_until <= self.available_from:
            raise ValueError("available_until must be greater than available_from.")
        if self.capacity <= 0:
            raise ValueError("machine capacity must be positive.")
        if not self.name:
            self.name = f"Line {self.machine_id}"
        if self.eligible_products is not None:
            self.eligible_products = set(self.eligible_products)
        self.downtime_windows = sorted(self.downtime_windows, key=lambda d: d.start)

    def to_dict(self) -> dict[str, Any]:
        return {
            "machine_id": self.machine_id,
            "name": self.name,
            "available_from": self.available_from,
            "available_until": self.available_until,
            "eligible_products": sorted(self.eligible_products)
            if self.eligible_products is not None
            else None,
            "capacity": self.capacity,
            "initial_product": self.initial_product,
            "downtime_windows": [d.to_dict() for d in self.downtime_windows],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Machine:
        ep = data.get("eligible_products")
        return cls(
            machine_id=str(data["machine_id"]),
            name=str(data.get("name", "")),
            available_from=float(data.get("available_from", 0.0)),
            available_until=float(data["available_until"])
            if data.get("available_until") is not None
            else None,
            eligible_products=set(ep) if ep is not None else None,
            capacity=float(data.get("capacity", 1.0)),
            initial_product=data.get("initial_product"),
            downtime_windows=[
                DowntimeWindow.from_dict(d) for d in data.get("downtime_windows", [])
            ],
        )


@dataclass
class Job:
    """Represents a customer production order / job."""

    job_id: str
    product_id: str
    quantity: int
    processing_time: float
    arrival_time: float = 0.0
    due_date: float = 0.0
    priority: float = 1.0
    eligible_machines: list[str] | None = None

    def __post_init__(self) -> None:
        if not self.job_id:
            raise ValueError("job_id must be non-empty.")
        if not self.product_id:
            raise ValueError("product_id must be non-empty.")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive.")
        if self.processing_time <= 0:
            raise ValueError("processing_time must be positive.")
        if self.arrival_time < 0:
            raise ValueError("arrival_time must be non-negative.")
        if self.due_date < 0:
            raise ValueError("due_date must be non-negative.")
        if self.priority < 0:
            raise ValueError("priority must be non-negative.")
        if self.eligible_machines is not None:
            self.eligible_machines = list(dict.fromkeys(self.eligible_machines))

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "product_id": self.product_id,
            "quantity": self.quantity,
            "processing_time": self.processing_time,
            "arrival_time": self.arrival_time,
            "due_date": self.due_date,
            "priority": self.priority,
            "eligible_machines": list(self.eligible_machines)
            if self.eligible_machines is not None
            else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        em = data.get("eligible_machines")
        return cls(
            job_id=str(data["job_id"]),
            product_id=str(data["product_id"]),
            quantity=int(data["quantity"]),
            processing_time=float(data["processing_time"]),
            arrival_time=float(data.get("arrival_time", 0.0)),
            due_date=float(data.get("due_date", 0.0)),
            priority=float(data.get("priority", 1.0)),
            eligible_machines=list(em) if em is not None else None,
        )
