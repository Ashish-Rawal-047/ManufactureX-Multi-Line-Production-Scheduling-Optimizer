"""CLI script to run SimPy discrete-event simulation and Monte Carlo robustness analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from plantsched.core import (
    CPSATConfig,
    GAConfig,
    ObjectiveWeights,
    SAConfig,
    SimulationConfig,
)
from plantsched.data import InstanceGeneratorConfig, generate_instance, load_problem_json
from plantsched.evaluation import compare_algorithms
from plantsched.simulation import run_monte_carlo, simulate_schedule
from plantsched.visualization import plot_monte_carlo_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PlantSched SimPy & Monte Carlo robustness analysis.")
    parser.add_argument("--instance", type=Path, default=None, help="Path to JSON instance.")
    parser.add_argument("--jobs", type=int, default=30, help="Number of jobs if generating.")
    parser.add_argument("--machines", type=int, default=3, help="Number of machines.")
    parser.add_argument("--products", type=int, default=6, help="Number of products.")
    parser.add_argument("--replications", type=int, default=30, help="Monte Carlo replications.")
    parser.add_argument("--cv", type=float, default=0.12, help="Processing time CV.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "results", help="Output directory.")
    args = parser.parse_args()

    problem = (
        load_problem_json(args.instance)
        if args.instance is not None
        else generate_instance(
            InstanceGeneratorConfig(
                num_jobs=args.jobs,
                num_machines=args.machines,
                num_products=args.products,
                seed=args.seed,
            )
        )
    )

    weights = ObjectiveWeights()
    comp = compare_algorithms(
        problem=problem,
        algorithms=("FCFS", "CP-SAT", "GA", "SA"),
        weights=weights,
        cp_sat_config=CPSATConfig(max_time_seconds=15.0, random_seed=args.seed, weights=weights),
        ga_config=GAConfig(population_size=50, generations=100, random_seed=args.seed, weights=weights),
        sa_config=SAConfig(max_iterations=1500, random_seed=args.seed, weights=weights),
    )

    sim_cfg = SimulationConfig(
        processing_time_cv=args.cv,
        enable_downtime=True,
        num_replications=args.replications,
        random_seed=args.seed,
    )

    mc_results = []
    mc_rows = []
    for algo_name, sched in comp.schedules.items():
        if not sched.has_solution:
            continue
        single_sim = simulate_schedule(problem, sched, config=sim_cfg, seed=args.seed)
        print(
            f"[{algo_name}] Single SimPy Run: Planned Makespan={single_sim.planned_makespan:.1f} -> "
            f"Simulated={single_sim.simulated_makespan:.1f}, Planned OTD={single_sim.planned_otd_pct:.1f}% -> "
            f"Simulated OTD={single_sim.simulated_otd_pct:.1f}%"
        )
        mc = run_monte_carlo(problem, sched, config=sim_cfg)
        mc_results.append(mc)
        mc_rows.append(mc.to_summary_dict())

    args.out_dir.mkdir(parents=True, exist_ok=True)
    mc_df = pd.DataFrame(mc_rows)
    mc_csv = args.out_dir / "monte_carlo_summary.csv"
    mc_df.to_csv(mc_csv, index=False)

    print("\n=== Monte Carlo Robustness Summary ===")
    print(mc_df.to_string(index=False))

    plots = plot_monte_carlo_results(mc_results, output_dir=args.out_dir)
    print(f"\nSaved Monte Carlo CSV to {mc_csv}")
    print(f"Saved robustness plots: {[str(p) for p in plots]}")


if __name__ == "__main__":
    main()
