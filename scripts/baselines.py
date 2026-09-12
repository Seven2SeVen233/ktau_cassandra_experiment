"""基线合并策略（§6.4）：LWW、Vector Clock、Pure CRDT、CRDT+LWW 回退、Leader overwrite。

统一接口：merge_<name>(scenario, seed) -> (sigma, coverage, unresolved)
- sigma: 合并后的总序（op_id 列表）
- coverage: 自动化覆盖率（无需应用代码/回退的比例）
- unresolved: 需应用介入的操作数
"""
import random

import numpy as np

from tau import positions

COMMUTATIVE = {"incr"}


def op_meta(scenario, op):
    return scenario.ops[op]


def merge_lww(scenario, seed=0):
    rng = random.Random(seed)
    skew = scenario.skew  # {replica: µs}
    items = list(scenario.D)
    items.sort(key=lambda o: (scenario.ops[o]["ts"] + skew.get(scenario.ops[o]["replica"], 0.0), rng.random()))
    return items, 1.0, 0


def topo_order(scenario, seed=0, tiebreak="random"):
    """DAG 拓扑序；并发对按 tiebreak（random 或 ts）处理。"""
    rng = random.Random(seed)
    adj = {o: [] for o in scenario.D}
    indeg = {o: 0 for o in scenario.D}
    for a, b in scenario.causal_edges:
        if a in scenario.D and b in scenario.D:
            adj[a].append(b)
            indeg[b] += 1
    ready = [o for o in scenario.D if indeg[o] == 0]
    # 相同就绪条件下按 (ts, rng) 稳定
    ready.sort(key=lambda o: (scenario.ops[o]["ts"], rng.random()))
    res = []
    while ready:
        o = ready.pop(0)
        res.append(o)
        for b in adj[o]:
            indeg[b] -= 1
            if indeg[b] == 0:
                ready.append(b)
                ready.sort(key=lambda x: (scenario.ops[x]["ts"], rng.random()))
    if len(res) != len(scenario.D):
        # 出现环（不应发生）：回退 ts 序
        res = sorted(scenario.D, key=lambda o: scenario.ops[o]["ts"])
    return res


def merge_vc(scenario, seed=0):
    """Vector Clock：只保证因果边；并发同 key 不可交换写交由应用。"""
    sigma = topo_order(scenario, seed=seed)
    unresolved = 0
    for o in scenario.D:
        if scenario.ops[o]["otype"] not in COMMUTATIVE:
            if _has_concurrent_same_key_conflict(scenario, o):
                unresolved += 1
    coverage = 1.0 - unresolved / max(1, len(scenario.D))
    return sigma, coverage, unresolved


def _has_concurrent_same_key_conflict(scenario, o):
    """op o 是否存在同 key 且与 o 并发的不可交换操作（需应用解决）。"""
    m = scenario.ops[o]
    if m["otype"] in COMMUTATIVE:
        return False
    key = m["key"]
    oid = o
    for other in scenario.D:
        if other == oid:
            continue
        om = scenario.ops[other]
        if om["key"] != key or om["otype"] in COMMUTATIVE:
            continue
        # 判断 o 与 other 是否并发（无因果路径）
        if not _comparable(scenario, oid, other):
            return True
    return False


def _comparable(scenario, a, b):
    """a、b 是否因果可比（有路径）。"""
    if a == b:
        return True
    seen = set()
    stack = [a]
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x)
        if x == b:
            return True
        for nxt in scenario.adj.get(x, ()):
            if nxt not in seen:
                stack.append(nxt)
    return False


def merge_crdt_pure(scenario, seed=0):
    """Pure CRDT：可交换操作自动合并（ts 序）；不可交换并发写未决。"""
    resolved = [o for o in scenario.D if scenario.ops[o]["otype"] in COMMUTATIVE]
    unresolved_ops = [
        o for o in scenario.D
        if scenario.ops[o]["otype"] not in COMMUTATIVE
        and _has_concurrent_same_key_conflict(scenario, o)
    ]
    # 未决操作也需一个总序（论文表4中 pure CRDT 信息保留≈LWW，采用 ts 序），
    # 但自动化覆盖率只统计可自动解决的部分。
    sigma = sorted(scenario.D, key=lambda o: scenario.ops[o]["ts"])
    unresolved = len(unresolved_ops)
    coverage = (len(scenario.D) - unresolved) / max(1, len(scenario.D))
    return sigma, coverage, unresolved


def merge_crdt_lww(scenario, seed=0):
    """CRDT + LWW 回退：可交换走 CRDT（ts 序），不可交换回退 LWW 时间戳。"""
    return merge_lww(scenario, seed=seed)


def merge_leader(scenario, seed=0):
    """Leader overwrite：保留最大分区（副本）的操作，按 leader 日志序；其余截断。"""
    if not scenario.partitions:
        return sorted(scenario.D, key=lambda o: scenario.ops[o]["ts"]), 1.0, 0
    leader = max(scenario.partitions, key=len)
    leader_set = set(leader)
    sigma = [o for o in scenario.replica_logs[scenario.leader_idx]
             if o in leader_set]
    # 补充 leader 分区中未出现在日志里的操作（理论上不会发生）
    remaining = sorted((leader_set - set(sigma)), key=lambda o: scenario.ops[o]["ts"])
    sigma = sigma + remaining
    return sigma, 1.0, 0


def all_strategies():
    return {
        "lww": merge_lww,
        "vc": merge_vc,
        "crdt_pure": merge_crdt_pure,
        "crdt_lww": merge_crdt_lww,
        "leader": merge_leader,
        "ranked_pairs": merge_ranked_pairs,
    }


def merge_ranked_pairs(scenario, seed=0):
    from ranked_pairs import ranked_pairs

    sigma = ranked_pairs(scenario.replica_logs, scenario.D)
    return sigma, 1.0, 0
