"""Configurable synthetic manufacturing instance generator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from plantsched.core.models import DowntimeWindow, Job, Machine, Product
from plantsched.core.problem import ChangeoverMatrix, SchedulingProblem


@dataclass
class InstanceGeneratorConfig:
    """Configuration for generating reproducible synthetic PlantSched instances."""

    num_jobs: int = 30
    num_machines: int = 3
    num_products: int = 6
    processing_time_dist: Literal["uniform", "normal", "lognormal"] = "uniform"
    processing_time_mean: float = 35.0
    processing_time_std: float = 10.0
    processing_time_range: tuple[int, int] = (15, 60)
    due_date_tightness: Literal["tight", "medium", "loose"] = "medium"
    changeover_complexity: Literal["low", "medium", "high"] = "medium"
    eligibility_prob: float = 0.8
    quantity_range: tuple[int, int] = (50, 300)
    max_arrival_ratio: float = 0.35
    include_downtime: bool = False
    include_initial_state: bool = True
    seed: int = 42
    name: str | None = None


def generate_instance(config: InstanceGeneratorConfig | None = None) -> SchedulingProblem:
    """Generate a validated, reproducible multi-line production scheduling instance."""
    cfg = config or InstanceGeneratorConfig()
    if cfg.num_jobs < 1:
        raise ValueError("num_jobs must be >= 1.")
    if cfg.num_machines < 1:
        raise ValueError("num_machines must be >= 1.")
    if cfg.num_products < 1:
        raise ValueError("num_products must be >= 1.")
    if not (0.0 < cfg.eligibility_prob <= 1.0):
        raise ValueError("eligibility_prob must be in (0, 1].")

    rng = np.random.default_rng(cfg.seed)

    # 1. Products
    product_ids = [f"P{i + 1}" for i in range(cfg.num_products)]
    products = {
        pid: Product(
            product_id=pid,
            name=f"Product {pid}",
            family=f"Fam{(i % max(1, cfg.num_products // 2)) + 1}",
            base_processing_rate=1.0,
        )
        for i, pid in enumerate(product_ids)
    }

    # 2. Directional Changeover Matrix (integer minutes for exact CP-SAT parity)
    setup_bounds = {
        "low": (5, 15),
        "medium": (10, 35),
        "high": (20, 60),
    }[cfg.changeover_complexity]
    matrix: dict[tuple[str, str], float] = {}
    for i, p_from in enumerate(product_ids):
        for j, p_to in enumerate(product_ids):
            if i == j:
                matrix[(p_from, p_to)] = 0.0
            else:
                # Introduce realistic family affinity + directional asymmetry
                same_family = products[p_from].family == products[p_to].family
                low, high = setup_bounds
                if same_family:
                    val = int(rng.integers(max(2, low // 2), max(4, (low + high) // 2)))
                else:
                    val = int(rng.integers(low, high + 1))
                matrix[(p_from, p_to)] = float(val)
    changeover = ChangeoverMatrix(product_ids=product_ids, matrix=matrix)

    # 3. Machines with product eligibility & optional initial state / downtime
    machine_ids = [f"M{m + 1}" for m in range(cfg.num_machines)]
    product_to_machines: dict[str, list[str]] = {pid: [] for pid in product_ids}
    machine_eligible: dict[str, set[str]] = {mid: set() for mid in machine_ids}

    for mid in machine_ids:
        for pid in product_ids:
            if rng.random() <= cfg.eligibility_prob:
                machine_eligible[mid].add(pid)
                product_to_machines[pid].append(mid)

    # Guarantee every product has >= 1 eligible machine and every machine >= 1 product
    for pid in product_ids:
        if not product_to_machines[pid]:
            chosen_m = machine_ids[int(rng.integers(0, len(machine_ids)))]
            machine_eligible[chosen_m].add(pid)
            product_to_machines[pid].append(chosen_m)

    for mid in machine_ids:
        if not machine_eligible[mid]:
            chosen_p = product_ids[int(rng.integers(0, len(product_ids)))]
            machine_eligible[mid].add(chosen_p)

    # Estimate rough workload per machine to place optional downtime realistically
    approx_load = (cfg.num_jobs * cfg.processing_time_mean) / max(1, cfg.num_machines)

    machines: dict[str, Machine] = {}
    for m_idx, mid in enumerate(machine_ids):
        initial_prod = None
        if cfg.include_initial_state:
            elig_list = sorted(machine_eligible[mid])
            initial_prod = elig_list[int(rng.integers(0, len(elig_list)))]

        downtimes: list[DowntimeWindow] = []
        if cfg.include_downtime and approx_load > 60:
            dt_start = float(int(rng.uniform(0.25, 0.55) * approx_load) + m_idx * 5)
            dt_dur = float(int(rng.integers(15, 30)))
            downtimes.append(
                DowntimeWindow(start=dt_start, end=dt_start + dt_dur, reason="preventive_maintenance")
            )

        machines[mid] = Machine(
            machine_id=mid,
            name=f"Line {mid}",
            available_from=0.0,
            eligible_products=machine_eligible[mid],
            capacity=1.0,
            initial_product=initial_prod,
            downtime_windows=downtimes,
        )

    # 4. Jobs / Orders
    tightness_factor = {
        "tight": (0.8, 1.3),
        "medium": (1.1, 1.9),
        "loose": (1.6, 2.8),
    }[cfg.due_date_tightness]

    jobs: dict[str, Job] = {}
    avg_setup = float(np.mean([v for v in matrix.values() if v > 0] or [0.0]))
    est_makespan = max(
        40.0,
        (cfg.num_jobs * (cfg.processing_time_mean + 0.5 * avg_setup)) / max(1, cfg.num_machines),
    )

    for j_idx in range(cfg.num_jobs):
        jid = f"J{j_idx + 1:03d}"
        pid = product_ids[int(rng.integers(0, cfg.num_products))]
        qty = int(rng.integers(cfg.quantity_range[0], cfg.quantity_range[1] + 1))

        if cfg.processing_time_dist == "uniform":
            proc = int(
                rng.integers(cfg.processing_time_range[0], cfg.processing_time_range[1] + 1)
            )
        elif cfg.processing_time_dist == "normal":
            raw = rng.normal(cfg.processing_time_mean, cfg.processing_time_std)
            proc = int(max(5, round(raw)))
        elif cfg.processing_time_dist == "lognormal":
            sigma = float(np.sqrt(np.log(1 + (cfg.processing_time_std / cfg.processing_time_mean) ** 2)))
            mu = float(np.log(cfg.processing_time_mean) - 0.5 * sigma**2)
            raw = rng.lognormal(mu, sigma)
            proc = int(max(5, round(raw)))
        else:
            raise ValueError(f"Unsupported distribution: {cfg.processing_time_dist}")

        # Arrival times staggered over the early fraction of estimated horizon
        if j_idx < max(2, cfg.num_jobs // 4):
            arrival = 0
        else:
            arrival = int(rng.uniform(0.0, cfg.max_arrival_ratio * est_makespan))

        slack_mult = float(rng.uniform(tightness_factor[0], tightness_factor[1]))
        # Scale due date reasonably with arrival + processing + expected queueing
        due = int(round(arrival + proc + slack_mult * (est_makespan * 0.65)))
        priority = float(rng.choice([1.0, 1.5, 2.0, 3.0], p=[0.4, 0.3, 0.2, 0.1]))

        jobs[jid] = Job(
            job_id=jid,
            product_id=pid,
            quantity=qty,
            processing_time=float(proc),
            arrival_time=float(arrival),
            due_date=float(due),
            priority=priority,
            eligible_machines=None,  # determined by machine eligibility
        )

    instance_name = cfg.name or f"plantsched_{cfg.num_jobs}j_{cfg.num_machines}m_{cfg.num_products}p_s{cfg.seed}"
    return SchedulingProblem(
        name=instance_name,
        products=products,
        machines=machines,
        jobs=jobs,
        changeover_matrix=changeover,
        metadata={
            "seed": cfg.seed,
            "num_jobs": cfg.num_jobs,
            "num_machines": cfg.num_machines,
            "num_products": cfg.num_products,
            "due_date_tightness": cfg.due_date_tightness,
            "changeover_complexity": cfg.changeover_complexity,
            "processing_time_dist": cfg.processing_time_dist,
        },
    )
