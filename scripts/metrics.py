"""实验结果指标计算（§6.1）：
- 操作保留率 ops_retained
- 自动化覆盖率 auto_coverage
- 排序信息保留率 info_retention = 1 - τ̂
- 因果违反数 causal_violations（τ_causal）
- 语义有效性 semantic_validity（CAS 相对发布副本本地状态）
- Gini（反转分布公平性）
"""
from tau import tau, positions, tau_causal_order, tauhat_effective, gini as gini_fn


def evaluate(scenario, sigma, coverage, unresolved, strategy):
    """计算全部指标。返回 dict。"""
    N = scenario.N
    M = len(scenario.D)
    op_meta = scenario.ops

    # 操作保留率
    ops_retained = len(sigma) / max(1, M)

    # 各副本 τ
    d = []
    for rl in scenario.replica_logs:
        d.append(tau(sigma, rl))
    total = sum(d)

    # 因果分量
    causal_viol = tau_causal_order(sigma, scenario.causal_pairs, scenario.n_ab)
    contested = max(0.0, total - causal_viol)

    # 语义有效性：cas 操作相对发布副本本地状态的正确性
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
    """Fraction of cas 操作在合并序中相对其发布副本本地状态仍有效。

    定义：cas 操作 o 在合并序 σ 中有效，当且仅当所有与其同 key 且
    不可交换、且在 σ 中先于 o 的操作，在 o 的发布副本本地日志中也先于 o。
    """
    pos = positions(sigma)
    op_meta = scenario.ops
    cas_ops = [o for o in sigma if op_meta[o]["otype"] == "cas"]
    if not cas_ops:
        return 1.0  # 无 cas 操作则语义有效性视为饱和
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
                # p 在合并序中先于 o；若发布副本未观测到 p 先于 o，则 o 失效
                if p not in issuer_pos or issuer_pos[p] > issuer_pos.get(o, 1 << 60):
                    ok = False
                    break
        if ok:
            valid += 1
    return valid / len(cas_ops)
