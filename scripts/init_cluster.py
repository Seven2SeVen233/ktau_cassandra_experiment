"""Phase 0: initialize the keyspace and all data tables, and verify cluster state."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
from common import log


def build_ddl(ks, rf):
    """Build DDL from the configured keyspace / replication_factor."""
    return [
        f"CREATE KEYSPACE IF NOT EXISTS {ks} WITH replication = "
        f"{{'class': 'SimpleStrategy', 'replication_factor': {rf}}}",
        f"""
        CREATE TABLE IF NOT EXISTS {ks}.trace_ops (
            dataset text, op_id bigint, ts double, node text, replica int,
            otype text, key_id int, level text, label text,
            PRIMARY KEY (dataset, op_id))
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {ks}.trace_raw (
            dataset text, line_no int, line text,
            PRIMARY KEY (dataset, line_no))
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {ks}.replica_logs (
            trial int, replica int, seq int, op_id bigint,
            PRIMARY KEY ((trial, replica), seq))
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {ks}.merge_results (
            trial int, strategy text, M int, ops_retained double,
            auto_coverage double, unresolved int, tau_total double,
            tau_causal double, tau_contested double, tauhat double,
            info_retention double, semantic_validity double, gini double,
            time_ms double, conflict text, sigma list<bigint>,
            PRIMARY KEY (trial, strategy))
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {ks}.monitor_series (
            trial int, sample_ts double, tauhat double, gini double,
            maxlag int, ops_total int, alert int, phase text,
            PRIMARY KEY (trial, sample_ts))
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {ks}.perf_samples (
            phase text, ts double, node text, cpu_pct double, mem_mb double,
            net_rx double, net_tx double,
            PRIMARY KEY (phase, ts, node))
        """,
    ]


def main():
    cfg = common.load_config()
    ks = cfg["cluster"]["keyspace"]
    rf = cfg["cluster"]["rf"]
    ddl = build_ddl(ks, rf)
    cluster, session = common.get_session(cfg)
    try:
        for stmt in ddl:
            session.execute(stmt)
        # Verification
        rows = session.execute("SELECT release_version FROM system.local")
        log.info("Cassandra release_version = %s", rows.one()[0])
        keys = session.execute("SELECT keyspace_name FROM system_schema.keyspaces "
                               "WHERE keyspace_name = %s", (ks,)).all()
        log.info("keyspace %s ready, tables=%d", ks, len(ddl) - 1)
    finally:
        cluster.shutdown()


if __name__ == "__main__":
    main()
