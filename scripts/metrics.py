"""Experiment result metrics (§6.1):
- operation retention rate ops_retained
- automation coverage auto_coverage
- ranking information retention info_retention = 1 - τ̂
- causal violation count causal_violations (τ_causal)
- semantic validity semantic_validity (CAS relative to issuing replica's local state)
- Gini (inversion distribution fairness)
"""
from tau import tau, positions, tau_causal_order, tauhat_effective, gini as gini_fn


def evaluate(scenario, sigma, coverage, unresolved, strategy):
    """Compute all metrics. Returns a dict."""
    N = scenario.N
    M = len(scenario.D)
    op_meta = scenario.ops

    # Operation retention rate
    ops_retained = len(sigma) / max(1, M)

    # Per-replica τ
    d = []
    for rl in scenario.replica_logs:
        d.append(tau(sigma, rl))
    total = sum(d)

    # Causal component
    causal_viol = tau_causal_order(sigma, scenario.causal_pairs, scenario.n_ab)
    contested = max(0.0, total - causal_viol)

    # Semantic validity: correctness of cas operations relative to the issuing
    # replica's local state
    sem_valid = semantic_validity(scenario, sigma)

    g = gini_fn(d) if len(d) > 1 else 0.0

    return {
        "strategy": strategy,
        "M": M,
        "ops_retained": ops_retained,
        "auto_coverage": coverage,
        "unresolved": unresolved,
        "tau_total": total,
        "tau_causal": causal_viol,
        "tau_contested": contested,
        "tauhat": tauhat_effective(total, scenario.replica_logs),
        "info_retention": 1.0 - tauhat_effective(total, scenario.replica_logs),
        "semantic_validity": sem_valid,
        "gini": g,
        "per_replica_tau": d,
    }


def semantic_validity(scenario, sigma):
    """Fraction of cas operations that remain valid in the merged order relative to
    their issuing replica's local state.

    Definition: a cas operation o is valid in merged order σ iff every operation
    with the same key that is non-commutative and precedes o in σ also precedes o
    in the issuing replica's local log.
    """
    pos = positions(sigma)
    op_meta = scenario.ops
    cas_ops = [o for o in sigma if op_meta[o]["otype"] == "cas"]
    if not cas_ops:
        return 1.0  # no cas operations → semantic validity is saturated
    valid = 0
    for o in cas_ops:
        issuer = op_meta[o]["issuer"]
        issuer_log = scenario.replica_logs[issuer]
        issuer_pos = positions(issuer_log)
        key = op_meta[o]["key"]
        ok = True
        for p in sigma:
            if p == o:
                break
            pm = op_meta[p]
            if pm["key"] == key and pm["otype"] != "incr":
                # p precedes o in the merged order; if the issuer did not observe
                # p before o, then o is invalid
                if p not in issuer_pos or issuer_pos[p] > issuer_pos.get(o, 1 << 60):
                    ok = False
                    break
        if ok:
            valid += 1
    return valid / len(cas_ops)
