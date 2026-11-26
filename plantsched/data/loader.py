"""Dataset loading and saving utilities (JSON and CSV formats)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from plantsched.core.models import DowntimeWindow, Job, Machine, Product
from plantsched.core.problem import ChangeoverMatrix, SchedulingProblem


def save_problem_json(problem: SchedulingProblem, filepath: str | Path) -> Path:
    """Save a SchedulingProblem instance to JSON."""
    p = Path(filepath)
    problem.to_json(p)
    return p


def load_problem_json(filepath: str | Path) -> SchedulingProblem:
    """Load and validate a SchedulingProblem instance from JSON."""
    return SchedulingProblem.from_json(filepath)


def save_problem_csv(problem: SchedulingProblem, directory: str | Path) -> Path:
    """Save a SchedulingProblem instance as a structured directory of CSV files."""
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)

    products_df = pd.DataFrame([p.to_dict() for p in problem.products.values()])
    products_df["attributes"] = products_df["attributes"].apply(json.dumps)
    products_df.to_csv(out_dir / "products.csv", index=False)

    machines_rows = []
    for m in problem.machines.values():
        d = m.to_dict()
        d["eligible_products"] = (
            "|".join(d["eligible_products"]) if d["eligible_products"] is not None else ""
        )
        d["downtime_windows"] = json.dumps(d["downtime_windows"])
        machines_rows.append(d)
    pd.DataFrame(machines_rows).to_csv(out_dir / "machines.csv", index=False)

    jobs_rows = []
    for j in problem.jobs.values():
        d = j.to_dict()
        d["eligible_machines"] = (
            "|".join(d["eligible_machines"]) if d["eligible_machines"] is not None else ""
        )
        jobs_rows.append(d)
    pd.DataFrame(jobs_rows).to_csv(out_dir / "jobs.csv", index=False)

    problem.changeover_matrix.to_dataframe().to_csv(out_dir / "changeover_matrix.csv")

    meta = {"name": problem.name, "horizon": problem.horizon, "metadata": problem.metadata}
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out_dir


def load_problem_csv(directory: str | Path) -> SchedulingProblem:
    """Load and validate a SchedulingProblem instance from a CSV directory."""
    in_dir = Path(directory)
    meta_path = in_dir / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    products_df = pd.read_csv(in_dir / "products.csv")
    products: dict[str, Product] = {}
    for _, row in products_df.iterrows():
        attrs = json.loads(row["attributes"]) if pd.notna(row.get("attributes")) else {}
        p = Product(
            product_id=str(row["product_id"]),
            name=str(row.get("name", "")),
            family=str(row.get("family", "general")),
            base_processing_rate=float(row.get("base_processing_rate", 1.0)),
            attributes=attrs,
        )
        products[p.product_id] = p

    machines_df = pd.read_csv(in_dir / "machines.csv")
    machines: dict[str, Machine] = {}
    for _, row in machines_df.iterrows():
        ep_raw = row.get("eligible_products")
        ep = (
            set(str(ep_raw).split("|"))
            if pd.notna(ep_raw) and str(ep_raw).strip() != ""
            else None
        )
        dt_raw = row.get("downtime_windows")
        dts = (
            [DowntimeWindow.from_dict(d) for d in json.loads(dt_raw)]
            if pd.notna(dt_raw) and str(dt_raw).strip() != ""
            else []
        )
        init_p = row.get("initial_product")
        avail_until = row.get("available_until")
        m = Machine(
            machine_id=str(row["machine_id"]),
            name=str(row.get("name", "")),
            available_from=float(row.get("available_from", 0.0)),
            available_until=float(avail_until) if pd.notna(avail_until) else None,
            eligible_products=ep,
            capacity=float(row.get("capacity", 1.0)),
            initial_product=str(init_p) if pd.notna(init_p) and str(init_p) != "" else None,
            downtime_windows=dts,
        )
        machines[m.machine_id] = m

    jobs_df = pd.read_csv(in_dir / "jobs.csv")
    jobs: dict[str, Job] = {}
    for _, row in jobs_df.iterrows():
        em_raw = row.get("eligible_machines")
        em = (
            str(em_raw).split("|")
            if pd.notna(em_raw) and str(em_raw).strip() != ""
            else None
        )
        j = Job(
            job_id=str(row["job_id"]),
            product_id=str(row["product_id"]),
            quantity=int(row["quantity"]),
            processing_time=float(row["processing_time"]),
            arrival_time=float(row.get("arrival_time", 0.0)),
            due_date=float(row["due_date"]),
            priority=float(row.get("priority", 1.0)),
            eligible_machines=em,
        )
        jobs[j.job_id] = j

    cm_df = pd.read_csv(in_dir / "changeover_matrix.csv", index_col=0)
    cm_df.index = cm_df.index.astype(str)
    cm_df.columns = cm_df.columns.astype(str)
    changeover = ChangeoverMatrix.from_dataframe(cm_df)

    return SchedulingProblem(
        name=str(meta.get("name", in_dir.name)),
        products=products,
        machines=machines,
        jobs=jobs,
        changeover_matrix=changeover,
        horizon=meta.get("horizon"),
        metadata=meta.get("metadata", {}),
    )
