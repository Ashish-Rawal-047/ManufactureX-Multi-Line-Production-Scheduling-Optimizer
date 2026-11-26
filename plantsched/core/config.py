"""Configuration dataclasses and solver status enums for PlantSched."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SolverStatus(str, Enum):
    """Standardized solver status across exact and heuristic algorithms."""

    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    UNKNOWN = "UNKNOWN"
    MODEL_INVALID = "MODEL_INVALID"


@dataclass(frozen=True)
class ObjectiveWeights:
    """Weights for the multi-objective scheduling cost function.

    Objective = alpha * Makespan + beta * WeightedTardiness + gamma * TotalChangeover
    """

    alpha: float = 1.0
    beta: float = 1.0
    gamma: float = 0.5

    def __post_init__(self) -> None:
        if self.alpha < 0 or self.beta < 0 or self.gamma < 0:
            raise ValueError("Objective weights must be non-negative.")
        if self.alpha == 0 and self.beta == 0 and self.gamma == 0:
            raise ValueError("At least one objective weight must be positive.")

    @classmethod
    def makespan_only(cls) -> ObjectiveWeights:
        return cls(alpha=1.0, beta=0.0, gamma=0.0)

    @classmethod
    def weighted_tardiness_only(cls) -> ObjectiveWeights:
        return cls(alpha=0.0, beta=1.0, gamma=0.0)

    @classmethod
    def changeover_only(cls) -> ObjectiveWeights:
        return cls(alpha=0.0, beta=0.0, gamma=1.0)

    @classmethod
    def balanced(cls) -> ObjectiveWeights:
        return cls(alpha=1.0, beta=1.0, gamma=0.5)


@dataclass
class CPSATConfig:
    """Configuration for the OR-Tools CP-SAT solver."""

    max_time_seconds: float = 30.0
    num_workers: int = 4
    random_seed: int = 42
    weights: ObjectiveWeights = ObjectiveWeights()
    log_search_progress: bool = False


@dataclass
class MILPConfig:
    """Configuration for the PuLP MILP solver."""

    max_time_seconds: float = 30.0
    msg: bool = False
    weights: ObjectiveWeights = ObjectiveWeights()
    include_downtime: bool = True


@dataclass
class GAConfig:
    """Configuration for the Genetic Algorithm."""

    population_size: int = 60
    generations: int = 120
    crossover_prob: float = 0.85
    mutation_prob: float = 0.25
    tournament_size: int = 3
    elitism_count: int = 2
    random_seed: int = 42
    weights: ObjectiveWeights = ObjectiveWeights()
    early_stop_generations: int | None = None


@dataclass
class SAConfig:
    """Configuration for Simulated Annealing."""

    initial_temp: float = 200.0
    cooling_rate: float = 0.992
    min_temp: float = 0.1
    max_iterations: int = 2000
    random_seed: int = 42
    weights: ObjectiveWeights = ObjectiveWeights()


@dataclass
class SimulationConfig:
    """Configuration for SimPy discrete-event and Monte Carlo simulation."""

    processing_time_cv: float = 0.10
    enable_downtime: bool = True
    mtbf: float = 300.0
    mttr: float = 20.0
    arrival_delay_prob: float = 0.15
    max_arrival_delay: float = 20.0
    num_replications: int = 30
    random_seed: int = 42
