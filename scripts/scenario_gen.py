"""Scenario generator (§5.4): constructs post-partition reconciliation scenarios
from real traces.

- Global: trace operations → logical replica assignment (node hash modulo),
  semantic type, conflict key
- Per trial: sample M divergent operations D, build a causal DAG (chain edges +
  cross-replica edges, tuning causal density), and generate each replica's local
  log (observed subset + concurrent-pair jitter noise + clock skew)
"""
import hashlib
import random
from collections import deque

import numpy as np


def assign_replicas(ops_by_node, N, rng):
    """Unique node → logical replica (round-robin), kept stable. Returns {node: replica}."""
    nodes = sorted(ops_by_node.keys())
    node_replica = {}
    for i, node in enumerate(nodes):
        node_replica[node] = i % N
    return node_replica


def op_type_from_level(level, label):
    """BGL Level/Label → operation semantic type (§5.3 mapping)."""
    lv = (level or "").upper()
    if lv in ("FATAL", "SEVERE", "ERROR") or (label and label != "-"):
        return "cas"
    if lv == "WARNING":
        return "set"
    return "incr"


def reachability(adj, nodes):
    """Returns {(a,b): reachable}, i.e., b is reachable from a."""
    reach = set()
    for a in nodes:
        seen = {a}
        stack = list(adj.get(a, ()))
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend(adj.get(x, ()))
        for b in seen:
            if b != a:
                reach.add((a, b))
    return reach


class Scenario:
    """Reconciliation scenario for a single trial."""

    def __init__(self, ops, D, replica_logs, causal_edges, adj, causal_pairs,
                 n_ab, partitions, leader_idx, skew, N, causal_density, conflict_groups):
        self.ops = ops
        self.D = set(D)
        self.replica_logs = replica_logs
        self.causal_edges = causal_edges
        self.adj = adj
        self.causal_pairs = causal_pairs
        self.n_ab = n_ab
        self.partitions = partitions
        self.leader_idx = leader_idx
        self.skew = skew
        self.N = N
        self.causal_density = causal_density
        self.conflict_groups = conflict_groups


class TraceModel:
    """Global operation pool constructed from a trace."""

    def __init__(self, ops_by_node, N, K=8):
        self.N = N
        self.K = K
        self.node_replica = {}
        self.ops = {}  # op_id -> meta
        self.ops_by_replica = {}  # replica -> [op_id (ordered by ts)]
        self.all_op_ids = []
        rng = random.Random(42)
        # Stable node → replica assignment (based on node-name hash, not round-robin,
        # to guarantee reproducibility and balance)
        for node in sorted(ops_by_node.keys()):
            self.node_replica[node] = int(hashlib.md5(node.encode()).hexdigest(), 16) % N
        for replica in range(N):
            self.ops_by_replica[replica] = []
        for node, oplist in ops_by_node.items():
            rep = self.node_replica[node]
            for m in oplist:
                m = dict(m)
                m["replica"] = rep
                m["issuer"] = rep
                m["key"] = sum(ord(c) for c in node) % K if m["otype"] != "incr" else 0
                self.ops[m["id"]] = m
                self.ops_by_replica[rep].append(m["id"])
        for rep in self.ops_by_replica:
            self.ops_by_replica[rep].sort(key=lambda o: self.ops[o]["ts"])
        self.all_op_ids = list(self.ops.keys())


def sample_conflict_group(tm, seed, M, conflict, max_tries=50,
                          obs=0.9, noise=0.05, skew_us=500.0):
    """Sample M operations forming a single conflict group (concurrency-connected)
    and build the scenario.

    conflict: 'low'|'high' → target causal density 0.35 / 0.10
    obs / noise / skew_us: replica observation ratio, concurrent-pair jitter noise,
    clock-skew bound (µs), matching the model section of config.yaml.
    """
    rng = random.Random(seed)
    N = tm.N
    target_density = 0.35 if conflict == "low" else 0.10

    ops = tm.ops
    for _ in range(max_tries):
        D = rng.sample(tm.all_op_ids, M)
        ops_sorted = sorted(D, key=lambda o: ops[o]["ts"])

        # --- Build causal DAG: chain edges (p_in) + cross-replica edges (p_cross,
        #     binary search tunes density) ---
        adj = {o: [] for o in D}
        # Chain edges: temporally adjacent observed ops within a replica
        for rep in range(N):
            seq = [o for o in tm.ops_by_replica[rep] if o in D]
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
            return len(reach) / n_pairs

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
        # The edge set is acyclic by construction (all edges oriented by ts)

        # --- Per-replica local logs ---
        reach = reachability(adj, D)
        replica_logs = []
        for rep in range(N):
            seq = [o for o in tm.ops_by_replica[rep] if o in D]
            log = [o for o in seq if (o in D and (ops[o]["issuer"] == rep or rng.random() < obs))]
            # Replica logs must be causally consistent (ts order satisfies this by
            # construction); apply concurrent-pair jitter noise
            for i in range(len(log) - 1):
                if rng.random() < noise and (log[i + 1], log[i]) not in reach \
                        and (log[i], log[i + 1]) not in reach:
                    log[i], log[i + 1] = log[i + 1], log[i]
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
        # Compute final density (approx. by observed constraint pairs only; use full-graph density)
        d_final = density(adj)

        # --- Conflict groups (concurrency graph connected components) ---
        concurrency = {(a, b) for a in D for b in D if a != b
                       and (a, b) not in reachability(adj, D) and (b, a) not in reachability(adj, D)}
        # Union-find over concurrency-connected components
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
            break  # single conflict group
        # If not connected, accept the largest group (may retry later)
        if max(group_sizes, default=0) >= M * 0.6:
            break

    # Partitioning (for leader overwrite): majority/minority
    rng2 = random.Random(seed + 1)
    if conflict == "low":
        maj = 6
    else:
        maj = 5
    reps = list(range(N))
    rng2.shuffle(reps)
    majority = reps[:maj]
    minority = reps[maj:]
    partitions = [majority, minority]
    leader_idx = majority[0]
    skew = {r: rng2.uniform(0, skew_us) for r in range(N)}

    edge_list = [(a, b) for a in D for b in adj.get(a, ())]
    return Scenario(ops, D, replica_logs, edge_list, adj, causal_pairs,
                    n_ab, partitions, leader_idx, skew, N, d_final, group_sizes)


def parse_bgl_line(line):
    """Parse a BGL line: Label UnixTs Date Node Ts2 Node2 Component Type Level Content..."""
    p = line.rstrip("\n").split(" ")
    if len(p) < 9:
        return None
    return {
        "label": p[0],
        "unix_ts": p[1],
        "date": p[2],
        "node": p[3],
        "ts2": p[4],
        "node2": p[5],
        "component": p[6],
        "type": p[7],
        "level": p[8],
        "content": " ".join(p[9:]),
    }


def disseminate(sc, seed, loss=0.0, jitter=60.0):
    """Dissemination phase (§4.1 assumption): causally ordered gossip makes every
    replica's log complete and causally closed.

    Per replica:
      1) keep the relative order of the observed subset L (adjacent-pair
         constraints) -- this constitutes that replica's vote on concurrent pairs;
      2) missing operations G = D \\ L are treated as arriving via causally ordered
         gossip; with loss>0 they are dropped with probability loss (degraded
         dissemination diagnosis, re-creating "exactly-one observation" cases);
      3) final log = linear extension of (causal DAG edges ∪ L adjacent-order
         constraints); unobserved concurrent operations are ordered by
         ts + per-replica arrival jitter (simulating different delivery orders).

    Returns (new_logs, causal_pairs, n_ab): the complete logs after dissemination
    and the recomputed consistent causal constraints (with loss=0, every causal
    edge has n_ab = N, i.e., agreement across all replicas).
    """
    rng = random.Random(seed)
    ops = sc.ops
    D = set(sc.D)
    new_logs = []
    for L in sc.replica_logs:
        # Observed relative order = that replica's vote; it is only a priority key
        # for topological ordering (causal DAG constraints always take precedence),
        # so votes are always linear extensions of the DAG (causal closure holds by
        # construction); concurrent pairs keep the observed votes, while observed
        # orders contradicting causality are automatically corrected (fixed after
        # dissemination by causal closure).
        L_pos = {o: i for i, o in enumerate(L)}
        G = [o for o in D if o not in L_pos]
        if loss > 0:
            G = [o for o in G if rng.random() >= loss]
        nodes = set(L) | set(G)
        jit = {o: rng.uniform(-jitter, jitter) for o in G}

        def key(o):
            if o in L_pos:
                return (0.0, float(L_pos[o]))  # observed: prefer local observation order
            return (1.0, ops[o]["ts"] + jit[o])  # unobserved: order by delivery arrival

        new_logs.append(_linear_extension(sc.adj, nodes, [], key, ops))
    # Recompute consistent causal constraints (n_ab = N under full ballots unless loss)
    causal_pairs, n_ab = [], {}
    for a in D:
        for b in sc.adj.get(a, ()):
            if b in D:
                n = sum(1 for rl in new_logs if a in rl and b in rl)
                if n > 0:
                    causal_pairs.append((a, b))
                    n_ab[(a, b)] = n
    return new_logs, causal_pairs, n_ab


def _linear_extension(adj, nodes, extra_edges, key_fn, ops):
    """Topological sort of (DAG adj ∪ extra_edges); key_fn decides the ready-queue
    order; falls back to ts order on cycles."""
    nodes = set(nodes)
    adj_all = {o: [] for o in nodes}
    indeg = {o: 0 for o in nodes}
    for o in nodes:
        for b in adj.get(o, ()):
            if b in nodes:
                adj_all[o].append(b)
                indeg[b] += 1
    for a, b in extra_edges:
        if a in nodes and b in nodes:
            adj_all[a].append(b)
            indeg[b] += 1
    ready = [o for o in nodes if indeg[o] == 0]
    ready.sort(key=key_fn)
    res = []
    while ready:
        o = ready.pop(0)
        res.append(o)
        for b in adj_all[o]:
            indeg[b] -= 1
            if indeg[b] == 0:
                ready.append(b)
                ready.sort(key=key_fn)
    if len(res) != len(nodes):
        res = sorted(nodes, key=lambda o: ops[o]["ts"])
    return res


def dissemination_structure(sc, new_logs):
    """Post-dissemination structural diagnosis: ballot length range, exactly-one
    observation count, consistent-causal-pair violation count (for a given order)."""
    D = set(sc.D)
    lens = [len(rl) for rl in new_logs]
    exactly_one = 0
    for a in D:
        for b in sc.adj.get(a, ()):
            if b in D:
                exactly_one += sum(1 for rl in new_logs if (a in rl) != (b in rl))
    return {"min_len": min(lens), "max_len": max(lens),
            "exactly_one_observers": exactly_one}


def parse_bgl_file(path, max_ops=2000):
    """Read a BGL log file → {node: [op meta]} (with id, ts(µs) microsecond timestamps)."""
    ops_by_node = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= max_ops:
                break
            m = parse_bgl_line(line)
            if m is None:
                continue
            # Parse ts2: yyyy-mm-dd-hh.mm.ss.uuuuuu → microseconds
            ts2 = m["ts2"]
            try:
                date_part = ts2[:10]
                time_part = ts2[11:]
                y, mo, d = date_part.split("-")
                h, mi, s = time_part.split(".")
                ss = s[:2]
                us = s[2:]
                us = us.ljust(6, "0")[:6]
                ts_us = (int(y) * 31536000 + int(mo) * 2628000 + int(d) * 86400
                         + int(h) * 3600 + int(mi) * 60 + int(ss)) * 10**6 + int(us)
            except Exception:
                try:
                    ts_us = int(m["unix_ts"]) * 10**6
                except Exception:
                    continue
            op = {
                "id": i,
                "ts": float(ts_us),
                "node": m["node"],
                "otype": op_type_from_level(m["level"], m["label"]),
                "level": m["level"],
                "label": m["label"],
            }
            ops_by_node.setdefault(m["node"], []).append(op)
    return ops_by_node
