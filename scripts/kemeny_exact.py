"""Exact Kemeny-Young optimum (M ≤ 8, brute-force enumeration), used by E3 to
validate how close Ranked Pairs gets.

kemeny_exact: unconstrained exact optimum (may violate causal constraints under
partial observation; see B.4).
kemeny_exact_constrained: causally constrained exact optimum -- minimizes total τ
over linear extensions of the causal DAG only.
count_causal_violations: number of causal pairs violated by a plain-RP output
(= the number of causal swaps needed for repair).
"""
from itertools import permutations

from tau import positions, tau


def kemeny_exact(replica_logs, op_set):
    """Return (optimal order, minimum total τ). Feasible for M ≤ 8."""
    ops = list(op_set)
    best = None
    best_order = None
    for perm in permutations(ops):
        t = sum(tau(perm, rl) for rl in replica_logs)
        if best is None or t < best:
            best = t
            best_order = perm
    return list(best_order), best


def is_linear_extension(order, causal_edges):
    pos = positions(order)
    return all(pos.get(a, -1) < pos.get(b, 1 << 60) for a, b in causal_edges)


def kemeny_exact_constrained(replica_logs, op_set, causal_edges):
    """Causally constrained Kemeny optimum: min Στ over the set of linear
    extensions (enumeration feasible for M ≤ 8)."""
    ops = list(op_set)
    edges = [(a, b) for a, b in causal_edges if a in op_set and b in op_set]
    best = None
    best_order = None
    for perm in permutations(ops):
        if not is_linear_extension(perm, edges):
            continue
        t = sum(tau(perm, rl) for rl in replica_logs)
        if best is None or t < best:
            best = t
            best_order = perm
    return list(best_order), best


def count_causal_violations(order, causal_edges):
    """Number of causal edges violated by order (= lower-bound estimate of the
    causal-pair swaps needed for post-hoc repair)."""
    pos = positions(order)
    return sum(1 for a, b in causal_edges if pos.get(a, -1) > pos.get(b, 1 << 60))
