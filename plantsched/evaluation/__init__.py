"""KPI calculation, algorithm comparison, and scaling benchmarks."""

from plantsched.evaluation.benchmark import ScalingBenchmarkConfig, run_scaling_benchmark
from plantsched.evaluation.comparison import ComparisonResult, compare_algorithms
from plantsched.evaluation.metrics import MachineKPI, ScheduleKPIs, evaluate_schedule

__all__ = [
    "ComparisonResult",
    "MachineKPI",
    "ScalingBenchmarkConfig",
    "ScheduleKPIs",
    "compare_algorithms",
    "evaluate_schedule",
    "run_scaling_benchmark",
]
