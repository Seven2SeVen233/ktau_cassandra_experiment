"""Ranked Pairs（Tideman）算法：Condorcet 一致的多项式时间近 τ 最优合并（§6.2）。

1. 计算 pairwise margin；
2. 按 margin 降序锁定边，成环则跳过；
3. 零 margin / 未决对按确定序补全；
4. 拓扑排序得到总序。

实现：用 bitset 增量维护锁定图的传递闭包（reach[i] 的第 j 位表示 i 可达 j），
成环判定 O(1)，闭包更新 O(n) 位运算。与逐边 has_cycle 版本语义完全一致。
"""
from tau import pairwise_margins


def _lock(reach, locked, locked_set, i, j, n):
    """锁边 (i,j)：若 j 可达 i 则成环跳过；否则锁边并增量更新闭包。返回是否锁定。"""
    if (reach[j] >> i) & 1:  # j 可达 i → 加边 (i,j) 成环
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
    """返回合并总序（op_id 列表）。op_set: 冲突组内操作集合。"""
    margins = pairwise_margins(replica_logs, op_set)
    ops = list(op_set)
    n = len(ops)
    idx = {op: i for i, op in enumerate(ops)}
    edges = sorted(margins.items(), key=lambda kv: kv[1], reverse=True)

    locked = []
    locked_set = set()
    reach = [0] * n

    # 1) 严格正 margin，按 margin 降序
    for (a, b), m in edges:
        if m <= 0:
            continue
        _lock(reach, locked, locked_set, idx[a], idx[b], n)

    # 2) 零 margin / 未决对：按 op 索引序补全，避免成环
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

    # 3) 拓扑排序（确定性：与逐边 has_cycle 版本一致的出队顺序）
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
    assert len(res) == n, f"RP 未覆盖全部操作 {len(res)}/{n}"
    return res
