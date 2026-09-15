# -*- coding: utf-8 -*-
"""E5 performance re-run under the dissemination premise (complete ballots,
CPU-only). Outputs results/synthetic_gossip/e5_complete.csv."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import common
from common import log
from baselines import merge_lww, merge_ranked_pairs, merge_vc
from ranked_pairs import ranked_pairs
from scenario_gen import Scenario, disseminate
from synthetic_model import SyntheticModel, build_synthetic_scenario
from tau import tau

OUT = os.path.join(common.RESULTS, "synthetic_gossip")
JITTER = 60.0


def complete_scenario(sc, seed):
    logs, cps, nab = disseminate(sc, seed, loss=0.0, jitter=JITTER)
    return Scenario(sc.ops, sc.D, logs, sc.causal_edges, sc.adj, cps, nab,
                    sc.partitions, sc.leader_idx, sc.skew, sc.N,
                    sc.causal_density, sc.conflict_groups)


def main():
    os.makedirs(OUT, exist_ok=True)
    sm = SyntheticModel(N=10, seed=42)
    rows = []
    for M in (5, 8, 10, 15, 20, 30, 50, 100):
        for t in range(12):
            seed = 9000 + M * 10 + t
            sc0 = build_synthetic_scenario(sm, seed, M, "high", obs=0.9, noise=0.05, jitter=JITTER)
            sc = complete_scenario(sc0, seed)
            t0 = time.perf_counter()
            total = sum(tau(merge_ranked_pairs(sc, seed=t)[0], rl) for rl in sc.replica_logs)
            tau_ms = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            sigma = ranked_pairs(sc.replica_logs, sc.D)
            rp_ms = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            merge_lww(sc, seed=t)
            lww_ms = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            merge_vc(sc, seed=t)
            vc_ms = (time.perf_counter() - t0) * 1000
            rows.append({"M": M, "trial": t, "tau_total_ms": tau_ms, "rp_ms": rp_ms,
                         "lww_ms": lww_ms, "vc_ms": vc_ms,
                         "merge_thr_ops_s": M / rp_ms * 1000 if rp_ms else 0.0,
                         "rp_tau": total})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e5_complete.csv"), index=False)
    summary = df.groupby("M")[["tau_total_ms", "rp_ms", "lww_ms", "vc_ms",
                               "merge_thr_ops_s"]].quantile(0.5).round(4)
    log.info("E5c summary(p50):\n%s", summary.to_string())
    print(summary.to_string())


if __name__ == "__main__":
    main()
