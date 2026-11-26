"""KPI comparison, scaling, convergence, and Monte Carlo visualizations."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from plantsched.core.schedule import Schedule
from plantsched.evaluation.metrics import ScheduleKPIs
from plantsched.simulation.monte_carlo import MonteCarloResult


def plot_kpi_comparison(
    comparison_df: pd.DataFrame,
    output_dir: str | Path,
    prefix: str = "kpi",
) -> list[Path]:
    """Generate multi-panel KPI comparison charts (PNG and HTML)."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = comparison_df[comparison_df["Valid"] == True].copy()  # noqa: E712
    if df.empty:
        return []

    created: list[Path] = []
    metrics = [
        ("Makespan", "Makespan (min)", "#2563EB"),
        ("Changeover", "Total Changeover Time (min)", "#D97706"),
        ("OTD_pct", "On-Time Delivery (%)", "#16A34A"),
        ("Utilization_pct", "Machine Utilization (%)", "#0891B2"),
        ("TotalTardiness", "Total Tardiness (min)", "#DC2626"),
        ("Runtime_s", "Solver Runtime (sec)", "#7C3AED"),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(15, 8.5))
    for ax, (col, label, color) in zip(axes.flat, metrics):
        bars = ax.bar(df["Algorithm"], df[col], color=color, alpha=0.88, edgecolor="#111827")
        ax.set_title(label, fontsize=10.5, fontweight="bold")
        ax.tick_params(axis="x", rotation=20)
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        for bar in bars:
            val = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                val,
                f"{val:.1f}" if col != "Runtime_s" else f"{val:.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    fig.suptitle("Algorithm KPI Comparison", fontsize=13, fontweight="bold")
    fig.tight_layout()
    png_path = out_dir / f"{prefix}_comparison.png"
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    created.append(png_path)

    # Interactive Plotly comparison
    melted = df.melt(
        id_vars=["Algorithm"],
        value_vars=["Makespan", "Changeover", "TotalTardiness", "OTD_pct", "Utilization_pct", "Runtime_s"],
        var_name="KPI",
        value_name="Value",
    )
    pfig = px.bar(
        melted,
        x="Algorithm",
        y="Value",
        color="Algorithm",
        facet_col="KPI",
        facet_col_wrap=3,
        title="Algorithm KPI Comparison (Interactive)",
        template="plotly_white",
    )
    pfig.update_yaxes(matches=None)
    html_path = out_dir / f"{prefix}_comparison.html"
    pfig.write_html(str(html_path))
    created.append(html_path)
    return created


def plot_machine_utilization(
    kpis: ScheduleKPIs,
    output_path: str | Path,
) -> Path:
    """Plot stacked processing, setup, idle, and downtime breakdown per machine."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    mdf = kpis.machine_table()

    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(len(mdf))
    ax.bar(x, mdf["total_processing_time"], label="Processing", color="#2563EB")
    ax.bar(
        x,
        mdf["total_setup_time"],
        bottom=mdf["total_processing_time"],
        label="Changeover / Setup",
        color="#F59E0B",
    )
    bottom2 = mdf["total_processing_time"] + mdf["total_setup_time"]
    ax.bar(x, mdf["idle_time"], bottom=bottom2, label="Idle Time", color="#D1D5DB")
    if mdf["downtime_time"].sum() > 0:
        bottom3 = bottom2 + mdf["idle_time"]
        ax.bar(x, mdf["downtime_time"], bottom=bottom3, label="Planned Downtime", color="#6B7280")

    ax.set_xticks(list(x))
    ax.set_xticklabels(
        [f"{row['machine_id']}\n({row['utilization_pct']:.1f}% util)" for _, row in mdf.iterrows()]
    )
    ax.set_ylabel("Time (minutes)")
    ax.set_title(f"Machine Time Breakdown — {kpis.algorithm}", fontweight="bold")
    ax.legend()
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_convergence(
    schedule: Schedule,
    output_path: str | Path,
) -> Path | None:
    """Plot GA or SA convergence curve from `schedule.metadata['convergence_history']`."""
    history = schedule.metadata.get("convergence_history")
    if not history:
        return None
    hdf = pd.DataFrame(history)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 4.8))
    if "generation" in hdf.columns:
        ax.plot(hdf["generation"], hdf["best_objective"], label="Best Objective", color="#2563EB", linewidth=2)
        if "mean_objective" in hdf.columns:
            ax.plot(
                hdf["generation"],
                hdf["mean_objective"],
                label="Population Mean",
                color="#93C5FD",
                linestyle="--",
            )
        ax.set_xlabel("Generation")
        ax.set_title(f"Genetic Algorithm Convergence — {schedule.problem_name}", fontweight="bold")
    else:
        ax.plot(hdf["iteration"], hdf["best_objective"], label="Best Objective", color="#16A34A", linewidth=2)
        ax.plot(
            hdf["iteration"],
            hdf["current_objective"],
            label="Current Accepted Objective",
            color="#86EFAC",
            alpha=0.75,
        )
        ax.set_xlabel("Iteration")
        ax.set_title(f"Simulated Annealing Convergence — {schedule.problem_name}", fontweight="bold")

    ax.set_ylabel("Weighted Objective Value")
    ax.legend()
    ax.grid(True, linestyle=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_scaling_experiments(
    scaling_df: pd.DataFrame,
    output_dir: str | Path,
) -> list[Path]:
    """Generate scaling benchmark plots: Runtime, Makespan, Changeover, and Quality vs Time."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = scaling_df[scaling_df["Valid"] == True].copy()  # noqa: E712
    if df.empty:
        return []

    created: list[Path] = []

    # 1. Runtime vs Problem Size + Makespan + Changeover (3-panel PNG)
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    for algo, sub in df.groupby("Algorithm"):
        sub = sub.sort_values("NumJobs")
        axes[0].plot(sub["NumJobs"], sub["Runtime_s"], marker="o", label=algo)
        axes[1].plot(sub["NumJobs"], sub["Makespan"], marker="o", label=algo)
        axes[2].plot(sub["NumJobs"], sub["Changeover"], marker="o", label=algo)

    axes[0].set_yscale("log")
    axes[0].set_title("Runtime vs. Problem Size (log scale)", fontweight="bold")
    axes[0].set_xlabel("Number of Jobs")
    axes[0].set_ylabel("Runtime (sec)")

    axes[1].set_title("Makespan vs. Problem Size", fontweight="bold")
    axes[1].set_xlabel("Number of Jobs")
    axes[1].set_ylabel("Makespan (min)")

    axes[2].set_title("Total Changeover vs. Problem Size", fontweight="bold")
    axes[2].set_xlabel("Number of Jobs")
    axes[2].set_ylabel("Changeover (min)")

    for ax in axes:
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.legend(fontsize=8)

    fig.suptitle("Exact Solver vs. Heuristic Scaling Performance", fontsize=13, fontweight="bold")
    fig.tight_layout()
    png1 = out_dir / "scaling_curves.png"
    fig.savefig(png1, dpi=150, bbox_inches="tight")
    plt.close(fig)
    created.append(png1)

    # 2. Solution Quality vs. Runtime scatter
    fig2, ax2 = plt.subplots(figsize=(8.5, 5.2))
    for algo, sub in df.groupby("Algorithm"):
        ax2.scatter(sub["Runtime_s"], sub["Objective"], s=60 + sub["NumJobs"] * 0.3, alpha=0.8, label=algo)
    ax2.set_xscale("log")
    ax2.set_title("Solution Quality (Objective) vs. Computation Time", fontweight="bold")
    ax2.set_xlabel("Runtime (sec, log scale)")
    ax2.set_ylabel("Weighted Objective (lower is better)")
    ax2.grid(True, linestyle=":", alpha=0.5)
    ax2.legend()
    fig2.tight_layout()
    png2 = out_dir / "quality_vs_runtime.png"
    fig2.savefig(png2, dpi=150, bbox_inches="tight")
    plt.close(fig2)
    created.append(png2)

    # 3. Interactive Plotly scaling chart
    pfig = px.line(
        df.sort_values("NumJobs"),
        x="NumJobs",
        y="Makespan",
        color="Algorithm",
        markers=True,
        hover_data=["Runtime_s", "Changeover", "OTD_pct", "Status"],
        title="Scaling Benchmark: Makespan vs. Problem Size",
        template="plotly_white",
    )
    html_path = out_dir / "scaling_makespan.html"
    pfig.write_html(str(html_path))
    created.append(html_path)
    return created


def plot_monte_carlo_results(
    mc_results: list[MonteCarloResult],
    output_dir: str | Path,
) -> list[Path]:
    """Plot Monte Carlo simulated makespan & OTD distributions vs deterministic plan."""
    if not mc_results:
        return []
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    labels = [r.algorithm for r in mc_results]
    makespan_samples = [r.replications_df["simulated_makespan"].to_numpy() for r in mc_results]
    otd_samples = [r.replications_df["simulated_otd_pct"].to_numpy() for r in mc_results]

    axes[0].boxplot(makespan_samples, tick_labels=labels, patch_artist=True)
    for idx, r in enumerate(mc_results, start=1):
        axes[0].scatter(
            [idx], [r.planned_makespan], color="#DC2626", marker="D", s=55, zorder=5,
            label="Planned Deterministic" if idx == 1 else "",
        )
    axes[0].set_title("Simulated Makespan Distribution vs. Planned", fontweight="bold")
    axes[0].set_ylabel("Makespan (min)")
    axes[0].legend()
    axes[0].grid(axis="y", linestyle=":", alpha=0.5)

    axes[1].boxplot(otd_samples, tick_labels=labels, patch_artist=True)
    for idx, r in enumerate(mc_results, start=1):
        axes[1].scatter(
            [idx], [r.planned_otd_pct], color="#DC2626", marker="D", s=55, zorder=5,
            label="Planned Deterministic" if idx == 1 else "",
        )
    axes[1].set_title("Simulated On-Time Delivery (%) Distribution", fontweight="bold")
    axes[1].set_ylabel("OTD (%)")
    axes[1].legend()
    axes[1].grid(axis="y", linestyle=":", alpha=0.5)

    fig.suptitle("Monte Carlo Robustness Analysis (Stochastic Plant Execution)", fontsize=13, fontweight="bold")
    fig.tight_layout()
    png_path = out_dir / "monte_carlo_robustness.png"
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    created.append(png_path)

    # Plotly distribution HTML
    combined = pd.concat(
        [r.replications_df.assign(Algorithm=r.algorithm) for r in mc_results],
        ignore_index=True,
    )
    pfig = px.box(
        combined,
        x="Algorithm",
        y="simulated_makespan",
        color="Algorithm",
        points="all",
        title="Monte Carlo Simulated Makespan Robustness",
        template="plotly_white",
    )
    html_path = out_dir / "monte_carlo_robustness.html"
    pfig.write_html(str(html_path))
    created.append(html_path)
    return created
