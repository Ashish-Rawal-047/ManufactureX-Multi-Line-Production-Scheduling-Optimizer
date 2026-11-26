"""Shared schedule feasibility validator."""

from __future__ import annotations

from dataclasses import dataclass, field

from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule, ScheduledJob


@dataclass
class ValidationResult:
    """Outcome of schedule feasibility validation."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ScheduleValidator:
    """Verifies that a Schedule satisfies every manufacturing constraint."""

    @staticmethod
    def validate(
        problem: SchedulingProblem,
        schedule: Schedule,
        tol: float = 1e-6,
    ) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not schedule.scheduled_jobs:
            errors.append("Schedule contains no scheduled jobs.")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # 1. Completeness and uniqueness of jobs
        seen_jobs: dict[str, int] = {}
        for sj in schedule.scheduled_jobs:
            seen_jobs[sj.job_id] = seen_jobs.get(sj.job_id, 0) + 1

        for j_id, count in seen_jobs.items():
            if j_id not in problem.jobs:
                errors.append(f"Unknown job_id in schedule: {j_id!r}.")
            elif count > 1:
                errors.append(f"Duplicate job_id in schedule: {j_id!r} appears {count} times.")

        missing_jobs = set(problem.jobs.keys()) - set(seen_jobs.keys())
        if missing_jobs:
            errors.append(f"Missing jobs in schedule: {sorted(missing_jobs)}.")

        # 2. Per-job consistency, eligibility, arrival, availability, downtime
        by_machine: dict[str, list[ScheduledJob]] = {m_id: [] for m_id in problem.machines}
        for sj in schedule.scheduled_jobs:
            if sj.job_id not in problem.jobs:
                continue
            job = problem.jobs[sj.job_id]

            if sj.product_id != job.product_id:
                errors.append(
                    f"Job {sj.job_id}: scheduled product {sj.product_id!r} != job product {job.product_id!r}."
                )

            if sj.machine_id not in problem.machines:
                errors.append(f"Job {sj.job_id}: unknown machine {sj.machine_id!r}.")
                continue

            eligible = problem.get_eligible_machines(sj.job_id)
            if sj.machine_id not in eligible:
                errors.append(
                    f"Job {sj.job_id}: machine {sj.machine_id!r} is not eligible (eligible={eligible})."
                )

            machine = problem.machines[sj.machine_id]
            by_machine[sj.machine_id].append(sj)

            # Timing & duration consistency
            if sj.setup_duration < -tol:
                errors.append(f"Job {sj.job_id}: negative setup_duration {sj.setup_duration}.")
            if sj.processing_duration <= 0:
                errors.append(f"Job {sj.job_id}: non-positive processing_duration {sj.processing_duration}.")

            expected_proc = problem.get_processing_time(sj.job_id, sj.machine_id)
            if abs(sj.processing_duration - expected_proc) > tol:
                errors.append(
                    f"Job {sj.job_id}: processing_duration {sj.processing_duration} != expected {expected_proc}."
                )

            if abs(sj.start_time - sj.setup_start_time) > tol:
                errors.append(
                    f"Job {sj.job_id}: start_time {sj.start_time} != setup_start_time {sj.setup_start_time}."
                )

            if abs((sj.setup_start_time + sj.setup_duration) - sj.processing_start_time) > tol:
                errors.append(
                    f"Job {sj.job_id}: setup_start ({sj.setup_start_time}) + setup_duration ({sj.setup_duration}) "
                    f"!= processing_start ({sj.processing_start_time})."
                )

            if abs((sj.processing_start_time + sj.processing_duration) - sj.completion_time) > tol:
                errors.append(
                    f"Job {sj.job_id}: processing_start ({sj.processing_start_time}) + "
                    f"processing_duration ({sj.processing_duration}) != completion ({sj.completion_time})."
                )

            expected_tardiness = max(0.0, sj.completion_time - job.due_date)
            if abs(sj.tardiness - expected_tardiness) > tol:
                errors.append(
                    f"Job {sj.job_id}: tardiness {sj.tardiness} != expected {expected_tardiness}."
                )

            # Arrival & machine availability
            if sj.start_time < job.arrival_time - tol:
                errors.append(
                    f"Job {sj.job_id}: starts at {sj.start_time} before arrival_time {job.arrival_time}."
                )

            if sj.start_time < machine.available_from - tol:
                errors.append(
                    f"Job {sj.job_id}: starts at {sj.start_time} before machine {machine.machine_id} "
                    f"available_from {machine.available_from}."
                )

            if machine.available_until is not None and sj.completion_time > machine.available_until + tol:
                errors.append(
                    f"Job {sj.job_id}: completes at {sj.completion_time} after machine {machine.machine_id} "
                    f"available_until {machine.available_until}."
                )

            # Downtime window overlap check
            for dt in machine.downtime_windows:
                if sj.start_time < dt.end - tol and sj.completion_time > dt.start + tol:
                    errors.append(
                        f"Job {sj.job_id} on {machine.machine_id} [{sj.start_time}, {sj.completion_time}] "
                        f"overlaps downtime window [{dt.start}, {dt.end}]."
                    )

        # 3. Machine-level sequencing: no overlap + valid changeover transitions
        for m_id, ops in by_machine.items():
            machine = problem.machines[m_id]
            ops_sorted = sorted(ops, key=lambda o: (o.start_time, o.completion_time, o.job_id))
            prev_prod = machine.initial_product
            prev_completion = machine.available_from

            for idx, curr in enumerate(ops_sorted):
                if idx > 0 and curr.start_time < prev_completion - tol:
                    errors.append(
                        f"Overlap on machine {m_id}: job {ops_sorted[idx - 1].job_id} ends at "
                        f"{prev_completion}, but job {curr.job_id} starts at {curr.start_time}."
                    )

                expected_setup = problem.get_setup_time(prev_prod, curr.product_id)
                if abs(curr.setup_duration - expected_setup) > tol:
                    errors.append(
                        f"Invalid setup on machine {m_id} for job {curr.job_id} "
                        f"({prev_prod} -> {curr.product_id}): got {curr.setup_duration}, "
                        f"expected {expected_setup}."
                    )

                prev_prod = curr.product_id
                prev_completion = curr.completion_time

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)
