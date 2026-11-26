"""Centralized KPI and evaluation engine for PlantSched schedules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from plantsched.core.config import ObjectiveWeights, SolverStatus
from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule
from plantsched.core.validator import ScheduleValidator


@dataclass
class MachineKPI:
    """Machine-level utilization, setup, processing, and idle time metrics.

    Note: `busy_time` includes both `total_processing_time` and `total_setup_time`.
    `processing_utilization_pct` is reported separately to isolate value-adding runtime.
    """

    machine_id: str
    num_jobs: int
    total_processing_time: float
    total_setup_time: float
    busy_time: float
    downtime_time: float
    available_time: float
    idle_time: float
    utilization_pct: float
    processing_utilization_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "machine_id": self.machine_id,
            "num_jobs": self.num_jobs,
            "total_processing_time": round(self.total_processing_time, 4),
            "total_setup_time": round(self.total_setup_time, 4),
            "busy_time": round(self.busy_time, 4),
            "downtime_time": round(self.downtime_time, 4),
            "available_time": round(self.available_time, 4),
            "idle_time": round(self.idle_time, 4),
            "utilization_pct": round(self.utilization_pct, 2),
            "processing_utilization_pct": round(self.processing_utilization_pct, 2),
        }


@dataclass
class ScheduleKPIs:
    """Comprehensive plant-level and machine-level KPI report for a Schedule."""

    problem_name: str
    algorithm: str
    solver_status: SolverStatus
    is_valid: bool
    validation_errors: list[str]
    runtime_seconds: float
    objective_value: float | None
    best_bound: float | None
    optimality_gap: float | None
    makespan: float
    total_changeover_time: float
    total_processing_time: float
    total_tardiness: float
    weighted_tardiness: float
    max_tardiness: float
    num_late_orders: int
    total_jobs: int
    on_time_delivery_pct: float
    avg_completion_time: float
    mean_utilization_pct: float
    mean_processing_utilization_pct: float
    total_idle_time: float
    approx_availability_pct: float
    approx_performance_pct: float
    approx_oee_pct: float
    oee_note: str
    machine_kpis: dict[str, MachineKPI] = field(default_factory=dict)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "Problem": self.problem_name,
            "Algorithm": self.algorithm,
            "Status": self.solver_status.value,
            "Valid": self.is_valid,
            "Makespan": round(self.makespan, 2),
            "Changeover": round(self.total_changeover_time, 2),
            "TotalTardiness": round(self.total_tardiness, 2),
            "WeightedTardiness": round(self.weighted_tardiness, 2),
            "MaxTardiness": round(self.max_tardiness, 2),
            "LateOrders": self.num_late_orders,
            "OTD_pct": round(self.on_time_delivery_pct, 2),
            "Utilization_pct": round(self.mean_utilization_pct, 2),
            "ProcUtilization_pct": round(self.mean_processing_utilization_pct, 2),
            "TotalIdleTime": round(self.total_idle_time, 2),
            "AvgCompletion": round(self.avg_completion_time, 2),
            "ApproxOEE_pct": round(self.approx_oee_pct, 2),
            "Objective": round(self.objective_value, 2)
            if self.objective_value is not None
            else None,
            "BestBound": round(self.best_bound, 2) if self.best_bound is not None else None,
            "Gap_pct": round(self.optimality_gap * 100.0, 2)
            if self.optimality_gap is not None
            else None,
            "Runtime_s": round(self.runtime_seconds, 4),
        }

    def machine_table(self) -> pd.DataFrame:
        rows = [mk.to_dict() for mk in self.machine_kpis.values()]
        return pd.DataFrame(rows)


def _overlap_duration(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def evaluate_schedule(
    problem: SchedulingProblem,
    schedule: Schedule,
    weights: ObjectiveWeights | None = None,
) -> ScheduleKPIs:
    """Validate a schedule and compute all manufacturing and solver KPIs."""
    w = weights or ObjectiveWeights()
    validation = ScheduleValidator.validate(problem, schedule)

    if not schedule.scheduled_jobs or not validation.is_valid:
        return ScheduleKPIs(
            problem_name=problem.name,
            algorithm=schedule.algorithm,
            solver_status=schedule.solver_status,
            is_valid=validation.is_valid,
            validation_errors=validation.errors,
            runtime_seconds=schedule.runtime_seconds,
            objective_value=schedule.objective_value,
            best_bound=schedule.best_bound,
            optimality_gap=schedule.optimality_gap,
            makespan=0.0,
            total_changeover_time=0.0,
            total_processing_time=0.0,
            total_tardiness=0.0,
            weighted_tardiness=0.0,
            max_tardiness=0.0,
            num_late_orders=len(problem.jobs),
            total_jobs=len(problem.jobs),
            on_time_delivery_pct=0.0,
            avg_completion_time=0.0,
            mean_utilization_pct=0.0,
            mean_processing_utilization_pct=0.0,
            total_idle_time=0.0,
            approx_availability_pct=0.0,
            approx_performance_pct=0.0,
            approx_oee_pct=0.0,
            oee_note="Invalid or empty schedule; KPIs not computed.",
            machine_kpis={},
        )

    makespan = schedule.makespan
    total_changeover = schedule.total_changeover
    total_processing = sum(sj.processing_duration for sj in schedule.scheduled_jobs)
    total_tardiness = schedule.total_tardiness
    weighted_tardiness = schedule.weighted_tardiness
    max_tardiness = max(sj.tardiness for sj in schedule.scheduled_jobs)
    num_late = sum(1 for sj in schedule.scheduled_jobs if sj.tardiness > 1e-6)
    total_jobs = len(problem.jobs)
    otd_pct = ((total_jobs - num_late) / total_jobs) * 100.0
    avg_comp = sum(sj.completion_time for sj in schedule.scheduled_jobs) / total_jobs
    obj_val = schedule.compute_objective(w)

    machine_kpis: dict[str, MachineKPI] = {}
    total_avail_all = 0.0
    total_horizon_all = 0.0
    total_downtime_all = 0.0
    total_idle_all = 0.0

    for m_id, machine in problem.machines.items():
        ops = schedule.get_machine_sequence(m_id)
        m_proc = sum(op.processing_duration for op in ops)
        m_setup = sum(op.setup_duration for op in ops)
        m_busy = m_proc + m_setup

        horizon_end = makespan
        if machine.available_until is not None:
            horizon_end = min(makespan, machine.available_until)
        window_len = max(0.0, horizon_end - machine.available_from)
        m_downtime = sum(
            _overlap_duration(machine.available_from, horizon_end, dt.start, dt.end)
            for dt in machine.downtime_windows
        )
        m_avail = max(0.0, window_len - m_downtime)
        m_idle = max(0.0, m_avail - m_busy)

        util_pct = (m_busy / m_avail * 100.0) if m_avail > 1e-9 else 0.0
        proc_util_pct = (m_proc / m_avail * 100.0) if m_avail > 1e-9 else 0.0

        machine_kpis[m_id] = MachineKPI(
            machine_id=m_id,
            num_jobs=len(ops),
            total_processing_time=m_proc,
            total_setup_time=m_setup,
            busy_time=m_busy,
            downtime_time=m_downtime,
            available_time=m_avail,
            idle_time=m_idle,
            utilization_pct=util_pct,
            processing_utilization_pct=proc_util_pct,
        )
        total_avail_all += m_avail
        total_horizon_all += window_len
        total_downtime_all += m_downtime
        total_idle_all += m_idle

    mean_util = (
        sum(mk.utilization_pct for mk in machine_kpis.values()) / len(machine_kpis)
        if machine_kpis
        else 0.0
    )
    mean_proc_util = (
        sum(mk.processing_utilization_pct for mk in machine_kpis.values()) / len(machine_kpis)
        if machine_kpis
        else 0.0
    )

    # Approximate OEE = Availability * Performance * Quality (Quality assumed 100% since defects are not modeled)
    # Availability = (Available Time - Setup Loss) / Horizon; Performance = Processing Time / Busy Time
    if total_horizon_all > 1e-9 and (total_processing + total_changeover) > 1e-9:
        avail_ratio = max(0.0, (total_avail_all - total_changeover - total_idle_all) / total_horizon_all)
        perf_ratio = total_processing / (total_processing + total_changeover)
        # Note: avail_ratio * perf_ratio == total_processing / total_horizon_all
        # Better decomposition:
        # Availability (planned uptime minus downtime & changeover loss) = (total_avail_all - total_changeover) / total_horizon_all
        # Performance (active running ratio within net run time) = total_processing / max(1e-9, total_avail_all - total_changeover)
        net_avail = max(0.0, total_avail_all - total_changeover)
        avail_pct = (net_avail / total_horizon_all) * 100.0
        perf_pct = (total_processing / net_avail * 100.0) if net_avail > 1e-9 else 0.0
        oee_pct = (avail_pct / 100.0) * (perf_pct / 100.0) * 100.0
    else:
        avail_pct = 0.0
        perf_pct = 0.0
        oee_pct = 0.0

    return ScheduleKPIs(
        problem_name=problem.name,
        algorithm=schedule.algorithm,
        solver_status=schedule.solver_status,
        is_valid=validation.is_valid,
        validation_errors=validation.errors,
        runtime_seconds=schedule.runtime_seconds,
        objective_value=obj_val,
        best_bound=schedule.best_bound,
        optimality_gap=schedule.optimality_gap,
        makespan=makespan,
        total_changeover_time=total_changeover,
        total_processing_time=total_processing,
        total_tardiness=total_tardiness,
        weighted_tardiness=weighted_tardiness,
        max_tardiness=max_tardiness,
        num_late_orders=num_late,
        total_jobs=total_jobs,
        on_time_delivery_pct=otd_pct,
        avg_completion_time=avg_comp,
        mean_utilization_pct=mean_util,
        mean_processing_utilization_pct=mean_proc_util,
        total_idle_time=total_idle_all,
        approx_availability_pct=avail_pct,
        approx_performance_pct=perf_pct,
        approx_oee_pct=oee_pct,
        oee_note=(
            "Approximated OEE = Availability * Performance * 1.0 (Quality assumed 100%; "
            "no defect/scrap data modeled). Utilization includes setup + processing time."
        ),
        machine_kpis=machine_kpis,
    )
