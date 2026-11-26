# Mathematical Formulation

## Sets & Parameters

- $J$: Set of production jobs/orders ($N = |J|$).
- $M$: Set of production lines/machines.
- $P$: Set of products.
- $M_j \subseteq M$: Eligible machines for job $j$ (intersection of `job.eligible_machines` and `machine.eligible_products`).
- $J_m \subseteq J$: Eligible jobs for machine $m$.
- $p_{jm}$: Effective processing duration of job $j$ on machine $m$ (`job.processing_time / machine.capacity`).
- $r_j$: Arrival (release) time of job $j$.
- $d_j$: Customer due date of job $j$.
- $w_j$: Priority weight of job $j$.
- $s_{pq}$: Directional changeover/setup time from product $p$ to product $q$, with $s_{pp} = 0$ and $s_{pq} \neq s_{qp}$ in general.
- $p^0_m$: Initial setup product state of machine $m$ (`None` implies zero initial setup).
- $A_m, U_m$: Machine availability start (`available_from`) and optional horizon end (`available_until`).
- $W_m = \{[\underline{\delta}_{mk}, \overline{\delta}_{mk})\}$: Planned downtime intervals on machine $m$.

## Decision Variables

- $x_{jm} \in \{0, 1\}$: $1$ if job $j$ is assigned to machine $m \in M_j$.
- $f_{jm} \in \{0, 1\}$: $1$ if job $j$ is the first job on machine $m$.
- $l_{jm} \in \{0, 1\}$: $1$ if job $j$ is the last job on machine $m$.
- $y_{ijm} \in \{0, 1\}$: $1$ if job $j$ immediately succeeds job $i$ on machine $m$ ($i \neq j$).
- $S^{\text{setup}}_j \ge r_j$: Start time of setup (and total machine occupation) for job $j$.
- $\Delta^{\text{setup}}_j \ge 0$: Realized setup duration of job $j$.
- $S^{\text{proc}}_j = S^{\text{setup}}_j + \Delta^{\text{setup}}_j$: Processing start time of job $j$.
- $C_j = S^{\text{proc}}_j + \sum_{m \in M_j} p_{jm} x_{jm}$: Completion time of job $j$.
- $T_j = \max(0, C_j - d_j)$: Tardiness of job $j$.
- $C_{\max} = \max_{j \in J} C_j$: Makespan.

## Objective Function

$$\min \; \alpha \, C_{\max} + \beta \sum_{j \in J} w_j T_j + \gamma \sum_{j \in J} \Delta^{\text{setup}}_j$$

where $\alpha, \beta, \gamma \ge 0$ are configurable via `ObjectiveWeights`.

## Core Constraints

1. **Unique Eligible Machine Assignment:**
   $$\sum_{m \in M_j} x_{jm} = 1 \quad \forall j \in J$$

2. **Immediate-Predecessor Flow Conservation (per machine $m$):**
   $$\sum_{j \in J_m} f_{jm} = \sum_{j \in J_m} l_{jm} \le 1$$
   $$f_{jm} + \sum_{i \in J_m \setminus \{j\}} y_{ijm} = x_{jm}, \qquad l_{jm} + \sum_{k \in J_m \setminus \{j\}} y_{jkm} = x_{jm} \quad \forall j \in J_m$$

3. **Exact Sequence-Dependent Changeover Time:**
   $$\Delta^{\text{setup}}_j = \sum_{m \in M_j} \left( s_{p^0_m, p(j)} f_{jm} + \sum_{i \in J_m \setminus \{j\}} s_{p(i), p(j)} y_{ijm} \right) \quad \forall j \in J$$

4. **Non-Overlap & Subtour Elimination:**
   - In **CP-SAT**: enforced via `AddCircuit` per machine (single Hamiltonian path over assigned jobs plus dummy node `0`) combined with `AddNoOverlap` over `[setup_start, completion]` intervals and fixed downtime intervals.
   - In **MILP**: enforced via Big-$M$ precedence $S^{\text{setup}}_j \ge C_i - M(1 - y_{ijm})$ where $M$ is `problem.compute_horizon()`. Because $p_{jm} > 0$, time strictly increases along any arc $y_{ijm}=1$, which simultaneously eliminates subtours.

5. **Machine Availability & Downtime Avoidance:**
   - $S^{\text{setup}}_j \ge \max(r_j, A_m)$ when $x_{jm}=1$, and $C_j \le U_m$ if $U_m$ is finite.
   - Job intervals $[S^{\text{setup}}_j, C_j)$ cannot overlap any downtime window $[\underline{\delta}_{mk}, \overline{\delta}_{mk})$.
