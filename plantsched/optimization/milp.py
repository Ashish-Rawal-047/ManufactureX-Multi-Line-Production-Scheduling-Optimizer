"""Mixed-Integer Linear Programming (MILP) formulation using PuLP/CBC."""

from __future__ import annotations

import time

import pulp

from plantsched.core.config import MILPConfig, ObjectiveWeights, SolverStatus
from plantsched.core.problem import SchedulingProblem
from plantsched.core.schedule import Schedule, ScheduledJob
from plantsched.optimization.objectives import compute_optimality_gap


def solve_milp(
    problem: SchedulingProblem,
    config: MILPConfig | None = None,
) -> Schedule:
    """Solve the multi-line sequence-dependent scheduling problem via MILP (PuLP + CBC).

    Mathematical Formulation:
    - Binary assignment: x[j, m] in {0, 1}
    - Immediate-predecessor flow variables per machine m:
        f[j, m]: j is first job on m
        l[j, m]: j is last job on m
        y[i, j, m]: j immediately follows i on m
    - Continuous timing: setup_start[j], setup_dur[j], proc_start[j], comp[j], tard[j], cmax
    - Big-M precedence + subtour elimination:
        setup_start[j] >= comp[i] - M * (1 - y[i, j, m]), with M = problem.compute_horizon()
    - Optional downtime disjunctive constraints (when `config.include_downtime` is True).

    Computational Note:
    This formulation introduces O(N^2 * M) binary sequencing variables and Big-M
    constraints; consequently, LP relaxations are weaker than CP-SAT interval/circuit
    propagation, making MILP suitable primarily for small instances (<= 20-25 jobs).
    """
    t0 = time.perf_counter()
    cfg = config or MILPConfig()
    weights: ObjectiveWeights = cfg.weights

    job_ids = list(problem.jobs.keys())
    machine_ids = list(problem.machines.keys())
    M = float(problem.compute_horizon())

    model = pulp.LpProblem(f"PlantSched_{problem.name}", pulp.LpMinimize)

    eligible_by_job = {j_id: problem.get_eligible_machines(j_id) for j_id in job_ids}
    jobs_by_machine: dict[str, list[str]] = {m_id: [] for m_id in machine_ids}
    for j_id, elig in eligible_by_job.items():
        for m_id in elig:
            jobs_by_machine[m_id].append(j_id)

    # Decision Variables
    x: dict[tuple[str, str], pulp.LpVariable] = {}
    f: dict[tuple[str, str], pulp.LpVariable] = {}
    l: dict[tuple[str, str], pulp.LpVariable] = {}
    y: dict[tuple[str, str, str], pulp.LpVariable] = {}

    for j_id in job_ids:
        for m_id in eligible_by_job[j_id]:
            x[(j_id, m_id)] = pulp.LpVariable(f"x_{j_id}_{m_id}", cat="Binary")
            f[(j_id, m_id)] = pulp.LpVariable(f"f_{j_id}_{m_id}", cat="Binary")
            l[(j_id, m_id)] = pulp.LpVariable(f"l_{j_id}_{m_id}", cat="Binary")

    for m_id in machine_ids:
        m_jobs = jobs_by_machine[m_id]
        for i_id in m_jobs:
            for j_id in m_jobs:
                if i_id != j_id:
                    y[(i_id, j_id, m_id)] = pulp.LpVariable(
                        f"y_{i_id}_{j_id}_{m_id}", cat="Binary"
                    )

    setup_start = {
        j_id: pulp.LpVariable(
            f"s_start_{j_id}", lowBound=problem.jobs[j_id].arrival_time, upBound=M, cat="Continuous"
        )
        for j_id in job_ids
    }
    setup_dur = {
        j_id: pulp.LpVariable(f"s_dur_{j_id}", lowBound=0.0, cat="Continuous")
        for j_id in job_ids
    }
    comp = {
        j_id: pulp.LpVariable(f"comp_{j_id}", lowBound=0.0, upBound=M, cat="Continuous")
        for j_id in job_ids
    }
    tard = {
        j_id: pulp.LpVariable(f"tard_{j_id}", lowBound=0.0, cat="Continuous")
        for j_id in job_ids
    }
    cmax = pulp.LpVariable("cmax", lowBound=0.0, upBound=M, cat="Continuous")

    # 1. Exactly one eligible machine per job + timing definitions
    for j_id in job_ids:
        job = problem.jobs[j_id]
        elig = eligible_by_job[j_id]
        model += pulp.lpSum(x[(j_id, m_id)] for m_id in elig) == 1, f"assign_{j_id}"

        proc_expr = pulp.lpSum(
            problem.get_processing_time(j_id, m_id) * x[(j_id, m_id)] for m_id in elig
        )
        model += (
            comp[j_id] == setup_start[j_id] + setup_dur[j_id] + proc_expr,
            f"comp_def_{j_id}",
        )
        model += tard[j_id] >= comp[j_id] - job.due_date, f"tard_def_{j_id}"
        model += cmax >= comp[j_id], f"cmax_def_{j_id}"

        # Exact sequence-dependent setup expression
        setup_terms = []
        for m_id in elig:
            machine = problem.machines[m_id]
            init_s = problem.get_setup_time(machine.initial_product, job.product_id)
            setup_terms.append(init_s * f[(j_id, m_id)])
            for i_id in jobs_by_machine[m_id]:
                if i_id != j_id:
                    trans_s = problem.get_setup_time(
                        problem.jobs[i_id].product_id, job.product_id
                    )
                    setup_terms.append(trans_s * y[(i_id, j_id, m_id)])
        model += setup_dur[j_id] == pulp.lpSum(setup_terms), f"setup_def_{j_id}"

        # Machine availability
        for m_id in elig:
            machine = problem.machines[m_id]
            model += (
                setup_start[j_id] >= machine.available_from * x[(j_id, m_id)],
                f"avail_from_{j_id}_{m_id}",
            )
            if machine.available_until is not None:
                model += (
                    comp[j_id] <= machine.available_until + M * (1 - x[(j_id, m_id)]),
                    f"avail_until_{j_id}_{m_id}",
                )

    # 2. Machine flow conservation, precedence, and non-overlap
    for m_id in machine_ids:
        m_jobs = jobs_by_machine[m_id]
        if not m_jobs:
            continue
        model += pulp.lpSum(f[(j_id, m_id)] for j_id in m_jobs) <= 1, f"one_first_{m_id}"
        model += pulp.lpSum(l[(j_id, m_id)] for j_id in m_jobs) <= 1, f"one_last_{m_id}"
        model += (
            pulp.lpSum(f[(j_id, m_id)] for j_id in m_jobs)
            == pulp.lpSum(l[(j_id, m_id)] for j_id in m_jobs),
            f"first_eq_last_{m_id}",
        )

        for j_id in m_jobs:
            model += (
                f[(j_id, m_id)]
                + pulp.lpSum(y[(i_id, j_id, m_id)] for i_id in m_jobs if i_id != j_id)
                == x[(j_id, m_id)],
                f"inflow_{m_id}_{j_id}",
            )
            model += (
                l[(j_id, m_id)]
                + pulp.lpSum(y[(j_id, k_id, m_id)] for k_id in m_jobs if k_id != j_id)
                == x[(j_id, m_id)],
                f"outflow_{m_id}_{j_id}",
            )

        for i_id in m_jobs:
            for j_id in m_jobs:
                if i_id != j_id:
                    model += (
                        setup_start[j_id] >= comp[i_id] - M * (1 - y[(i_id, j_id, m_id)]),
                        f"prec_{m_id}_{i_id}_{j_id}",
                    )

        # Optional downtime disjunctive constraints
        if cfg.include_downtime:
            machine = problem.machines[m_id]
            for dt_idx, dt in enumerate(machine.downtime_windows):
                for j_id in m_jobs:
                    z = pulp.LpVariable(f"dt_{m_id}_{dt_idx}_{j_id}", cat="Binary")
                    model += (
                        comp[j_id] <= dt.start + M * (1 - z) + M * (1 - x[(j_id, m_id)]),
                        f"dt_before_{m_id}_{dt_idx}_{j_id}",
                    )
                    model += (
                        setup_start[j_id] >= dt.end - M * z - M * (1 - x[(j_id, m_id)]),
                        f"dt_after_{m_id}_{dt_idx}_{j_id}",
                    )

    # 3. Objective Function
    weighted_tard_expr = pulp.lpSum(
        problem.jobs[j_id].priority * tard[j_id] for j_id in job_ids
    )
    total_setup_expr = pulp.lpSum(setup_dur[j_id] for j_id in job_ids)
    model += (
        weights.alpha * cmax
        + weights.beta * weighted_tard_expr
        + weights.gamma * total_setup_expr,
        "TotalWeightedObjective",
    )

    solver = pulp.PULP_CBC_CMD(msg=cfg.msg, timeLimit=cfg.max_time_seconds)
    model.solve(solver)
    runtime = time.perf_counter() - t0

    pulp_status = pulp.LpStatus[model.status]
    sol_status = model.sol_status
    sol_status_name = pulp.LpSolution.get(sol_status, str(sol_status))

    # NOTE: PuLP sets model.status == LpStatusOptimal even when CBC stops on time limit
    # with an integer-feasible incumbent; model.sol_status distinguishes Optimal (1)
    # from IntegerFeasible (2) and NoSolutionFound (0).
    if sol_status == pulp.LpSolutionOptimal and pulp_status == "Optimal":
        status = SolverStatus.OPTIMAL
    elif sol_status == pulp.LpSolutionIntegerFeasible:
        status = SolverStatus.FEASIBLE
    elif sol_status == pulp.LpSolutionInfeasible or pulp_status == "Infeasible":
        status = SolverStatus.INFEASIBLE
    else:
        status = SolverStatus.UNKNOWN

    # Verify binary integrality when an incumbent is claimed
    if status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
        binary_vars = list(x.values()) + list(f.values()) + list(l.values()) + list(y.values())
        if any(
            pulp.value(v) is None or abs(float(pulp.value(v)) - round(float(pulp.value(v)))) > 1e-4
            for v in binary_vars
        ):
            status = SolverStatus.UNKNOWN

    if status not in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
        return Schedule(
            problem_name=problem.name,
            algorithm="MILP",
            scheduled_jobs=[],
            solver_status=status,
            runtime_seconds=runtime,
            metadata={
                "pulp_status": pulp_status,
                "pulp_sol_status": sol_status_name,
                "big_m": M,
            },
        )

    assigned_machine: dict[str, str] = {}
    for j_id in job_ids:
        for m_id in eligible_by_job[j_id]:
            if (pulp.value(x[(j_id, m_id)]) or 0.0) > 0.5:
                assigned_machine[j_id] = m_id
                break

    pred_product_by_job: dict[str, str | None] = {}
    for m_id in machine_ids:
        m_ops = sorted(
            (j_id for j_id in jobs_by_machine[m_id] if assigned_machine.get(j_id) == m_id),
            key=lambda jid: float(pulp.value(setup_start[jid]) or 0.0),
        )
        prev_p = problem.machines[m_id].initial_product
        for j_id in m_ops:
            pred_product_by_job[j_id] = prev_p
            prev_p = problem.jobs[j_id].product_id

    scheduled_jobs: list[ScheduledJob] = []
    for j_id in job_ids:
        job = problem.jobs[j_id]
        m_id = assigned_machine[j_id]
        s_start_v = float(pulp.value(setup_start[j_id]) or 0.0)
        s_dur_v = float(pulp.value(setup_dur[j_id]) or 0.0)
        p_start_v = s_start_v + s_dur_v
        p_dur_v = problem.get_processing_time(j_id, m_id)
        comp_v = p_start_v + p_dur_v
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
        algorithm="MILP",
        scheduled_jobs=scheduled_jobs,
        solver_status=status,
        runtime_seconds=runtime,
    )
    obj_val = schedule.compute_objective(weights)
    schedule.objective_value = obj_val
    schedule.best_bound = obj_val if status == SolverStatus.OPTIMAL else None
    schedule.optimality_gap = (
        0.0 if status == SolverStatus.OPTIMAL else compute_optimality_gap(obj_val, schedule.best_bound)
    )
    schedule.metadata = {
        "pulp_status": pulp_status,
        "pulp_sol_status": sol_status_name,
        "big_m": M,
        "num_variables": model.numVariables(),
        "num_constraints": model.numConstraints(),
        "include_downtime": cfg.include_downtime,
    }
    return schedule
