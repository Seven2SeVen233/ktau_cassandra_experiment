"""Synthetic workload model (paper §6.1): a synthetic operation pool compatible
with the TraceModel interface + adversarial scenario construction.

Operation pool:
- N logical replicas, K keys
- operation types: incr (commutative, ≈50%), set (≈30%), cas (non-commutative, ≈20%)
- per-replica ts = replica-local ordinal × base + clock skew (skew ≤ skew_us)
  -- the timestamp basis for LWW

Scenario construction (consistent with §6.1):
- sample M divergent operations D, build a causal DAG (intra-replica chain edges +
  cross-replica edges, binary search tunes causal density low≈0.35 / high≈0.10)
- each replica gets a causally consistent log: DAG topological order, concurrent
  pairs ordered by ts + arrival jitter, plus adjacent-swap noise -- replicas
  genuinely disagree on concurrent pairs
- observation ratio obs, noise, clock skew skew_us aligned with config
"""
import random

import numpy as np

from scenario_gen import reachability


class SyntheticModel:
    """Synthetic operation pool. Fields match TraceModel: N, ops, ops_by_replica,
    all_op_ids."""

    def __init__(self, N=10, K=8, pool_size=500, seed=42,
                 incr_ratio=0.5, set_ratio=0.3, base=1.0, skew_us=60.0):
        self.N = N
        self.K = K
        rng = random.Random(seed)
        self.ops = {}
        self.ops_by_replica = {r: [] for r in range(N)}
        op_id = 0
        n_per_rep = max(1, pool_size // N)
        for rep in range(N):
            offset = rng.uniform(0, skew_us)
            for j in range(n_per_rep):
                r = rng.random()
                if r < incr_ratio:
                    otype, key = "incr", 0
                elif r < incr_ratio + set_ratio:
                    otype, key = "set", rng.randrange(K)
                else:
                    otype, key = "cas", rng.randrange(K)
                self.ops[op_id] = {
                    "id": op_id, "ts": j * base + offset,
                    "replica": rep, "issuer": rep, "otype": otype, "key": key,
                }
                self.ops_by_replica[rep].append(op_id)
                op_id += 1
        for rep in range(N):
            self.ops_by_replica[rep].sort(key=lambda o: self.ops[o]["ts"])
        self.all_op_ids = list(self.ops.keys())


def _topological_order(adj, subset, key_fn):
    """DAG topological order (key_fn decides the ready-node dequeue order); falls
    back to ts order on cycles."""
    subset = set(subset)
    adj_s = {o: [b for b in adj.get(o, ()) if b in subset] for o in subset}
    indeg = {o: 0 for o in subset}
    for o in subset:
        for b in adj_s[o]:
            indeg[b] += 1
    ready = [o for o in subset if indeg[o] == 0]
    ready.sort(key=key_fn)
    res = []
    while ready:
        o = ready.pop(0)
        res.append(o)
        for b in adj_s[o]:
            indeg[b] -= 1
            if indeg[b] == 0:
                ready.append(b)
                ready.sort(key=key_fn)
    if len(res) != len(subset):
        res = sorted(subset, key=key_fn)
    return res


def build_synthetic_scenario(pool, seed, M, conflict, obs=0.9, noise=0.05,
                             jitter=60.0, max_tries=50):
    """Build a single-conflict-group scenario; returns a Scenario-compatible object
    (including partitions/leader_idx/skew)."""
    rng = random.Random(seed)
    N = pool.N
    ops = pool.ops
    target_density = 0.35 if conflict == "low" else 0.10

    for _ in range(max_tries):
        D = set(rng.sample(pool.all_op_ids, M))
        ops_sorted = sorted(D, key=lambda o: ops[o]["ts"])

        # --- Causal DAG: chain edges (intra-replica adjacent, p=0.4) +
        #     cross-replica edges (binary search tunes density) ---
        adj = {o: [] for o in D}
        for rep in range(N):
            seq = [o for o in pool.ops_by_replica[rep] if o in D]
            for i in range(len(seq) - 1):
                if rng.random() < 0.4:
                    adj[seq[i]].append(seq[i + 1])

        def edges_from_pcross(pc):
            a = {o: list(v) for o, v in adj.items()}
            for i in range(len(ops_sorted)):
                for j in range(i + 1, len(ops_sorted)):
                    u, v = ops_sorted[i], ops_sorted[j]
                    if ops[u]["replica"] != ops[v]["replica"] and rng.random() < pc:
                        a[u].append(v)
            return a

        def density(a):
            reach = reachability(a, D)
            n_pairs = M * (M - 1) / 2
            return len(reach) / n_pairs if n_pairs else 0.0

        lo, hi = 0.0, 1.0
        best_adj, best_d = None, 0.0
        for _ in range(8):
            pc = (lo + hi) / 2
            a = edges_from_pcross(pc)
            d = density(a)
            best_adj, best_d = a, d
            if abs(d - target_density) < 0.03:
                break
            if d < target_density:
                lo = pc
            else:
                hi = pc
        adj = best_adj
        reach = reachability(adj, D)

        # --- Per-replica log: causally consistent (topological order), concurrent
        #     pairs ordered by ts + jitter ---
        replica_logs = []
        for rep in range(N):
            observed = [o for o in D if ops[o]["issuer"] == rep or rng.random() < obs]
            jit = {o: rng.uniform(-jitter, jitter) for o in observed}
            log = _topological_order(adj, observed,
                                     key_fn=lambda o: ops[o]["ts"] + jit[o])
            # Adjacent-swap noise (concurrent pairs only)
            for i in range(len(log) - 1):
                a, b = log[i], log[i + 1]
                if (rng.random() < noise and (a, b) not in reach
                        and (b, a) not in reach):
                    log[i], log[i + 1] = b, a
            replica_logs.append(log)

        # --- Consistent causal constraints ---
        causal_pairs = []
        n_ab = {}
        for a in D:
            for b in adj.get(a, ()):
                if b in D:
                    n = sum(1 for rl in replica_logs if a in rl and b in rl)
                    if n > 0:
                        causal_pairs.append((a, b))
                        n_ab[(a, b)] = n

        # --- Conflict groups (concurrency-connected components), require single
        #     connectivity ---
        concurrency = {(a, b) for a in D for b in D if a != b
                       and (a, b) not in reach and (b, a) not in reach}
        parent = {o: o for o in D}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[ry] = rx

        for (a, b) in concurrency:
            union(a, b)
        groups = {}
        for o in D:
            groups.setdefault(find(o), []).append(o)
        group_sizes = sorted((len(v) for v in groups.values()), reverse=True)
        if len(groups) == 1:
            break
        if max(group_sizes, default=0) >= M * 0.6:
            break

    # --- Partitions and clock skew (for leader overwrite) ---
    rng2 = random.Random(seed + 1)
    reps = list(range(N))
    rng2.shuffle(reps)
    if conflict == "low":
        partitions = [reps[:7], reps[7:]]
    else:
        partitions = [reps[:4], reps[4:7], reps[7:]]
    leader_idx = partitions[0][0]
    skew = {r: rng2.uniform(0, 60.0) for r in range(N)}

    edge_list = [(a, b) for a in D for b in adj.get(a, ())]
    from scenario_gen import Scenario

    return Scenario(ops, D, replica_logs, edge_list, adj, causal_pairs,
                    n_ab, partitions, leader_idx, skew, N, best_d, group_sizes)
