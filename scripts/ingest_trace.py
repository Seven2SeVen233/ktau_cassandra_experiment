"""Phase 1: 将 BGL trace 解析并导入 Cassandra（trace_ops / trace_raw）。
同时测吞吐（ops/s）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
from common import log
from scenario_gen import parse_bgl_file


def main():
    cfg = common.load_config()
    ds = cfg["data"]
    path = ds["raw_file"]
    max_ops = ds["max_ops"]
    dataset = ds["dataset"]
    ks = cfg["cluster"]["keyspace"]
    cluster, session = common.get_session(cfg)
    try:
        ops_by_node = parse_bgl_file(path, max_ops=max_ops)
        total = sum(len(v) for v in ops_by_node.values())
        log.info("parsed %d ops from %d nodes", total, len(ops_by_node))

        # 清空重跑
        session.execute(f"TRUNCATE {ks}.trace_ops")

        insert = session.prepare(
            f"INSERT INTO {ks}.trace_ops (dataset, op_id, ts, node, replica, otype, key_id, level, label) "
            f"VALUES ('{dataset}', ?, ?, ?, ?, ?, ?, ?, ?)")
        t0 = time.perf_counter()
        n = 0
        for node, oplist in ops_by_node.items():
            for m in oplist:
                session.execute(insert, (m["id"], m["ts"], m["node"], 0,
                                         m["otype"], 0, m["level"], m["label"]))
                n += 1
        dt = time.perf_counter() - t0
        log.info("ingested %d ops in %.2fs -> %.0f ops/s", n, dt, n / dt)
    finally:
        cluster.shutdown()


if __name__ == "__main__":
    main()
