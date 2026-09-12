"""Phase 4: 性能/资源采集（宿主机侧）。

- docker stats 每 2s 采样 ktau 集群节点 CPU%/内存/网络 IO → results/perf_host.csv + ktau.perf_samples
- 客户端 CQL 往返延迟 p50/p95/p99（连接 cass-1 的 9042）
"""
import csv
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
from common import log

NODES = ["ktau-cass-1", "ktau-cass-2", "ktau-cass-3", "ktau-cass-4"]


def _parse_bytes(s):
    """将 docker stats 的字节串（如 1.2MB / 500kB / 100B）归一化为 MB。"""
    s = s.strip()
    try:
        if "GiB" in s:
            return float(s.replace("GiB", "")) * 1024
        if "MiB" in s:
            return float(s.replace("MiB", ""))
        if "kB" in s:
            return float(s.replace("kB", "")) / 1024
        if "MB" in s:
            return float(s.replace("MB", ""))
        if "B" in s:
            return float(s.replace("B", "")) / 1048576
        return float(s) / 1048576
    except Exception:
        return 0.0


def docker_stats_row():
    """一次 docker stats 采样 → {node: (cpu%, mem_mb, net_rx_mb, net_tx_mb)}"""
    out = subprocess.run(
        ["docker", "stats", "--no-stream", "--format",
         "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}"],
        capture_output=True, text=True, timeout=30)
    res = {}
    for line in out.stdout.strip().splitlines():
        parts = line.split("|")
        if len(parts) != 4:
            continue
        name, cpu, mem, net = parts
        cpu = float(cpu.replace("%", ""))
        try:
            mem_mb = float(mem.split("/")[0].replace("MiB", "").replace("GiB", "")) * (
                1024 if "GiB" in mem.split("/")[0] else 1)
        except Exception:
            mem_mb = 0.0
        rx = _parse_bytes(net.split("/")[0]) if "/" in net else 0.0
        tx = _parse_bytes(net.split("/")[1]) if "/" in net else 0.0
        res[name] = (cpu, mem_mb, rx, tx)
    return res


def cql_rtt(cfg, n=100):
    """客户端 → cass-1 的 CQL 往返延迟(ms)。"""
    cluster, session = common.get_session(cfg)
    try:
        lat = []
        for _ in range(n):
            t0 = time.perf_counter()
            session.execute("SELECT release_version FROM system.local")
            lat.append((time.perf_counter() - t0) * 1000)
    finally:
        cluster.shutdown()
    lat.sort()
    return (statistics.median(lat), lat[int(len(lat) * 0.95)], lat[int(len(lat) * 0.99)])


def main(duration_s=90, interval_s=2):
    cfg = common.load_config()
    out_csv = os.path.join(common.ensure_results(), "perf_host.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "node", "cpu_pct", "mem_mb", "net_rx", "net_tx"])
        t_end = time.time() + duration_s
        while time.time() < t_end:
            try:
                rows = docker_stats_row()
                for node, (cpu, mem, rx, tx) in rows.items():
                    w.writerow([time.time(), node, cpu, mem, rx, tx])
            except Exception as e:
                log.warning("docker stats error: %s", e)
            f.flush()
            time.sleep(interval_s)
    p50, p95, p99 = cql_rtt(cfg)
    log.info("CQL RTT ms p50=%.2f p95=%.2f p99=%.2f", p50, p95, p99)
    with open(os.path.join(common.RESULTS, "perf_cql_latency.csv"), "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([["metric", "ms"], ["p50", p50], ["p95", p95], ["p99", p99]])


if __name__ == "__main__":
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    main(duration, interval)
