"""Tests for manufacturing data models, changeover validation, generator, and I/O."""

import pytest

from plantsched.core import (
    ChangeoverMatrix,
    DowntimeWindow,
    Job,
    Machine,
    Product,
    SchedulingProblem,
)
from plantsched.data import (
    InstanceGeneratorConfig,
    generate_instance,
    load_problem_csv,
    load_problem_json,
    preprocess_problem,
    save_problem_csv,
    save_problem_json,
)


def test_generator_reproducibility_and_sizes():
    for size in (10, 25, 50, 100, 250, 500):
        p1 = generate_instance(InstanceGeneratorConfig(num_jobs=size, seed=77))
        p2 = generate_instance(InstanceGeneratorConfig(num_jobs=size, seed=77))
        assert len(p1.jobs) == size
        assert p1.to_dict() == p2.to_dict()


def test_json_and_csv_roundtrip(tmp_path):
    problem = generate_instance(
        InstanceGeneratorConfig(num_jobs=15, num_machines=3, num_products=5, seed=12, include_downtime=True)
    )
    json_file = save_problem_json(problem, tmp_path / "inst.json")
    loaded_json = load_problem_json(json_file)
    assert loaded_json.to_dict() == problem.to_dict()

    csv_dir = save_problem_csv(problem, tmp_path / "inst_csv")
    loaded_csv = load_problem_csv(csv_dir)
    assert len(loaded_csv.jobs) == len(problem.jobs)
    assert len(loaded_csv.machines) == len(problem.machines)
    assert loaded_csv.changeover_matrix.matrix == problem.changeover_matrix.matrix


def test_invalid_changeover_and_eligibility():
    with pytest.raises(ValueError, match="Diagonal"):
        ChangeoverMatrix(product_ids=["A", "B"], matrix={("A", "A"): 5.0, ("A", "B"): 10.0})

    with pytest.raises(ValueError, match="negative"):
        ChangeoverMatrix(product_ids=["A", "B"], matrix={("A", "B"): -1.0})

    products = {"A": Product("A"), "B": Product("B")}
    cm = ChangeoverMatrix(product_ids=["A", "B"], matrix={("A", "B"): 10.0, ("B", "A"): 15.0})
    machines = {"M1": Machine("M1", eligible_products={"A"})}
    jobs = {"J1": Job("J1", product_id="B", quantity=10, processing_time=20.0, due_date=50.0)}

    with pytest.raises(ValueError, match="no eligible machines"):
        SchedulingProblem(name="bad", products=products, machines=machines, jobs=jobs, changeover_matrix=cm)


def test_preprocessing_summary():
    problem = generate_instance(InstanceGeneratorConfig(num_jobs=20, num_machines=3, num_products=4, seed=5))
    _, summary, jobs_df = preprocess_problem(problem)
    assert summary.num_jobs == 20
    assert len(jobs_df) == 20
    assert 0.0 < summary.eligibility_density <= 1.0
