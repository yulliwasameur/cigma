"""Optimal migration plans under constraints (CP-SAT), with a checkable certificate.

Problem (one step = one change window):
- units u (services, devices, certificate authorities) with a risk weight w_u;
- capacity: at most C units migrated per step (team budget);
- interoperability: for a dependency v -> u (v calls u), the client v must be
  hybrid-capable no later than the server u switches, i.e. s_v <= s_u, unless u
  is already hybrid-capable (it then accepts both old and new clients);
- trust anchors first: an issuing CA is migrated no later than the certificates it issues;
- maintenance windows: unit u may only move in its allowed steps.
Objective: minimize sum_u w_u * (s_u + 1), the area under the remaining risk curve.

The greedy baseline is list scheduling (highest weight first among units whose
predecessors are done). The solver returns a plan, its objective, the best proven
lower bound and the optimality gap; ``check_plan`` re-verifies every constraint
independently of the solver (the certificate).

References for the approach: SMT/CP planning of reconfigurations (Robillard &
Coullon, FASE 2022; SafeMigration, FMANO@SIGCOMM 2025); dependency-aware PQC
ordering (Sharma et al., ICAISET 2026), here made optimal and certified.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(slots=True)
class PlanningProblem:
    units: list[str]
    weight: dict[str, float]
    precedences: list[tuple[str, str]]          # (a, b): a no later than b
    capacity: int
    horizon: int
    hybrid_capable: set[str] = field(default_factory=set)
    windows: dict[str, list[int]] = field(default_factory=dict)

    def effective_precedences(self) -> list[tuple[str, str]]:
        # a dependency onto a hybrid-capable server imposes nothing
        return [(a, b) for a, b in self.precedences if b not in self.hybrid_capable]


def objective(problem: PlanningProblem, step: Mapping[str, int]) -> float:
    return sum(problem.weight[u] * (step[u] + 1) for u in problem.units)


def check_plan(problem: PlanningProblem, step: Mapping[str, int]) -> dict[str, Any]:
    violations: list[str] = []
    for u in problem.units:
        if u not in step:
            violations.append(f"unscheduled:{u}")
        elif not 0 <= step[u] < problem.horizon:
            violations.append(f"outside_horizon:{u}")
        elif u in problem.windows and step[u] not in problem.windows[u]:
            violations.append(f"outside_window:{u}")
    load: dict[int, int] = {}
    for u, s in step.items():
        load[s] = load.get(s, 0) + 1
    violations += [f"capacity:{t}" for t, n in load.items() if n > problem.capacity]
    violations += [f"order:{a}>{b}" for a, b in problem.effective_precedences()
                   if a in step and b in step and step[a] > step[b]]
    body = {"plan": dict(sorted(step.items())), "capacity": problem.capacity,
            "precedences": sorted(problem.effective_precedences())}
    return {"valid": not violations, "violations": violations[:50],
            "certificate_sha256": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
            "objective": objective(problem, step) if not violations else None}


def greedy_plan(problem: PlanningProblem) -> dict[str, int]:
    preds: dict[str, set[str]] = {u: set() for u in problem.units}
    for a, b in problem.effective_precedences():
        preds[b].add(a)
    done: dict[str, int] = {}
    t = 0
    while len(done) < len(problem.units) and t < problem.horizon:
        ready = [u for u in problem.units if u not in done and all(p in done and done[p] <= t for p in preds[u])
                 and (u not in problem.windows or t in problem.windows[u])]
        ready.sort(key=lambda u: (-problem.weight[u], u))
        for u in ready[: problem.capacity]:
            done[u] = t
        t += 1
    return done


def solve_optimal(problem: PlanningProblem, time_limit_s: float = 30.0, workers: int = 4) -> dict[str, Any]:
    from ortools.sat.python import cp_model

    m = cp_model.CpModel()
    scale = 1000
    s = {}
    for i, u in enumerate(problem.units):
        allowed = problem.windows.get(u)
        if allowed:
            s[u] = m.NewIntVarFromDomain(cp_model.Domain.FromValues(sorted(allowed)), f"s_{i}")
        else:
            s[u] = m.NewIntVar(0, problem.horizon - 1, f"s_{i}")
    intervals = [m.NewFixedSizeIntervalVar(s[u], 1, f"i_{i}") for i, u in enumerate(problem.units)]
    m.AddCumulative(intervals, [1] * len(intervals), problem.capacity)
    for a, b in problem.effective_precedences():
        m.Add(s[a] <= s[b])
    m.Minimize(sum(int(round(scale * problem.weight[u])) * (s[u] + 1) for u in problem.units))
    greedy = greedy_plan(problem)
    if len(greedy) == len(problem.units):
        for u, t in greedy.items():
            m.AddHint(s[u], t)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = workers
    t0 = time.perf_counter()
    status = solver.Solve(m)
    dt = time.perf_counter() - t0
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": solver.StatusName(status), "seconds": dt}
    plan = {u: int(solver.Value(s[u])) for u in problem.units}
    obj = solver.ObjectiveValue() / scale
    bound = solver.BestObjectiveBound() / scale
    return {"status": solver.StatusName(status), "plan": plan, "objective": obj, "lower_bound": bound,
            "proven_gap": (obj - bound) / obj if obj else 0.0, "seconds": dt}


def random_enterprise(n: int, *, seed: int, capacity_fraction: float = 0.05, hybrid_fraction: float = 0.2,
                      window_fraction: float = 0.1, ca_fraction: float = 0.03) -> PlanningProblem:
    """Layered service graph (front -> middle -> back), CAs anchoring leaves, heavy-tailed risk."""

    rng = random.Random(seed)
    units = [f"u{i:05d}" for i in range(n)]
    layers = [units[: n // 4], units[n // 4: 3 * n // 4], units[3 * n // 4:]]
    prec: list[tuple[str, str]] = []
    for upper, lower in ((layers[0], layers[1]), (layers[1], layers[2])):
        for v in upper:
            for u in rng.sample(lower, k=min(len(lower), rng.randint(1, 3))):
                prec.append((v, u))          # client v before server u
    cas = rng.sample(units, k=max(1, int(ca_fraction * n)))
    for ca in cas:
        for leaf in rng.sample(units, k=min(n - 1, rng.randint(2, 8))):
            if leaf != ca:
                prec.append((ca, leaf))      # anchor before the certificates it issues
    weight = {u: round(rng.paretovariate(1.5), 3) for u in units}
    for ca in cas:
        weight[ca] *= 3                       # forge-later blast radius
    capacity = max(1, int(capacity_fraction * n))
    horizon = 2 * ((n + capacity - 1) // capacity) + 2
    hybrid = set(rng.sample(units, k=int(hybrid_fraction * n)))
    windows = {}
    for u in rng.sample(units, k=int(window_fraction * n)):
        start = rng.randrange(0, horizon // 2)
        windows[u] = list(range(start, horizon, 2)) or [horizon - 1]
    # keep the problem feasible: drop precedences that create cycles
    order = {u: i for i, u in enumerate(units)}
    prec = [(a, b) for a, b in prec if order[a] < order[b] or b in cas and a not in cas]
    seen, acyclic = set(), []
    for a, b in prec:
        if (b, a) not in seen:
            seen.add((a, b))
            acyclic.append((a, b))
    return PlanningProblem(units, weight, acyclic, capacity, horizon, hybrid, windows)
