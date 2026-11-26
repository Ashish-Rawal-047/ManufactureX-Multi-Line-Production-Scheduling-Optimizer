"""Tests for SimPy discrete-event simulation, Monte Carlo, and full end-to-end integration."""

from plantsched.core import CPSATConfig, GAConfig, ObjectiveWeights, SAConfig, SimulationConfig
from plantsched.data import InstanceGeneratorConfig, generate_instance
from plantsched.evaluation import compare_algorithms
from plantsched.simulation import run_monte_carlo, simulate_schedule
from plantsched.visualization import plot_gantt_matplotlib, plot_gantt_plotly


def test_simulation_reproducibility_and_deterministic_parity():
    problem = generate_instance(InstanceGeneratorConfig(num_jobs=12, num_machines=3, num_products=4, seed=42))
    comp = compare_algorithms(
        problem,
        algorithms=("FCFS", "CP-SAT"),
        cp_sat_config=CPSATConfig(max_time_seconds=5.0),
    )
    cp_sched = comp.schedules["CP-SAT"]

    # Zero stochasticity -> simulated makespan must match planned makespan
    det_cfg = SimulationConfig(
        processing_time_cv=0.0,
        enable_downtime=False,
        arrival_delay_prob=0.0,
        random_seed=42,
    )
    sim_det = simulate_schedule(problem, cp_sched, config=det_cfg)
    assert abs(sim_det.simulated_makespan - sim_det.planned_makespan) < 1e-6

    # Stochastic simulation with fixed seed is reproducible
    stoch_cfg = SimulationConfig(
        processing_time_cv=0.15,
        enable_downtime=True,
        arrival_delay_prob=0.2,
        num_replications=10,
        random_seed=123,
    )
    s1 = simulate_schedule(problem, cp_sched, config=stoch_cfg, seed=123)
    s2 = simulate_schedule(problem, cp_sched, config=stoch_cfg, seed=123)
    assert s1.simulated_makespan == s2.simulated_makespan
    assert len(s1.events) >= len(problem.jobs) * 2

    mc = run_monte_carlo(problem, cp_sched, config=stoch_cfg)
    assert mc.num_replications == 10
    assert mc.worst_case_makespan >= mc.avg_makespan >= mc.min_makespan


def test_full_end_to_end_workflow(tmp_path):
    problem = generate_instance(
        InstanceGeneratorConfig(num_jobs=10, num_machines=3, num_products=4, seed=42, include_downtime=True)
    )
    weights = ObjectiveWeights()
    comp = compare_algorithms(
        problem,
        algorithms=("FCFS", "CP-SAT", "MILP", "GA", "SA"),
        weights=weights,
        cp_sat_config=CPSATConfig(max_time_seconds=10.0, weights=weights),
        ga_config=GAConfig(population_size=25, generations=25, random_seed=42, weights=weights),
        sa_config=SAConfig(max_iterations=300, random_seed=42, weights=weights),
    )

    assert len(comp.summary_table) == 5
    assert comp.summary_table["Valid"].all()

    cp_sched = comp.schedules["CP-SAT"]
    png_path = tmp_path / "gantt.png"
    html_path = tmp_path / "gantt.html"
    plot_gantt_matplotlib(problem, cp_sched, output_path=png_path)
    plot_gantt_plotly(problem, cp_sched, output_path=html_path)
    assert png_path.exists() and png_path.stat().st_size > 0
    assert html_path.exists() and html_path.stat().st_size > 0

    mc = run_monte_carlo(problem, cp_sched, SimulationConfig(num_replications=5, random_seed=42))
    assert len(mc.replications_df) == 5
