"""场景生成器（§5.4）：从真实 trace 构造后分区协调场景。

- 全局：trace 操作 → 逻辑副本归属（node 哈希取模）、语义类型、冲突键
- 每 trial：采样 M 个发散操作 D，构建因果 DAG（链边 + 跨副本边，调节因果密度），
  生成各副本局部日志（观测子集 + 并发对抖动噪声 + 时钟偏移）
"""
import hashlib
import random
from collections import deque

import numpy as np


def assign_replicas(ops_by_node, N, rng):
    """唯一 node → 逻辑副本（轮转），保持稳定。返回 {node: replica}。"""
    nodes = sorted(ops_by_node.keys())
    node_replica = {}
    for i, node in enumerate(nodes):
        node_replica[node] = i % N
    return node_replica


def op_type_from_level(level, label):
    """BGL Level/Label → 操作语义类型（§5.3 映射）。"""
    lv = (level or "").upper()
    if lv in ("FATAL", "SEVERE", "ERROR") or (label and label != "-"):
        return "cas"
    if lv == "WARNING":
        return "set"
    return "incr"


def reachability(adj, nodes):
    """返回 {(a,b): 可达}，b 从 a 出发可达。"""
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
    """一次 trial 的协调场景。"""

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
    """从 trace 构造的全局操作池。"""

    def __init__(self, ops_by_node, N, K=8):
        self.N = N
        self.K = K
        self.node_replica = {}
        self.ops = {}  # op_id -> meta
        self.ops_by_replica = {}  # replica -> [op_id (按 ts)]
        self.all_op_ids = []
        rng = random.Random(42)
        # node -> replica 稳定分配（基于 node 名哈希，而非轮转，保证可复现且均衡）
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
    """采样 M 个操作构成单冲突组（并发连通），并构建场景。

    conflict: 'low'|'high' → 目标因果密度 0.35 / 0.10
    obs / noise / skew_us: 副本观测比例、并发对抖动噪声、时钟偏移上限(µs)，
    与 config.yaml 的 model 段对应。
    """
    rng = random.Random(seed)
    N = tm.N
    target_density = 0.35 if conflict == "low" else 0.10

    ops = tm.ops
    for _ in range(max_tries):
        D = rng.sample(tm.all_op_ids, M)
        ops_sorted = sorted(D, key=lambda o: ops[o]["ts"])

        # --- 构造因果 DAG：链边(p_in) + 跨副本边(p_cross)，p_cross 二分调节密度 ---
        adj = {o: [] for o in D}
        # 链边：副本内按 ts 相邻观测操作
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
        # 确保边集无环（所有边按 ts 定向，天然无环）

        # --- 各副本局部日志 ---
        reach = reachability(adj, D)
        replica_logs = []
        for rep in range(N):
            seq = [o for o in tm.ops_by_replica[rep] if o in D]
            log = [o for o in seq if (o in D and (ops[o]["issuer"] == rep or rng.random() < obs))]
            # 副本日志必须因果一致（ts 序天然满足）；施加并发对抖动噪声
            for i in range(len(log) - 1):
                if rng.random() < noise and (log[i + 1], log[i]) not in reach \
                        and (log[i], log[i + 1]) not in reach:
                    log[i], log[i + 1] = log[i + 1], log[i]
            replica_logs.append(log)

        # --- 一致因果约束 ---
        causal_pairs = []
        n_ab = {}
        for a in D:
            for b in adj.get(a, ()):
                if b in D:
                    n = sum(1 for rl in replica_logs if a in rl and b in rl)
                    if n > 0:
                        causal_pairs.append((a, b))
                        n_ab[(a, b)] = n
        # 计算最终密度（仅保留被观测到的约束对近似；用全图密度）
        d_final = density(adj)

        # --- 冲突组（并发图连通分量）---
        concurrency = {(a, b) for a in D for b in D if a != b
                       and (a, b) not in reachability(adj, D) and (b, a) not in reachability(adj, D)}
        # 用并查集求并发连通分量
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
            break  # 单冲突组
        # 若未连通，接受最大组（在后续可能重试）
        if max(group_sizes, default=0) >= M * 0.6:
            break

    # 分区（leader overwrite 用）：多数派/少数派
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
    """解析 BGL 行：Label UnixTs Date Node Ts2 Node2 Component Type Level Content..."""
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


def parse_bgl_file(path, max_ops=2000):
    """读取 BGL 日志文件 → {node: [op meta]}（含 id、ts(µs) 微秒时间戳）。"""
    ops_by_node = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= max_ops:
                break
            m = parse_bgl_line(line)
            if m is None:
                continue
            # 解析 ts2: yyyy-mm-dd-hh.mm.ss.uuuuuu → 微秒
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
