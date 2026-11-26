"""CLI script to run and validate the FCFS baseline scheduler."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plantsched.baselines import solve_fcfs
from plantsched.core import ObjectiveWeights
from plantsched.data import InstanceGeneratorConfig, generate_instance, load_problem_json
from plantsched.evaluation import evaluate_schedule
from plantsched.visualization import plot_gantt_matplotlib, plot_gantt_plotly


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PlantSched FCFS baseline.")
    parser.add_argument("--instance", type=Path, default=None, help="Path to JSON problem file.")
    parser.add_argument("--jobs", type=int, default=30, help="Jobs if generating on the fly.")
    parser.add_argument("--machines", type=int, default=3, help="Machines if generating.")
    parser.add_argument("--products", type=int, default=6, help="Products if generating.")
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
    schedule = solve_fcfs(problem, weights=weights)
    kpis = evaluate_schedule(problem, schedule, weights=weights)

    print("=== FCFS Baseline Summary ===")
    for k, v in kpis.to_summary_dict().items():
        print(f"  {k}: {v}")
    print("\nMachine Breakdown:")
    print(kpis.machine_table().to_string(index=False))

    png = args.out_dir / "fcfs_gantt.png"
    html = args.out_dir / "fcfs_gantt.html"
    plot_gantt_matplotlib(problem, schedule, output_path=png)
    plot_gantt_plotly(problem, schedule, output_path=html)
    print(f"\nSaved Gantt charts to {png} and {html}")


if __name__ == "__main__":
    main()
