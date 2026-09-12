"""精确 Kemeny-Young 最优（M ≤ 8，暴力枚举），用于 E3 验证 Ranked Pairs 的接近程度。"""
from itertools import permutations

from tau import tau


def kemeny_exact(replica_logs, op_set):
    """返回 (最优序, 最小总 τ)。M ≤ 8 时可行。"""
    ops = list(op_set)
    best = None
    best_order = None
    for perm in permutations(ops):
        t = sum(tau(perm, rl) for rl in replica_logs)
        if best is None or t < best:
            best = t
            best_order = perm
    return list(best_order), best
