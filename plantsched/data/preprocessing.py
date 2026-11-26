"""Data preprocessing and problem feature extraction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from plantsched.core.problem import SchedulingProblem


@dataclass
class ProblemSummary:
    """Descriptive manufacturing statistics for a SchedulingProblem."""

    name: str
    num_jobs: int
    num_machines: int
    num_products: int
    total_processing_time: float
    mean_processing_time: float
    mean_setup_time: float
    max_setup_time: float
    eligibility_density: float
    tight_due_date_ratio: float


def build_jobs_dataframe(problem: SchedulingProblem) -> pd.DataFrame:
    """Create an enriched DataFrame of jobs with eligibility and slack features."""
    rows = []
    for j_id, job in problem.jobs.items():
        eligible = problem.get_eligible_machines(j_id)
        min_proc = min(problem.get_processing_time(j_id, m_id) for m_id in eligible)
        slack = job.due_date - (job.arrival_time + min_proc)
        rows.append(
            {
                "job_id": j_id,
                "product_id": job.product_id,
                "quantity": job.quantity,
                "processing_time": job.processing_time,
                "min_effective_proc_time": min_proc,
                "arrival_time": job.arrival_time,
                "due_date": job.due_date,
                "priority": job.priority,
                "num_eligible_machines": len(eligible),
                "initial_slack": slack,
            }
        )
    return pd.DataFrame(rows)


def preprocess_problem(problem: SchedulingProblem) -> tuple[SchedulingProblem, ProblemSummary, pd.DataFrame]:
    """Validate problem data and compute summary diagnostics and job features."""
    problem.validate()
    jobs_df = build_jobs_dataframe(problem)

    off_diag = [
        v for (p1, p2), v in problem.changeover_matrix.matrix.items() if p1 != p2
    ]
    mean_setup = float(np.mean(off_diag)) if off_diag else 0.0
    max_setup = float(np.max(off_diag)) if off_diag else 0.0

    elig_counts = jobs_df["num_eligible_machines"].sum()
    elig_density = float(elig_counts) / (len(problem.jobs) * len(problem.machines))

    tight_ratio = float((jobs_df["initial_slack"] < jobs_df["min_effective_proc_time"]).mean())

    summary = ProblemSummary(
        name=problem.name,
        num_jobs=len(problem.jobs),
        num_machines=len(problem.machines),
        num_products=len(problem.products),
        total_processing_time=float(jobs_df["min_effective_proc_time"].sum()),
        mean_processing_time=float(jobs_df["min_effective_proc_time"].mean()),
        mean_setup_time=mean_setup,
        max_setup_time=max_setup,
        eligibility_density=elig_density,
        tight_due_date_ratio=tight_ratio,
    )
    return problem, summary, jobs_df
