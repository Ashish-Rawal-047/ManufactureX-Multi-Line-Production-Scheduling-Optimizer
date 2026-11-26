"""Exact constraint programming optimization model using Google OR-Tools CP-SAT."""

from __future__ import annotations

import time
from typing import Any

from ortools.sat.python import cp_model

from plantsched.baselines.fcfs import solve_fcfs
from plantsched.core.config import CPSATConfig, ObjectiveWeights, SolverStatus
from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule, ScheduledJob
from plantsched.optimization.constraints import (
    compute_scaled_horizon,
    compute_time_scale,
    compute_weight_scale,
    scale_int,
)
from plantsched.optimization.objectives import compute_optimality_gap


def _map_cp_status(status: int) -> SolverStatus:
    if status == cp_model.OPTIMAL:
        return SolverStatus.OPTIMAL
    if status == cp_model.FEASIBLE:
        return SolverStatus.FEASIBLE
    if status == cp_model.INFEASIBLE:
        return SolverStatus.INFEASIBLE
    if status == cp_model.MODEL_INVALID:
        return SolverStatus.MODEL_INVALID
    return SolverStatus.UNKNOWN


def solve_cp_sat(
    problem: SchedulingProblem,
    config: CPSATConfig | None = None,
) -> Schedule:
    """Solve the multi-line sequence-dependent scheduling problem with OR-Tools CP-SAT.

    Model features:
    - Exact machine assignment via `AddExactlyOne` over eligible machines
    - Immediate-predecessor sequence-dependent changeovers via per-machine `AddCircuit`
    - Initial machine setup state (`machine.initial_product`) on first job arc `(0 -> j)`
    - Non-overlapping machine execution + planned downtime intervals via `AddNoOverlap`
    - Configurable multi-objective: alpha * Makespan + beta * WeightedTardiness + gamma * TotalChangeover
    """
    t0 = time.perf_counter()
    cfg = config or CPSATConfig()
    weights: ObjectiveWeights = cfg.weights

    time_scale = compute_time_scale(problem)
    weight_scale = compute_weight_scale(problem, weights)
    horizon = compute_scaled_horizon(problem, time_scale)

    job_ids = list(problem.jobs.keys())
    machine_ids = list(problem.machines.keys())
    num_jobs = len(job_ids)
    max_setup = scale_int(problem.changeover_matrix.max_setup(), time_scale)

    model = cp_model.CpModel()

    # Job-level decision variables
    x: dict[tuple[int, str], cp_model.IntVar] = {}
    setup_start: list[cp_model.IntVar] = []
    setup_dur: list[cp_model.IntVar] = []
    proc_start: list[cp_model.IntVar] = []
    proc_dur: list[cp_model.IntVar] = []
    comp: list[cp_model.IntVar] = []
    tardiness: list[cp_model.IntVar] = []

    eligible_by_job: list[list[str]] = []
    jobs_by_machine: dict[str, list[int]] = {m_id: [] for m_id in machine_ids}
    circuit_vars_by_machine: dict[
        str,
        tuple[
            cp_model.IntVar,
            dict[int, cp_model.IntVar],
            dict[int, cp_model.IntVar],
            dict[tuple[int, int], cp_model.IntVar],
            dict[int, cp_model.IntVar],
        ],
    ] = {}

    for j_idx, j_id in enumerate(job_ids):
        job = problem.jobs[j_id]
        elig = problem.get_eligible_machines(j_id)
        eligible_by_job.append(elig)

        arr = scale_int(job.arrival_time, time_scale)
        due = scale_int(job.due_date, time_scale)
        proc_options = [
            scale_int(problem.get_processing_time(j_id, m_id), time_scale) for m_id in elig
        ]
        min_p, max_p = min(proc_options), max(proc_options)

        s_start = model.NewIntVar(arr, horizon, f"s_start_{j_idx}")
        s_dur = model.NewIntVar(0, max_setup, f"s_dur_{j_idx}")
        p_start = model.NewIntVar(arr, horizon, f"p_start_{j_idx}")
        p_dur = model.NewIntVar(min_p, max_p, f"p_dur_{j_idx}")
        c_var = model.NewIntVar(arr + min_p, horizon, f"comp_{j_idx}")
        tard = model.NewIntVar(0, horizon, f"tard_{j_idx}")

        model.Add(p_start == s_start + s_dur)
        model.Add(c_var == p_start + p_dur)
        model.Add(tard >= c_var - due)

        setup_start.append(s_start)
        setup_dur.append(s_dur)
        proc_start.append(p_start)
        proc_dur.append(p_dur)
        comp.append(c_var)
        tardiness.append(tard)

        assign_vars: list[cp_model.IntVar] = []
        proc_terms = []
        for m_id in elig:
            var = model.NewBoolVar(f"x_{j_idx}_{m_id}")
            x[(j_idx, m_id)] = var
            assign_vars.append(var)
            jobs_by_machine[m_id].append(j_idx)

            p_jm = scale_int(problem.get_processing_time(j_id, m_id), time_scale)
            proc_terms.append(p_jm * var)

            machine = problem.machines[m_id]
            avail_from = scale_int(machine.available_from, time_scale)
            model.Add(s_start >= avail_from).OnlyEnforceIf(var)
            if machine.available_until is not None:
                avail_until = scale_int(machine.available_until, time_scale)
                model.Add(c_var <= avail_until).OnlyEnforceIf(var)

        model.AddExactlyOne(assign_vars)
        model.Add(p_dur == sum(proc_terms))

    # Machine-level NoOverlap (with downtime) and AddCircuit (sequence-dependent setups)
    for m_id in machine_ids:
        machine = problem.machines[m_id]
        m_jobs = jobs_by_machine[m_id]
        if not m_jobs:
            continue

        intervals: list[cp_model.IntervalVar] = []
        span_vars: dict[int, cp_model.IntVar] = {}
        for j_idx in m_jobs:
            j_id = job_ids[j_idx]
            p_jm = scale_int(problem.get_processing_time(j_id, m_id), time_scale)
            span_dur = model.NewIntVar(p_jm, p_jm + max_setup, f"span_{j_idx}_{m_id}")
            span_vars[j_idx] = span_dur
            model.Add(span_dur == setup_dur[j_idx] + p_jm).OnlyEnforceIf(x[(j_idx, m_id)])
            opt_iv = model.NewOptionalIntervalVar(
                setup_start[j_idx],
                span_dur,
                comp[j_idx],
                x[(j_idx, m_id)],
                f"iv_{j_idx}_{m_id}",
            )
            intervals.append(opt_iv)

        for dt_idx, dt in enumerate(machine.downtime_windows):
            dt_s = scale_int(dt.start, time_scale)
            dt_d = scale_int(dt.duration, time_scale)
            if dt_d > 0:
                intervals.append(
                    model.NewFixedSizeIntervalVar(dt_s, dt_d, f"dt_{m_id}_{dt_idx}")
                )

        model.AddNoOverlap(intervals)

        # Circuit formulation: node 0 is dummy start/end, nodes 1..K correspond to m_jobs[k-1]
        arcs: list[tuple[int, int, Any]] = []
        idle_m = model.NewBoolVar(f"idle_{m_id}")
        # idle_m == 1 iff no job is assigned to machine m
        model.Add(sum(x[(j_idx, m_id)] for j_idx in m_jobs) == 0).OnlyEnforceIf(idle_m)
        model.Add(sum(x[(j_idx, m_id)] for j_idx in m_jobs) >= 1).OnlyEnforceIf(idle_m.Not())
        arcs.append((0, 0, idle_m))

        first_arcs: dict[int, cp_model.IntVar] = {}
        last_arcs: dict[int, cp_model.IntVar] = {}
        job_arcs: dict[tuple[int, int], cp_model.IntVar] = {}

        for k_idx, j_idx in enumerate(m_jobs, start=1):
            j_id = job_ids[j_idx]
            j_prod = problem.jobs[j_id].product_id
            assign_jm = x[(j_idx, m_id)]

            # Unassigned self-loop (automatically forces assign_jm == 1 if any non-self arc is active)
            arcs.append((k_idx, k_idx, assign_jm.Not()))

            # First job on machine m: 0 -> k_idx
            first_arc = model.NewBoolVar(f"first_{m_id}_{j_idx}")
            first_arcs[j_idx] = first_arc
            init_setup = scale_int(
                problem.get_setup_time(machine.initial_product, j_prod), time_scale
            )
            model.Add(setup_dur[j_idx] == init_setup).OnlyEnforceIf(first_arc)
            arcs.append((0, k_idx, first_arc))

            # Last job on machine m: k_idx -> 0
            last_arc = model.NewBoolVar(f"last_{m_id}_{j_idx}")
            last_arcs[j_idx] = last_arc
            arcs.append((k_idx, 0, last_arc))

        # Job-to-job immediate successor transitions
        for k_i, i_idx in enumerate(m_jobs, start=1):
            i_prod = problem.jobs[job_ids[i_idx]].product_id
            for k_j, j_idx in enumerate(m_jobs, start=1):
                if i_idx == j_idx:
                    continue
                j_prod = problem.jobs[job_ids[j_idx]].product_id
                arc_ij = model.NewBoolVar(f"arc_{m_id}_{i_idx}_{j_idx}")
                job_arcs[(i_idx, j_idx)] = arc_ij
                model.Add(comp[i_idx] <= setup_start[j_idx]).OnlyEnforceIf(arc_ij)
                trans_setup = scale_int(
                    problem.get_setup_time(i_prod, j_prod), time_scale
                )
                model.Add(setup_dur[j_idx] == trans_setup).OnlyEnforceIf(arc_ij)
                arcs.append((k_i, k_j, arc_ij))

        model.AddCircuit(arcs)
        circuit_vars_by_machine[m_id] = (idle_m, first_arcs, last_arcs, job_arcs, span_vars)

    # Objective terms
    cmax = model.NewIntVar(0, horizon, "cmax")
    model.AddMaxEquality(cmax, comp)
    total_changeover = sum(setup_dur)

    alpha_i = scale_int(weights.alpha, weight_scale)
    gamma_i = scale_int(weights.gamma, weight_scale)
    tard_terms = []
    for j_idx, j_id in enumerate(job_ids):
        coef = scale_int(weights.beta * problem.jobs[j_id].priority, weight_scale)
        if coef > 0:
            tard_terms.append(coef * tardiness[j_idx])

    obj_expr = alpha_i * cmax + gamma_i * total_changeover + sum(tard_terms)
    model.Minimize(obj_expr)

    # Warm-start hint from FCFS if feasible (speeds up search without restricting optimality)
    fcfs_sched = solve_fcfs(problem, weights=weights)
    if fcfs_sched.has_solution:
        job_to_idx = {j_id: idx for idx, j_id in enumerate(job_ids)}
        fcfs_by_job = {sj.job_id: sj for sj in fcfs_sched.scheduled_jobs}
        for j_idx, j_id in enumerate(job_ids):
            sj = fcfs_by_job[j_id]
            for m_id in eligible_by_job[j_idx]:
                model.AddHint(x[(j_idx, m_id)], 1 if m_id == sj.machine_id else 0)
            model.AddHint(setup_start[j_idx], scale_int(sj.setup_start_time, time_scale))
            model.AddHint(setup_dur[j_idx], scale_int(sj.setup_duration, time_scale))
            model.AddHint(proc_start[j_idx], scale_int(sj.processing_start_time, time_scale))
            model.AddHint(proc_dur[j_idx], scale_int(sj.processing_duration, time_scale))
            model.AddHint(comp[j_idx], scale_int(sj.completion_time, time_scale))
            model.AddHint(tardiness[j_idx], scale_int(sj.tardiness, time_scale))
        model.AddHint(cmax, scale_int(fcfs_sched.makespan, time_scale))

        for m_id, (idle_m, first_arcs, last_arcs, job_arcs, span_vars) in circuit_vars_by_machine.items():
            for j_idx, s_var in span_vars.items():
                sj = fcfs_by_job[job_ids[j_idx]]
                if sj.machine_id == m_id:
                    model.AddHint(s_var, scale_int(sj.setup_duration + sj.processing_duration, time_scale))
                else:
                    p_jm = scale_int(problem.get_processing_time(job_ids[j_idx], m_id), time_scale)
                    model.AddHint(s_var, p_jm)
            seq = fcfs_sched.get_machine_sequence(m_id)
            if not seq:
                model.AddHint(idle_m, 1)
                continue
            model.AddHint(idle_m, 0)
            seq_idx = [job_to_idx[sj.job_id] for sj in seq]
            for j_idx, var in first_arcs.items():
                model.AddHint(var, 1 if j_idx == seq_idx[0] else 0)
            for j_idx, var in last_arcs.items():
                model.AddHint(var, 1 if j_idx == seq_idx[-1] else 0)
            active_pairs = set(zip(seq_idx[:-1], seq_idx[1:]))
            for pair, var in job_arcs.items():
                model.AddHint(var, 1 if pair in active_pairs else 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(cfg.max_time_seconds)
    solver.parameters.num_search_workers = int(cfg.num_workers)
    solver.parameters.random_seed = int(cfg.random_seed)
    solver.parameters.log_search_progress = bool(cfg.log_search_progress)

    raw_status = solver.Solve(model)
    status = _map_cp_status(raw_status)
    runtime = time.perf_counter() - t0

    if status not in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
        return Schedule(
            problem_name=problem.name,
            algorithm="CP-SAT",
            scheduled_jobs=[],
            solver_status=status,
            runtime_seconds=runtime,
            metadata={"cp_sat_status": solver.StatusName(raw_status)},
        )

    # Extract Schedule
    inv_time = 1.0 / time_scale
    inv_obj = 1.0 / (time_scale * weight_scale)

    assigned_machine: dict[int, str] = {}
    for j_idx in range(num_jobs):
        for m_id in eligible_by_job[j_idx]:
            if solver.Value(x[(j_idx, m_id)]) == 1:
                assigned_machine[j_idx] = m_id
                break

    # Group by machine to identify predecessor product
    raw_ops: list[tuple[int, str, float]] = []
    for j_idx in range(num_jobs):
        m_id = assigned_machine[j_idx]
        s_t = solver.Value(setup_start[j_idx]) * inv_time
        raw_ops.append((j_idx, m_id, s_t))

    pred_product_by_job: dict[str, str | None] = {}
    for m_id in machine_ids:
        m_ops = sorted((op for op in raw_ops if op[1] == m_id), key=lambda o: o[2])
        prev_p = problem.machines[m_id].initial_product
        for j_idx, _, _ in m_ops:
            j_id = job_ids[j_idx]
            pred_product_by_job[j_id] = prev_p
            prev_p = problem.jobs[j_id].product_id

    scheduled_jobs: list[ScheduledJob] = []
    for j_idx, j_id in enumerate(job_ids):
        job = problem.jobs[j_id]
        m_id = assigned_machine[j_idx]
        s_start_v = solver.Value(setup_start[j_idx]) * inv_time
        s_dur_v = solver.Value(setup_dur[j_idx]) * inv_time
        p_start_v = solver.Value(proc_start[j_idx]) * inv_time
        p_dur_v = solver.Value(proc_dur[j_idx]) * inv_time
        comp_v = solver.Value(comp[j_idx]) * inv_time
        tard_v = max(0.0, comp_v - job.due_date)

        scheduled_jobs.append(
            ScheduledJob(
                job_id=j_id,
                product_id=job.product_id,
                machine_id=m_id,
                start_time=s_start_v,
                setup_start_time=s_start_v,
                setup_duration=s_dur_v,
                processing_start_time=p_start_v,
                processing_duration=p_dur_v,
                completion_time=comp_v,
                due_date=job.due_date,
                tardiness=tard_v,
                priority=job.priority,
                predecessor_product=pred_product_by_job[j_id],
            )
        )

    schedule = Schedule(
        problem_name=problem.name,
        algorithm="CP-SAT",
        scheduled_jobs=scheduled_jobs,
        solver_status=status,
        runtime_seconds=runtime,
    )
    obj_val = schedule.compute_objective(weights)
    raw_bound = solver.BestObjectiveBound() * inv_obj
    # Ensure bound doesn't exceed objective due to floating representation
    best_bound = min(raw_bound, obj_val) if status == SolverStatus.FEASIBLE else obj_val
    gap = 0.0 if status == SolverStatus.OPTIMAL else compute_optimality_gap(obj_val, best_bound)

    schedule.objective_value = obj_val
    schedule.best_bound = best_bound
    schedule.optimality_gap = gap
    schedule.metadata = {
        "cp_sat_status": solver.StatusName(raw_status),
        "num_branches": solver.NumBranches(),
        "num_conflicts": solver.NumConflicts(),
        "time_scale": time_scale,
    }
    return schedule
