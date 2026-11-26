"""CLI script to generate synthetic PlantSched manufacturing datasets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plantsched.data import (
    InstanceGeneratorConfig,
    generate_instance,
    preprocess_problem,
    save_problem_csv,
    save_problem_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic PlantSched datasets.")
    parser.add_argument("--jobs", type=int, default=30, help="Number of jobs for primary instance.")
    parser.add_argument("--machines", type=int, default=3, help="Number of production lines.")
    parser.add_argument("--products", type=int, default=6, help="Number of products.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "data" / "generated",
        help="Output directory for generated datasets.",
    )
    parser.add_argument(
        "--all-sizes",
        action="store_true",
        help="Also generate standard benchmark sizes (10, 25, 50, 100, 250, 500).",
    )
    args = parser.parse_args()

    cfg = InstanceGeneratorConfig(
        num_jobs=args.jobs,
        num_machines=args.machines,
        num_products=args.products,
        seed=args.seed,
        include_downtime=True,
    )
    problem = generate_instance(cfg)
    _, summary, _ = preprocess_problem(problem)

    json_path = save_problem_json(problem, args.out_dir / f"{problem.name}.json")
    csv_dir = save_problem_csv(problem, args.out_dir / f"{problem.name}_csv")

    print(f"Generated primary instance: {problem.name}")
    print(f"  Summary: {summary}")
    print(f"  JSON:    {json_path}")
    print(f"  CSV dir: {csv_dir}")

    if args.all_sizes:
        for size in (10, 25, 50, 100, 250, 500):
            s_cfg = InstanceGeneratorConfig(
                num_jobs=size,
                num_machines=max(3, min(8, 2 + size // 40)),
                num_products=max(6, min(14, 4 + size // 30)),
                seed=args.seed + size,
            )
            p = generate_instance(s_cfg)
            p_path = save_problem_json(p, args.out_dir / f"{p.name}.json")
            print(f"  Saved {size}-job instance -> {p_path}")


if __name__ == "__main__":
    main()
