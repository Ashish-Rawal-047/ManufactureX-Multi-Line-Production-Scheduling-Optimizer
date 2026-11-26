"""CLI script to execute scaling benchmarks across 10 to 500 jobs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plantsched.evaluation import ScalingBenchmarkConfig, run_scaling_benchmark
from plantsched.visualization import plot_scaling_experiments


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PlantSched scaling benchmarks.")
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=[10, 25, 50, 100, 250, 500],
        help="Job sizes to benchmark.",
    )
    parser.add_argument("--cp-time", type=float, default=15.0, help="CP-SAT time limit (sec).")
    parser.add_argument("--milp-time", type=float, default=15.0, help="MILP time limit (sec).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "results", help="Output directory.")
    args = parser.parse_args()

    cfg = ScalingBenchmarkConfig(
        job_sizes=tuple(args.sizes),
        cp_sat_time_limit=args.cp_time,
        milp_time_limit=args.milp_time,
        seed=args.seed,
    )
    csv_path = args.out_dir / "scaling_benchmark.csv"
    df = run_scaling_benchmark(cfg, output_csv=csv_path)

    print("=== Scaling Benchmark Results ===")
    cols = ["NumJobs", "Algorithm", "Status", "Valid", "Makespan", "Changeover", "OTD_pct", "Objective", "Gap_pct", "Runtime_s"]
    print(df[cols].to_string(index=False))

    plots = plot_scaling_experiments(df, output_dir=args.out_dir)
    print(f"\nSaved benchmark CSV to {csv_path}")
    print(f"Saved scaling plots: {[str(p) for p in plots]}")


if __name__ == "__main__":
    main()
