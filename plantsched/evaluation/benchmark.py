"""Scaling benchmark suite across increasing job counts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from plantsched.core.config import (
    CPSATConfig,
    GAConfig,
    MILPConfig,
    ObjectiveWeights,
    SAConfig,
)
from plantsched.data.generator import InstanceGeneratorConfig, generate_instance
from plantsched.evaluation.comparison import compare_algorithms


@dataclass
class ScalingBenchmarkConfig:
    """Parameters controlling multi-scale solver vs heuristic experiments."""

    job_sizes: tuple[int, ...] = (10, 25, 50, 100, 250, 500)
    num_machines: int = 4
    num_products: int = 8
    cp_sat_time_limit: float = 20.0
    cp_sat_max_jobs: int = 100
    milp_time_limit: float = 15.0
    milp_max_jobs: int = 25
    ga_population: int = 50
    ga_generations: int = 100
    sa_iterations: int = 1500
    seed: int = 42
    weights: ObjectiveWeights = ObjectiveWeights()


def run_scaling_benchmark(
    config: ScalingBenchmarkConfig | None = None,
    output_csv: str | Path | None = None,
) -> pd.DataFrame:
    """Benchmark FCFS, CP-SAT, MILP (up to `milp_max_jobs`), GA, and SA across sizes."""
    cfg = config or ScalingBenchmarkConfig()
    all_rows: list[dict] = []

    for n_jobs in cfg.job_sizes:
        n_machines = max(cfg.num_machines, min(8, 2 + n_jobs // 40))
        n_products = max(cfg.num_products, min(14, 4 + n_jobs // 30))
        inst_cfg = InstanceGeneratorConfig(
            num_jobs=n_jobs,
            num_machines=n_machines,
            num_products=n_products,
            seed=cfg.seed + n_jobs,
        )
        problem = generate_instance(inst_cfg)

        algos = ["FCFS", "GA", "SA"]
        if n_jobs <= cfg.cp_sat_max_jobs:
            algos.insert(1, "CP-SAT")
        if n_jobs <= cfg.milp_max_jobs:
            algos.insert(2 if "CP-SAT" in algos else 1, "MILP")

        # Scale heuristic effort reasonably for very large instances so runs stay practical
        ga_gens = cfg.ga_generations if n_jobs <= 100 else max(40, cfg.ga_generations // 2)
        sa_iters = cfg.sa_iterations if n_jobs <= 100 else max(800, cfg.sa_iterations // 2)

        comp = compare_algorithms(
            problem=problem,
            algorithms=tuple(algos),
            weights=cfg.weights,
            cp_sat_config=CPSATConfig(
                max_time_seconds=cfg.cp_sat_time_limit,
                random_seed=cfg.seed,
                weights=cfg.weights,
            ),
            milp_config=MILPConfig(
                max_time_seconds=cfg.milp_time_limit,
                weights=cfg.weights,
            ),
            ga_config=GAConfig(
                population_size=cfg.ga_population,
                generations=ga_gens,
                random_seed=cfg.seed,
                weights=cfg.weights,
            ),
            sa_config=SAConfig(
                max_iterations=sa_iters,
                random_seed=cfg.seed,
                weights=cfg.weights,
            ),
        )

        for row in comp.summary_table.to_dict(orient="records"):
            row["NumJobs"] = n_jobs
            row["NumMachines"] = n_machines
            row["NumProducts"] = n_products
            all_rows.append(row)

    df = pd.DataFrame(all_rows)
    if output_csv is not None:
        out_path = Path(output_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
    return df
