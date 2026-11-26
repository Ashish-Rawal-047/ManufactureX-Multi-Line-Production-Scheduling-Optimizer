"""Production schedule Gantt chart visualization (Matplotlib PNG and Plotly HTML)."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import plotly.graph_objects as go

from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule

_PALETTE = [
    "#2563EB",
    "#16A34A",
    "#EA580C",
    "#9333EA",
    "#0891B2",
    "#DB2777",
    "#CA8A04",
    "#4F46E5",
    "#059669",
    "#DC2626",
    "#0284C7",
    "#7C3AED",
    "#65A30D",
    "#D97706",
]


def _product_color_map(problem: SchedulingProblem) -> dict[str, str]:
    product_ids = sorted(problem.products.keys())
    return {pid: _PALETTE[idx % len(_PALETTE)] for idx, pid in enumerate(product_ids)}


def plot_gantt_matplotlib(
    problem: SchedulingProblem,
    schedule: Schedule,
    output_path: str | Path | None = None,
    title: str | None = None,
    dpi: int = 150,
) -> plt.Figure:
    """Render a static Matplotlib Gantt chart showing jobs, setups, and downtimes."""
    if not schedule.has_solution:
        raise ValueError("Cannot plot Gantt chart for an empty or infeasible schedule.")

    colors = _product_color_map(problem)
    machine_ids = list(problem.machines.keys())
    n_machines = len(machine_ids)

    fig_height = max(3.6, 1.15 * n_machines + 1.8)
    fig, ax = plt.subplots(figsize=(13, fig_height))

    y_positions = {m_id: n_machines - 1 - idx for idx, m_id in enumerate(machine_ids)}

    # Draw planned downtime windows first
    for m_id in machine_ids:
        y = y_positions[m_id]
        for dt in problem.machines[m_id].downtime_windows:
            ax.barh(
                y,
                dt.duration,
                left=dt.start,
                height=0.62,
                color="#E5E7EB",
                edgecolor="#6B7280",
                hatch="///",
                alpha=0.85,
                zorder=1,
            )

    # Draw setup intervals and job processing intervals
    for sj in schedule.scheduled_jobs:
        y = y_positions[sj.machine_id]
        color = colors.get(sj.product_id, "#3B82F6")

        if sj.setup_duration > 1e-6:
            ax.barh(
                y,
                sj.setup_duration,
                left=sj.setup_start_time,
                height=0.56,
                color="#FBBF24",
                edgecolor="#78350F",
                hatch="\\\\",
                linewidth=0.8,
                zorder=2,
            )
            if sj.setup_duration >= schedule.makespan * 0.025:
                ax.text(
                    sj.setup_start_time + sj.setup_duration / 2.0,
                    y,
                    "S",
                    ha="center",
                    va="center",
                    fontsize=7,
                    fontweight="bold",
                    color="#451A03",
                    zorder=4,
                )

        edge_col = "#991B1B" if sj.tardiness > 1e-6 else "#111827"
        line_w = 1.4 if sj.tardiness > 1e-6 else 0.8
        ax.barh(
            y,
            sj.processing_duration,
            left=sj.processing_start_time,
            height=0.56,
            color=color,
            edgecolor=edge_col,
            linewidth=line_w,
            alpha=0.92,
            zorder=3,
        )

        if sj.processing_duration >= schedule.makespan * 0.03:
            ax.text(
                sj.processing_start_time + sj.processing_duration / 2.0,
                y,
                f"{sj.job_id}\n({sj.product_id})",
                ha="center",
                va="center",
                fontsize=7.5,
                fontweight="bold",
                color="white",
                zorder=4,
            )

    # Makespan marker
    makespan = schedule.makespan
    ax.axvline(makespan, color="#DC2626", linestyle="--", linewidth=1.4, zorder=5)
    ax.text(
        makespan,
        n_machines - 0.35,
        f" Makespan = {makespan:.1f}",
        color="#DC2626",
        fontsize=9,
        fontweight="bold",
        va="bottom",
    )

    ax.set_yticks([y_positions[m] for m in machine_ids])
    ax.set_yticklabels([f"{problem.machines[m].name} ({m})" for m in machine_ids])
    ax.set_xlabel("Time (minutes)")
    ax.set_xlim(0, max(10.0, makespan * 1.10))
    ax.set_ylim(-0.6, n_machines - 0.2)
    ax.grid(axis="x", linestyle=":", alpha=0.55, zorder=0)

    chart_title = title or (
        f"Production Gantt Chart — {schedule.algorithm} "
        f"(Makespan: {makespan:.1f}, Changeover: {schedule.total_changeover:.1f})"
    )
    ax.set_title(chart_title, fontsize=12, fontweight="bold", pad=12)

    # Legend
    handles = [
        mpatches.Patch(facecolor=colors[pid], edgecolor="#111827", label=f"Product {pid}")
        for pid in sorted(colors.keys())
    ]
    handles.append(
        mpatches.Patch(
            facecolor="#FBBF24", edgecolor="#78350F", hatch="\\\\", label="Setup / Changeover"
        )
    )
    if any(problem.machines[m].downtime_windows for m in machine_ids):
        handles.append(
            mpatches.Patch(
                facecolor="#E5E7EB", edgecolor="#6B7280", hatch="///", label="Planned Downtime"
            )
        )
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=min(6, len(handles)),
        fontsize=8,
        frameon=True,
    )

    fig.tight_layout()
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=dpi, bbox_inches="tight")
    return fig


def plot_gantt_plotly(
    problem: SchedulingProblem,
    schedule: Schedule,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> go.Figure:
    """Create an interactive Plotly production Gantt chart with setup & job hover details."""
    if not schedule.has_solution:
        raise ValueError("Cannot plot Gantt chart for an empty or infeasible schedule.")

    colors = _product_color_map(problem)
    machine_ids = list(problem.machines.keys())
    fig = go.Figure()

    shown_legends: set[str] = set()

    # Planned downtime blocks
    for m_id in machine_ids:
        for dt in problem.machines[m_id].downtime_windows:
            show_leg = "Planned Downtime" not in shown_legends
            shown_legends.add("Planned Downtime")
            fig.add_trace(
                go.Bar(
                    x=[dt.duration],
                    y=[m_id],
                    base=[dt.start],
                    orientation="h",
                    name="Planned Downtime",
                    legendgroup="Planned Downtime",
                    showlegend=show_leg,
                    marker=dict(color="rgba(156,163,175,0.55)", line=dict(color="#4B5563", width=1)),
                    hovertemplate=(
                        f"<b>Downtime</b><br>Machine: {m_id}<br>"
                        f"Window: {dt.start:.1f} - {dt.end:.1f}<br>Reason: {dt.reason}<extra></extra>"
                    ),
                )
            )

    # Setups and jobs
    for sj in schedule.scheduled_jobs:
        if sj.setup_duration > 1e-6:
            show_setup = "Changeover/Setup" not in shown_legends
            shown_legends.add("Changeover/Setup")
            fig.add_trace(
                go.Bar(
                    x=[sj.setup_duration],
                    y=[sj.machine_id],
                    base=[sj.setup_start_time],
                    orientation="h",
                    name="Changeover/Setup",
                    legendgroup="Changeover/Setup",
                    showlegend=show_setup,
                    marker=dict(color="#FBBF24", line=dict(color="#78350F", width=1)),
                    text="S",
                    textposition="inside",
                    hovertemplate=(
                        f"<b>Changeover for {sj.job_id}</b><br>"
                        f"Machine: {sj.machine_id}<br>"
                        f"Transition: {sj.predecessor_product or 'None'} → {sj.product_id}<br>"
                        f"Setup: {sj.setup_start_time:.1f} - {sj.processing_start_time:.1f} "
                        f"({sj.setup_duration:.1f} min)<extra></extra>"
                    ),
                )
            )

        prod_label = f"Product {sj.product_id}"
        show_prod = prod_label not in shown_legends
        shown_legends.add(prod_label)
        fig.add_trace(
            go.Bar(
                x=[sj.processing_duration],
                y=[sj.machine_id],
                base=[sj.processing_start_time],
                orientation="h",
                name=prod_label,
                legendgroup=prod_label,
                showlegend=show_prod,
                marker=dict(
                    color=colors.get(sj.product_id, "#3B82F6"),
                    line=dict(color="#DC2626" if sj.tardiness > 1e-6 else "#111827", width=1.2),
                ),
                text=sj.job_id,
                textposition="inside",
                hovertemplate=(
                    f"<b>{sj.job_id} ({sj.product_id})</b><br>"
                    f"Machine: {sj.machine_id}<br>"
                    f"Processing: {sj.processing_start_time:.1f} - {sj.completion_time:.1f} "
                    f"({sj.processing_duration:.1f} min)<br>"
                    f"Due Date: {sj.due_date:.1f}<br>"
                    f"Tardiness: {sj.tardiness:.1f}<extra></extra>"
                ),
            )
        )

    makespan = schedule.makespan
    fig.add_vline(
        x=makespan,
        line_dash="dash",
        line_color="#DC2626",
        annotation_text=f"Makespan={makespan:.1f}",
        annotation_position="top right",
    )

    chart_title = title or (
        f"Interactive Gantt — {schedule.algorithm} "
        f"(Makespan: {makespan:.1f}, Changeover: {schedule.total_changeover:.1f})"
    )
    fig.update_layout(
        title=chart_title,
        barmode="overlay",
        xaxis_title="Time (minutes)",
        yaxis_title="Production Line",
        yaxis=dict(categoryorder="array", categoryarray=list(reversed(machine_ids))),
        height=max(380, 95 * len(machine_ids) + 140),
        template="plotly_white",
    )

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(out))
    return fig
