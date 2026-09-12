"""Kendall τ 距离计算模块（论文 §5.1）。

- tau(σ, Li): 合并序 σ 与副本 i 局部日志的成对逆序数
- tau_total / tauhat / info_retention
- tau_causal / tau_contested（论文 Proposition 2 因果分解）
- gini（反转分布公平性，§5.5）
"""
from collections import defaultdict

import numpy as np


def positions(order):
    """order: op_id 列表 -> {op: index}"""
    return {op: i for i, op in enumerate(order)}


def tau(order, replica_log):
    """两个排序之间的 Kendall tau 距离（按成对相对顺序计数）。

    order 与 replica_log 均为同一操作集上的列表（或子集）。
    仅统计同时出现在两者中的操作对。
    """
    if len(order) < 2 or len(replica_log) < 2:
        return 0
    pos = positions(order)
    # 用 Fenwick 树按 replica_log 顺序扫描，统计逆序
    items = [op for op in replica_log if op in pos]
    # 将 replica_log 顺序映射为 0..k-1，合并序映射为其位置
    mapped = [(pos[op], i) for i, op in enumerate(items)]
    mapped.sort()
    # 统计第二个分量的逆序数
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
    for _, rank in mapped:  # rank = 在 replica_log 中的下标
        # 已插入且 rank 大于当前值的个数 = 逆序
        inv += inserted - qry(rank + 1)
        upd(rank, 1)
        inserted += 1
    return inv


def tau_causal_order(order, causal_pairs, n_ab):
    """因果分量：对每条被违反的一致因果约束 (a,b)，精确贡献 n_ab。

    causal_pairs: list of (a, b)；n_ab[a,b] = 同时观测到两者的副本数。
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
    """归一化 τ（满观测假设）：分母 N·M(M−1)/2 假定所有副本含全部 M 个操作。

    当副本日志可能不完整时应使用 tauhat_effective。
    """
    denom = N * M * (M - 1) / 2
    return total / denom if denom > 0 else 0.0


def observed_pairs(replica_logs):
    """Z_eff = Σ_i |Li|(|Li|−1)/2：各副本实际观测到的操作对数（有效分母）。

    缺失处理：某对 (a,b) 未同时出现在副本 Li 中 → 不贡献 τ(σ,Li)，也不计入分母。
    边界条件：|Li| ≤ 1 → 该副本贡献 0 对；全部副本日志均 <2 个操作 → Z_eff = 0。
    """
    return sum(len(rl) * (len(rl) - 1) / 2 for rl in replica_logs)


def tauhat_effective(total, replica_logs):
    """有效归一化 τ̂：τ̂(σ) = τtotal(σ) / Z_eff。

    当所有副本观测全部操作时 Z_eff = N·M(M−1)/2，退化为 tauhat。
    """
    z = observed_pairs(replica_logs)
    return total / z if z > 0 else 0.0


def info_retention(total, N, M):
    return 1.0 - tauhat(total, N, M)


def info_retention_effective(total, replica_logs):
    return 1.0 - tauhat_effective(total, replica_logs)


def gini(values):
    """Gini 系数（每副本 τ 距离的分布公平性，§5.5）。"""
    v = np.asarray(values, dtype=float)
    if v.size == 0 or v.sum() == 0:
        return 0.0
    v = np.sort(v)
    n = v.size
    cum = np.cumsum(v)
    return (2 * np.sum((np.arange(1, n + 1)) * v) - (n + 1) * cum[-1]) / (n * cum[-1])


def pairwise_margins(replica_logs, op_set):
    """由各副本投票计算 pairwise margin：n(a≻b) - n(b≻a)。

    仅统计同时包含 a,b 的副本。返回 {(a,b): margin}。
    """
    pref = defaultdict(int)  # (a,b): n(a≻b)
    contain = defaultdict(int)  # (a,b): 同时包含数
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
