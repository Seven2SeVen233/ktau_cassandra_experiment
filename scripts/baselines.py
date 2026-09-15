"""Baseline merge strategies (§6.4): LWW, Vector Clock, Pure CRDT, CRDT+LWW fallback,
Leader overwrite.

Unified interface: merge_<name>(scenario, seed) -> (sigma, coverage, unresolved)
- sigma: merged total order (op_id list)
- coverage: automation coverage (fraction resolvable without application code/fallback)
- unresolved: number of operations requiring application intervention
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


def topo_order(scenario, seed=0, tiebreak="ts"):
    """DAG topological order. tiebreak: 'ts' (ts primary, random secondary) or
    'random' (purely random)."""
    rng = random.Random(seed)
    adj = {o: [] for o in scenario.D}
    indeg = {o: 0 for o in scenario.D}
    for a, b in scenario.causal_edges:
        if a in scenario.D and b in scenario.D:
            adj[a].append(b)
            indeg[b] += 1
    if tiebreak == "ts":
        def key(o):
            return (scenario.ops[o]["ts"], rng.random())
    else:
        def key(o):
            return rng.random()
    ready = [o for o in scenario.D if indeg[o] == 0]
    ready.sort(key=key)
    res = []
    while ready:
        o = ready.pop(0)
        res.append(o)
        for b in adj[o]:
            indeg[b] -= 1
            if indeg[b] == 0:
                ready.append(b)
                ready.sort(key=key)
    if len(res) != len(scenario.D):
        # Cycle appeared (should not happen): fall back to ts order
        res = sorted(scenario.D, key=lambda o: scenario.ops[o]["ts"])
    return res


def merge_vc(scenario, seed=0):
    """Vector Clock: guarantees causal edges only; concurrent same-key
    non-commutative writes are deferred to the application (random decision)."""
    sigma = topo_order(scenario, seed=seed, tiebreak="random")
    unresolved = 0
    for o in scenario.D:
        if scenario.ops[o]["otype"] not in COMMUTATIVE:
            if _has_concurrent_same_key_conflict(scenario, o):
                unresolved += 1
    coverage = 1.0 - unresolved / max(1, len(scenario.D))
    return sigma, coverage, unresolved


def _has_concurrent_same_key_conflict(scenario, o):
    """Does op o have a same-key non-commutative operation concurrent with o
    (requiring application resolution)?"""
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
        # Check whether o and other are concurrent (no causal path)
        if not _comparable(scenario, oid, other):
            return True
    return False


def _comparable(scenario, a, b):
    """Are a and b causally comparable (there is a path)?"""
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
    """Pure CRDT: commutative operations merge automatically (ts order);
    non-commutative concurrent writes stay unresolved."""
    resolved = [o for o in scenario.D if scenario.ops[o]["otype"] in COMMUTATIVE]
    unresolved_ops = [
        o for o in scenario.D
        if scenario.ops[o]["otype"] not in COMMUTATIVE
        and _has_concurrent_same_key_conflict(scenario, o)
    ]
    # Unresolved operations still need a total order (in Table 4 of the paper,
    # pure CRDT information retention ≈ LWW, using ts order),
    # but automation coverage only counts the auto-resolvable part.
    sigma = sorted(scenario.D, key=lambda o: scenario.ops[o]["ts"])
    unresolved = len(unresolved_ops)
    coverage = (len(scenario.D) - unresolved) / max(1, len(scenario.D))
    return sigma, coverage, unresolved


def merge_crdt_lww(scenario, seed=0):
    """CRDT + LWW fallback: commutative ops go through CRDT (ts order),
    non-commutative ops fall back to LWW timestamps."""
    return merge_lww(scenario, seed=seed)


def merge_leader(scenario, seed=0):
    """Leader overwrite: retain operations issued in the largest partition
    (replicas), in leader-log order; the rest are truncated."""
    if not scenario.partitions:
        return sorted(scenario.D, key=lambda o: scenario.ops[o]["ts"]), 1.0, 0
    leader = max(scenario.partitions, key=len)
    leader_set = set(leader)
    # Retain operations issued by replicas in the leader partition (in the leader
    # replica's local log order)
    sigma = [o for o in scenario.replica_logs[scenario.leader_idx]
             if scenario.ops[o]["issuer"] in leader_set]
    # Append operations issued in the leader partition that do not appear in the
    # leader's log (should not happen in theory)
    retained = set(sigma)
    remaining = sorted(
        (o for o in scenario.D
         if scenario.ops[o]["issuer"] in leader_set and o not in retained),
        key=lambda o: scenario.ops[o]["ts"])
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
    """τ-minimizing strategy (causally constrained Ranked Pairs, §6.2 revised model).

    Under partially observed ballots, causal edges are locked first (margin = +∞),
    then contested pairs are aggregated by majority evidence; the output is always
    a linear extension of the causal DAG (τ_causal = 0 holds unconditionally),
    with no dissemination phase required.
    """
    from ranked_pairs import ranked_pairs_causal

    sigma = ranked_pairs_causal(scenario.replica_logs, scenario.D, scenario.causal_edges)
    return sigma, 1.0, 0


def merge_ranked_pairs_unconstrained(scenario, seed=0):
    """Plain RP (no causal pre-locking), used to quantify the repair cost of
    "detect-and-repair": its output may violate causal edges under partial
    observation; the §B.4 theoretical counterexample and the repair counts
    measured in E1 come from outputs of this kind."""
    from ranked_pairs import ranked_pairs

    sigma = ranked_pairs(scenario.replica_logs, scenario.D)
    return sigma, 1.0, 0
