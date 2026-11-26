"""Schedule chromosome representation and deterministic feasible decoders."""

from __future__ import annotations

from dataclasses import dataclass

from plantsched.core.config import ObjectiveWeights, SolverStatus
from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule, ScheduledJob
from plantsched.core.scheduling_utils import compute_earliest_slot


@dataclass
class Chromosome:
    """Valid scheduling solution encoding: job permutation + eligible machine map."""

    job_sequence: list[str]
    machine_choices: dict[str, str]

    def copy(self) -> Chromosome:
        return Chromosome(
            job_sequence=list(self.job_sequence),
            machine_choices=dict(self.machine_choices),
        )


def validate_chromosome(problem: SchedulingProblem, chrom: Chromosome) -> bool:
    """Verify chromosome contains an exact permutation of jobs and eligible machines."""
    expected_jobs = set(problem.jobs.keys())
    if len(chrom.job_sequence) != len(expected_jobs):
        return False
    if set(chrom.job_sequence) != expected_jobs:
        return False
    if set(chrom.machine_choices.keys()) != expected_jobs:
        return False
    for j_id, m_id in chrom.machine_choices.items():
        if m_id not in problem.get_eligible_machines(j_id):
            return False
    return True


def build_greedy_chromosome(
    problem: SchedulingProblem,
    job_sequence: list[str],
    weights: ObjectiveWeights | None = None,
) -> Chromosome:
    """Assign each job in `job_sequence` greedily to the best eligible machine."""
    w = weights or ObjectiveWeights()
    machine_free: dict[str, float] = {
        m_id: m.available_from for m_id, m in problem.machines.items()
    }
    machine_prod: dict[str, str | None] = {
        m_id: m.initial_product for m_id, m in problem.machines.items()
    }

    machine_choices: dict[str, str] = {}
    for j_id in job_sequence:
        job = problem.jobs[j_id]
        eligible = problem.get_eligible_machines(j_id)
        best_op: ScheduledJob | None = None
        best_score: tuple[float, float, str] | None = None

        for m_id in eligible:
            op = compute_earliest_slot(
                problem=problem,
                job_id=j_id,
                machine_id=m_id,
                machine_free_time=machine_free[m_id],
                machine_current_product=machine_prod[m_id],
            )
            if op is None:
                continue
            marginal = (
                w.alpha * op.completion_time
                + w.beta * job.priority * op.tardiness
                + w.gamma * op.setup_duration
            )
            score = (marginal, op.completion_time, m_id)
            if best_score is None or score < best_score:
                best_score = score
                best_op = op

        chosen_m = best_op.machine_id if best_op is not None else eligible[0]
        machine_choices[j_id] = chosen_m
        if best_op is not None:
            machine_free[chosen_m] = best_op.completion_time
            machine_prod[chosen_m] = job.product_id

    return Chromosome(job_sequence=list(job_sequence), machine_choices=machine_choices)


def decode_chromosome(
    problem: SchedulingProblem,
    chrom: Chromosome,
    weights: ObjectiveWeights,
    algorithm_name: str = "Heuristic",
    runtime_seconds: float = 0.0,
) -> tuple[Schedule, float]:
    """Decode a Chromosome into a constraint-feasible Schedule and objective value.

    If a chosen machine cannot fit a job before `machine.available_until`,
    the decoder repairs the assignment using alternative eligible machines.
    """
    machine_free: dict[str, float] = {
        m_id: m.available_from for m_id, m in problem.machines.items()
    }
    machine_prod: dict[str, str | None] = {
        m_id: m.initial_product for m_id, m in problem.machines.items()
    }

    scheduled: list[ScheduledJob] = []
    for j_id in chrom.job_sequence:
        preferred_m = chrom.machine_choices[j_id]
        eligible = problem.get_eligible_machines(j_id)
        candidates = [preferred_m] + [m for m in eligible if m != preferred_m]

        placed: ScheduledJob | None = None
        for m_id in candidates:
            op = compute_earliest_slot(
                problem=problem,
                job_id=j_id,
                machine_id=m_id,
                machine_free_time=machine_free[m_id],
                machine_current_product=machine_prod[m_id],
            )
            if op is not None:
                placed = op
                break

        if placed is None:
            sched = Schedule(
                problem_name=problem.name,
                algorithm=algorithm_name,
                scheduled_jobs=[],
                solver_status=SolverStatus.INFEASIBLE,
                runtime_seconds=runtime_seconds,
                metadata={"reason": f"Infeasible placement for job {j_id}."},
            )
            return sched, float("inf")

        scheduled.append(placed)
        machine_free[placed.machine_id] = placed.completion_time
        machine_prod[placed.machine_id] = placed.product_id

    sched = Schedule(
        problem_name=problem.name,
        algorithm=algorithm_name,
        scheduled_jobs=scheduled,
        solver_status=SolverStatus.FEASIBLE,
        runtime_seconds=runtime_seconds,
    )
    obj = sched.compute_objective(weights)
    sched.objective_value = obj
    return sched, obj
