"""Discrete-event SimPy plant simulator executing an optimized schedule."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import simpy

from plantsched.core.config import SimulationConfig
from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule, ScheduledJob
from plantsched.simulation.events import (
    SimulationEvent,
    sample_arrival_delay,
    sample_breakdown_delay,
    sample_processing_time,
)
from plantsched.simulation.machine import SimulatedMachine


@dataclass
class SimulatedJobOutcome:
    """Planned vs actual simulated execution metrics for a single job."""

    job_id: str
    product_id: str
    machine_id: str
    planned_start: float
    planned_completion: float
    actual_arrival: float
    actual_start: float
    actual_setup_duration: float
    actual_processing_duration: float
    breakdown_delay: float
    actual_completion: float
    due_date: float
    planned_tardiness: float
    actual_tardiness: float
    waiting_time: float
    schedule_deviation: float


@dataclass
class SimulationResult:
    """Aggregated result of a single discrete-event simulation run."""

    problem_name: str
    algorithm: str
    seed: int
    planned_makespan: float
    simulated_makespan: float
    planned_otd_pct: float
    simulated_otd_pct: float
    planned_total_tardiness: float
    simulated_total_tardiness: float
    simulated_utilization_pct: float
    mean_waiting_time: float
    mean_schedule_deviation: float
    max_schedule_deviation: float
    job_outcomes: list[SimulatedJobOutcome] = field(default_factory=list)
    events: list[SimulationEvent] = field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([vars(o) for o in self.job_outcomes])


def simulate_schedule(
    problem: SchedulingProblem,
    schedule: Schedule,
    config: SimulationConfig | None = None,
    seed: int | None = None,
) -> SimulationResult:
    """Execute a deterministic Schedule inside a stochastic SimPy discrete-event plant.

    Each machine runs a SimPy process executing its planned job queue in sequence:
    1. Job arrival (with optional stochastic arrival delay)
    2. Queue wait for machine availability / planned start
    3. Machine resource acquisition (`simpy.Resource`)
    4. Planned downtime avoidance
    5. Sequence-dependent changeover/setup (`env.timeout`)
    6. Production processing with stochastic variability (`env.timeout`)
    7. Optional unplanned machine breakdown delay (`env.timeout`)
    8. Machine release and completion recording
    """
    if not schedule.has_solution:
        raise ValueError("Cannot simulate an infeasible or empty schedule.")

    cfg = config or SimulationConfig()
    run_seed = cfg.random_seed if seed is None else seed
    rng = np.random.default_rng(run_seed)

    env = simpy.Environment()
    sim_machines: dict[str, SimulatedMachine] = {
        m_id: SimulatedMachine(env=env, machine=machine)
        for m_id, machine in problem.machines.items()
    }
    events: list[SimulationEvent] = []
    outcomes: list[SimulatedJobOutcome] = []

    def run_machine_queue(m_id: str, planned_ops: list[ScheduledJob]):
        sm = sim_machines[m_id]
        if sm.machine.available_from > env.now:
            yield env.timeout(sm.machine.available_from - env.now)

        for planned in planned_ops:
            job = problem.jobs[planned.job_id]
            arr_delay = sample_arrival_delay(cfg.arrival_delay_prob, cfg.max_arrival_delay, rng)
            actual_arrival = job.arrival_time + arr_delay
            events.append(
                SimulationEvent(
                    event_type="JOB_ARRIVAL",
                    time=actual_arrival,
                    machine_id=m_id,
                    job_id=job.job_id,
                    product_id=job.product_id,
                    details={"planned_arrival": job.arrival_time, "delay": arr_delay},
                )
            )

            # Wait for job arrival and planned start release
            release_target = max(env.now, actual_arrival, planned.start_time)
            if release_target > env.now:
                yield env.timeout(release_target - env.now)

            with sm.resource.request() as req:
                yield req

                setup_dur = problem.get_setup_time(sm.current_product, job.product_id)
                proc_dur = sample_processing_time(
                    planned.processing_duration, cfg.processing_time_cv, rng
                )
                bd_delay = (
                    sample_breakdown_delay(proc_dur, cfg.mtbf, cfg.mttr, rng)
                    if cfg.enable_downtime
                    else 0.0
                )

                # Respect planned downtime windows
                total_need = setup_dur + proc_dur + bd_delay
                feasible_start = sm.advance_past_planned_downtime(env.now, total_need)
                if feasible_start > env.now:
                    dt_wait = feasible_start - env.now
                    sm.total_planned_downtime += dt_wait
                    events.append(
                        SimulationEvent(
                            event_type="PLANNED_DOWNTIME_WAIT",
                            time=env.now,
                            machine_id=m_id,
                            job_id=job.job_id,
                            duration=dt_wait,
                        )
                    )
                    yield env.timeout(dt_wait)

                actual_start = float(env.now)
                waiting_time = max(0.0, actual_start - actual_arrival)

                # Changeover / Setup
                if setup_dur > 0:
                    events.append(
                        SimulationEvent(
                            event_type="SETUP_START",
                            time=env.now,
                            machine_id=m_id,
                            job_id=job.job_id,
                            product_id=job.product_id,
                            duration=setup_dur,
                            details={"from_product": sm.current_product},
                        )
                    )
                    yield env.timeout(setup_dur)
                    sm.total_setup_time += setup_dur

                # Production
                events.append(
                    SimulationEvent(
                        event_type="PRODUCTION_START",
                        time=env.now,
                        machine_id=m_id,
                        job_id=job.job_id,
                        product_id=job.product_id,
                        duration=proc_dur,
                    )
                )
                yield env.timeout(proc_dur)
                sm.total_processing_time += proc_dur

                # Unplanned machine breakdown during run
                if bd_delay > 0:
                    events.append(
                        SimulationEvent(
                            event_type="BREAKDOWN",
                            time=env.now,
                            machine_id=m_id,
                            job_id=job.job_id,
                            duration=bd_delay,
                        )
                    )
                    yield env.timeout(bd_delay)
                    sm.total_breakdown_time += bd_delay

                actual_completion = float(env.now)
                sm.current_product = job.product_id
                sm.jobs_completed += 1
                events.append(
                    SimulationEvent(
                        event_type="JOB_COMPLETE",
                        time=actual_completion,
                        machine_id=m_id,
                        job_id=job.job_id,
                        product_id=job.product_id,
                    )
                )

                actual_tard = max(0.0, actual_completion - job.due_date)
                outcomes.append(
                    SimulatedJobOutcome(
                        job_id=job.job_id,
                        product_id=job.product_id,
                        machine_id=m_id,
                        planned_start=planned.start_time,
                        planned_completion=planned.completion_time,
                        actual_arrival=actual_arrival,
                        actual_start=actual_start,
                        actual_setup_duration=setup_dur,
                        actual_processing_duration=proc_dur,
                        breakdown_delay=bd_delay,
                        actual_completion=actual_completion,
                        due_date=job.due_date,
                        planned_tardiness=planned.tardiness,
                        actual_tardiness=actual_tard,
                        waiting_time=waiting_time,
                        schedule_deviation=actual_completion - planned.completion_time,
                    )
                )

    for m_id in problem.machines:
        seq = schedule.get_machine_sequence(m_id)
        if seq:
            env.process(run_machine_queue(m_id, seq))

    env.run()

    planned_makespan = schedule.makespan
    sim_makespan = max((o.actual_completion for o in outcomes), default=0.0)
    n_jobs = len(problem.jobs)
    planned_late = sum(1 for sj in schedule.scheduled_jobs if sj.tardiness > 1e-6)
    sim_late = sum(1 for o in outcomes if o.actual_tardiness > 1e-6)
    planned_otd = (n_jobs - planned_late) / n_jobs * 100.0
    sim_otd = (n_jobs - sim_late) / n_jobs * 100.0

    # Machine utilization across simulated makespan
    utils = []
    for m_id, sm in sim_machines.items():
        avail = max(0.0, sim_makespan - sm.machine.available_from - sm.total_breakdown_time - sm.total_planned_downtime)
        busy = sm.total_setup_time + sm.total_processing_time
        utils.append((busy / avail * 100.0) if avail > 1e-9 else 0.0)

    mean_util = sum(utils) / len(utils) if utils else 0.0
    mean_wait = sum(o.waiting_time for o in outcomes) / len(outcomes) if outcomes else 0.0
    mean_dev = sum(o.schedule_deviation for o in outcomes) / len(outcomes) if outcomes else 0.0
    max_dev = max((abs(o.schedule_deviation) for o in outcomes), default=0.0)

    return SimulationResult(
        problem_name=problem.name,
        algorithm=schedule.algorithm,
        seed=run_seed,
        planned_makespan=planned_makespan,
        simulated_makespan=sim_makespan,
        planned_otd_pct=planned_otd,
        simulated_otd_pct=sim_otd,
        planned_total_tardiness=schedule.total_tardiness,
        simulated_total_tardiness=sum(o.actual_tardiness for o in outcomes),
        simulated_utilization_pct=mean_util,
        mean_waiting_time=mean_wait,
        mean_schedule_deviation=mean_dev,
        max_schedule_deviation=max_dev,
        job_outcomes=sorted(outcomes, key=lambda o: o.job_id),
        events=sorted(events, key=lambda e: e.time),
    )
