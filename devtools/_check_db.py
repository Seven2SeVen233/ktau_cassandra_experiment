"""检查 Cassandra 中 E4 trial 各副本窗口的实际状态。"""
import sys

sys.path.insert(0, "scripts")

import common
from ranked_pairs import ranked_pairs
from tau import tau, tauhat


def main():
    cfg = common.load_config()
    cluster, session = common.get_session(cfg)
    try:
        sel = session.prepare(
            "SELECT op_id FROM ktau.replica_logs WHERE trial=? AND replica=? "
            "ORDER BY seq DESC LIMIT 20")
        N = cfg["model"]["N"]
        for trial in (20000, 20003):
            print(f"=== trial {trial} ===")
            windows = []
            for r in range(N):
                rows = session.execute(sel, (trial, r)).all()
                windows.append([row[0] for row in rows])
                print(f"  副本{r}: {windows[-1][:6]}... (共{len(windows[-1])})")
            op_set = list(set(o for w in windows for o in w))
            print(f"  op_set大小={len(op_set)}")
            if len(op_set) >= 2:
                sigma = ranked_pairs(windows, op_set)
                d = [tau(sigma, w) for w in windows]
                print(f"  τ̂={tauhat(sum(d), N, len(op_set)):.4f} 每副本τ={[round(x,1) for x in d]}")
    finally:
        cluster.shutdown()


if __name__ == "__main__":
    main()
