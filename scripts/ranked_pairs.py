"""Ranked Pairs (Tideman) algorithm: a Condorcet-consistent polynomial-time
near-τ-optimal merge (§6.2).

1. Compute pairwise margins;
2. Lock edges in descending margin order, skipping edges that create cycles;
3. Zero-margin / undecided pairs are completed in a deterministic order;
4. Topological sort yields the total order.

Implementation: incrementally maintain the transitive closure of the locked graph
with bitsets (bit j of reach[i] indicates i reaches j), giving O(1) cycle
detection and O(n) bitwise closure updates. Semantically identical to the
per-edge has_cycle version.
"""
from tau import pairwise_margins


def _lock(reach, locked, locked_set, i, j, n):
    """Lock edge (i,j): if j reaches i, the edge would create a cycle and is
    skipped; otherwise lock and update the closure incrementally. Returns whether
    the edge was locked."""
    if (reach[j] >> i) & 1:  # j reaches i → adding (i,j) creates a cycle
        return False
    locked.append((i, j))
    locked_set.add((i, j))
    if not ((reach[i] >> j) & 1):
        reach[i] |= (1 << j) | reach[j]
        for x in range(n):
            if (reach[x] >> i) & 1:
                reach[x] |= reach[i]
    return True


def ranked_pairs(replica_logs, op_set):
    """Return the merged total order (op_id list). op_set: operations in the
    conflict group."""
    margins = pairwise_margins(replica_logs, op_set)
    ops = list(op_set)
    n = len(ops)
    idx = {op: i for i, op in enumerate(ops)}
    edges = sorted(margins.items(), key=lambda kv: kv[1], reverse=True)

    locked = []
    locked_set = set()
    reach = [0] * n

    # 1) strictly positive margins, descending
    for (a, b), m in edges:
        if m <= 0:
            continue
        _lock(reach, locked, locked_set, idx[a], idx[b], n)

    # 2) zero-margin / undecided pairs: completed in op-index order to avoid cycles
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if (i, j) in locked_set or (j, i) in locked_set:
                continue
            m = margins.get((ops[i], ops[j]), margins.get((ops[j], ops[i]), 0))
            if m < 0:
                continue
            _lock(reach, locked, locked_set, i, j, n)

    # 3) Topological sort (deterministic: same dequeue order as the per-edge
    #    has_cycle version)
    from collections import deque

    adj = [[] for _ in range(n)]
    indeg = [0] * n
    for u, v in locked:
        adj[u].append(v)
        indeg[v] += 1
    q = deque([i for i in range(n) if indeg[i] == 0])
    res = []
    while q:
        u = q.popleft()
        res.append(ops[u])
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    assert len(res) == n, f"RP did not cover all operations {len(res)}/{n}"
    return res


def ranked_pairs_causal(replica_logs, op_set, causal_edges):
    """Causally constrained Ranked Pairs (CF-RP, §6.2 revised model): lock all
    causal edges first, then lock the remaining edges in descending margin order
    (skipping cycles), and finally perform a deterministic topological sort.

    Properties (independent of the dissemination premise, hold unconditionally):
    - the output is always a linear extension of the causal DAG
      (τ_causal = 0 by construction);
    - equivalent to "plain RP + post-hoc causal repair": causal edges are treated
      as locked items with margin = +∞, contested pairs are still aggregated by
      majority evidence, and computation is purely local with no communication
      phase.
    """
    margins = pairwise_margins(replica_logs, op_set)
    ops = list(op_set)
    n = len(ops)
    idx = {op: i for i, op in enumerate(ops)}

    locked = []
    locked_set = set()
    reach = [0] * n

    # 0) Pre-lock causal edges (margin = +∞): a cycle here means inconsistent
    #    input (should not happen)
    for a, b in causal_edges:
        if a in idx and b in idx:
            ok = _lock(reach, locked, locked_set, idx[a], idx[b], n)
            assert ok, f"causal edge creates a cycle: inconsistent causal metadata {(a, b)}"

    # 1) strictly positive margins, descending
    edges = sorted(margins.items(), key=lambda kv: kv[1], reverse=True)
    for (a, b), m in edges:
        if m <= 0:
            continue
        _lock(reach, locked, locked_set, idx[a], idx[b], n)

    # 2) zero-margin / undecided pairs completed in index order
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if (i, j) in locked_set or (j, i) in locked_set:
                continue
            m = margins.get((ops[i], ops[j]), margins.get((ops[j], ops[i]), 0))
            if m < 0:
                continue
            _lock(reach, locked, locked_set, i, j, n)

    # 3) Topological sort (deterministic)
    from collections import deque

    adj = [[] for _ in range(n)]
    indeg = [0] * n
    for u, v in locked:
        adj[u].append(v)
        indeg[v] += 1
    q = deque([i for i in range(n) if indeg[i] == 0])
    res = []
    while q:
        u = q.popleft()
        res.append(ops[u])
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    assert len(res) == n, f"CF-RP did not cover all operations {len(res)}/{n}"
    return res
