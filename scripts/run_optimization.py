"""CLI script to run FCFS, CP-SAT, MILP (small), GA, and SA on a single instance."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plantsched.core import (
    CPSATConfig,
    GAConfig,
    MILPConfig,
    ObjectiveWeights,
    SAConfig,
)
from plantsched.data import InstanceGeneratorConfig, generate_instance, load_problem_json
from plantsched.evaluation import compare_algorithms
from plantsched.visualization import (
    plot_convergence,
    plot_gantt_matplotlib,
    plot_gantt_plotly,
    plot_kpi_comparison,
    plot_machine_utilization,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PlantSched multi-algorithm optimization.")
    parser.add_argument("--instance", type=Path, default=None, help="Path to JSON instance.")
    parser.add_argument("--jobs", type=int, default=20, help="Number of jobs if generating.")
    parser.add_argument("--machines", type=int, default=3, help="Number of machines.")
    parser.add_argument("--products", type=int, default=6, help="Number of products.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--cp-time", type=float, default=20.0, help="CP-SAT time limit (sec).")
    parser.add_argument("--milp-time", type=float, default=20.0, help="MILP time limit (sec).")
    parser.add_argument("--skip-milp", action="store_true", help="Skip MILP solver.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "results", help="Results directory.")
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
    algos = ["FCFS", "CP-SAT", "GA", "SA"]
    if not args.skip_milp and len(problem.jobs) <= 25:
        algos.insert(2, "MILP")

    comp = compare_algorithms(
        problem=problem,
        algorithms=tuple(algos),
        weights=weights,
        cp_sat_config=CPSATConfig(max_time_seconds=args.cp_time, random_seed=args.seed, weights=weights),
        milp_config=MILPConfig(max_time_seconds=args.milp_time, weights=weights),
        ga_config=GAConfig(population_size=60, generations=120, random_seed=args.seed, weights=weights),
        sa_config=SAConfig(max_iterations=2000, random_seed=args.seed, weights=weights),
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.out_dir / "optimization_comparison.csv"
    comp.summary_table.to_csv(csv_path, index=False)

    print("=== Optimization Comparison ===")
    print(comp.summary_table.to_string(index=False))

    for algo_name, sched in comp.schedules.items():
        if sched.has_solution and comp.kpis[algo_name].is_valid:
            slug = algo_name.lower().replace("-", "_").replace(" ", "_")
            plot_gantt_matplotlib(problem, sched, output_path=args.out_dir / f"gantt_{slug}.png")
            plot_gantt_plotly(problem, sched, output_path=args.out_dir / f"gantt_{slug}.html")
            plot_machine_utilization(comp.kpis[algo_name], output_path=args.out_dir / f"util_{slug}.png")
            plot_convergence(sched, output_path=args.out_dir / f"convergence_{slug}.png")

    plot_kpi_comparison(comp.summary_table, output_dir=args.out_dir)
    print(f"\nSaved comparison CSV, Gantt charts, and KPI plots to {args.out_dir}")


if __name__ == "__main__":
    main()
