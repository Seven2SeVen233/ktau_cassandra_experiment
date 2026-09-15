"""Kendall τ distance computation module (paper §5.1).

- tau(σ, Li): pairwise inversion count between merged order σ and replica i's local log
- tau_total / tauhat / info_retention
- tau_causal / tau_contested (paper Proposition 2 causal decomposition)
- gini (inversion distribution fairness, §5.5)
"""
from collections import defaultdict

import numpy as np


def positions(order):
    """order: op_id list -> {op: index}"""
    return {op: i for i, op in enumerate(order)}


def tau(order, replica_log):
    """Kendall tau distance between two rankings (counted by pairwise relative order).

    order and replica_log are both lists over the same operation set (or subsets).
    Only pairs that appear in both are counted.
    """
    if len(order) < 2 or len(replica_log) < 2:
        return 0
    pos = positions(order)
    # Scan in replica_log order with a Fenwick tree to count inversions
    items = [op for op in replica_log if op in pos]
    # Map replica_log order to 0..k-1 and merged order to its position
    mapped = [(pos[op], i) for i, op in enumerate(items)]
    mapped.sort()
    # Count inversions of the second component
    size = len(mapped)
    bit = [0] * (size + 2)

    def upd(i, v):
        i += 1
        while i <= size:
            bit[i] += v
            i += i & -i

    def qry(i):
        s = 0
        while i > 0:
            s += bit[i]
            i -= i & -i
        return s

    inv = 0
    inserted = 0
    for _, rank in mapped:  # rank = index in replica_log
        # Number of already inserted elements with rank greater than current = inversions
        inv += inserted - qry(rank + 1)
        upd(rank, 1)
        inserted += 1
    return inv


def tau_causal_order(order, causal_pairs, n_ab):
    """Causal component: for each violated consistent causal constraint (a,b),
    the exact contribution is n_ab.

    causal_pairs: list of (a, b); n_ab[a,b] = number of replicas observing both.
    """
    pos = positions(order)
    viol = 0
    for a, b in causal_pairs:
        if pos.get(a, -1) > pos.get(b, 1 << 60):
            viol += n_ab[(a, b)]
    return viol


def tau_contested(total, causal):
    return max(0, total - causal)


def tauhat(total, N, M):
    """Normalized τ (full-observation assumption): denominator N·M(M−1)/2 assumes
    every replica holds all M operations.

    Use tauhat_effective when replica logs may be incomplete.
    """
    denom = N * M * (M - 1) / 2
    return total / denom if denom > 0 else 0.0


def observed_pairs(replica_logs):
    """Z_eff = Σ_i |Li|(|Li|−1)/2: pairs actually observed by each replica
    (the effective denominator).

    Missing handling: a pair (a,b) not co-occurring in replica Li contributes
    nothing to τ(σ,Li) and is excluded from the denominator.
    Boundary: |Li| ≤ 1 → that replica contributes 0 pairs; if every replica log
    has < 2 operations → Z_eff = 0.
    """
    return sum(len(rl) * (len(rl) - 1) / 2 for rl in replica_logs)


def tauhat_effective(total, replica_logs):
    """Effective normalization τ̂: τ̂(σ) = τtotal(σ) / Z_eff.

    When all replicas observe all operations, Z_eff = N·M(M−1)/2, reducing to tauhat.
    """
    z = observed_pairs(replica_logs)
    return total / z if z > 0 else 0.0


def info_retention(total, N, M):
    return 1.0 - tauhat(total, N, M)


def info_retention_effective(total, replica_logs):
    return 1.0 - tauhat_effective(total, replica_logs)


def gini(values):
    """Gini coefficient (distributional fairness of per-replica τ distances, §5.5)."""
    v = np.asarray(values, dtype=float)
    if v.size == 0 or v.sum() == 0:
        return 0.0
    v = np.sort(v)
    n = v.size
    cum = np.cumsum(v)
    return (2 * np.sum((np.arange(1, n + 1)) * v) - (n + 1) * cum[-1]) / (n * cum[-1])


def pairwise_margins(replica_logs, op_set):
    """Compute pairwise margins from per-replica votes: n(a≻b) - n(b≻a).

    Only replicas containing both a and b are counted. Returns {(a,b): margin}.
    """
    pref = defaultdict(int)  # (a,b): n(a≻b)
    contain = defaultdict(int)  # (a,b): number of co-containing replicas
    for rlog in replica_logs:
        pos = positions(rlog)
        seq = [op for op in rlog if op in op_set]
        for i in range(len(seq)):
            for j in range(i + 1, len(seq)):
                pref[(seq[i], seq[j])] += 1
                contain[(seq[i], seq[j])] += 1
    margins = {}
    for (a, b), c in contain.items():
        nb = pref[(a, b)]
        na = c - nb
        margins[(a, b)] = nb - na
    return margins
