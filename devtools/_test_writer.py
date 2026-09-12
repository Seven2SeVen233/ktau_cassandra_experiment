"""离线测试 monitor.py 的 writer 漂移逻辑（mock 会话）。"""
import random
import sys
import time

sys.path.insert(0, "scripts")

import monitor


class FakeFuture:
    def __init__(self):
        pass

    def result(self):
        return None


class FakeSession:
    def __init__(self):
        self.writes = []
        self.prep = object()

    def prepare(self, q):
        return q

    def execute(self, *a):
        return None

    def execute_async(self, *a):
        self.writes.append(a)
        return FakeFuture()


class FakeTM:
    def __init__(self):
        self.all_op_ids = [str(i) for i in range(500)]
        self.ops = {str(i): {"ts": i} for i in range(500)}


class FakeCfg(dict):
    def __init__(self):
        super().__init__()
        self["model"] = {"N": 8}


def main():
    cfg = FakeCfg()
    tm = FakeTM()
    ses = FakeSession()
    # 加速：临时压低 RATE
    old_rate = monitor.RATE
    monitor.RATE = 1000
    try:
        lm = monitor.LiveMonitor(cfg, tm, 99999, ses, drift_max=0.6, threshold=0.05)
        lm.run_writer()
        resh = [a for a in ses.writes if a[0][3] != 99999]  # 非监控写
        total_writes = len(ses.writes)
        # 统计重排写：同一 (r,s) 被写两次以上 = 重排覆盖
        seq_by_rep = {}
        reshuffle_writes = 0
        writes_flat = [a[1] for a in ses.writes]
        for (trial, r, s, o) in writes_flat:
            k = (r, s)
            if k in seq_by_rep:
                reshuffle_writes += 1  # 同一 (r,s) 被写两次以上 = 重排覆盖
            seq_by_rep[k] = o
        # 重排后各副本窗口是否分歧（模拟 DB 状态：同 seq 只取最后一次写）
        last = {}
        for (trial, r, s, o) in writes_flat:
            last[(r, s)] = o
        by_rep = {}
        for (r, s), o in last.items():
            by_rep.setdefault(r, []).append((s, o))
        orders = []
        for r in range(8):
            w = sorted(by_rep.get(r, []), key=lambda t: -t[0])
            orders.append([o for _, o in w][:20])
        diff = sum(1 for i in range(8) for j in range(i + 1, 8)
                   if orders[i] != orders[j])
        print(f"总写数={total_writes} 重排覆盖写={reshuffle_writes}")
        print(f"8副本中序分歧副本对数={diff}/28")
        # τ̂
        from ranked_pairs import ranked_pairs
        from tau import tau, tauhat
        op_set = list(set(o for w in orders for o in w))
        sigma = ranked_pairs(orders, op_set)
        d = [tau(sigma, w) for w in orders]
        print(f"窗口M={len(op_set)} τ̂={tauhat(sum(d), 8, len(op_set)):.4f}")
    finally:
        monitor.RATE = old_rate


if __name__ == "__main__":
    main()
