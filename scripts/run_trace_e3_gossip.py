# -*- coding: utf-8 -*-
"""E3 re-run under the trace dissemination premise (RP vs exact Kemeny, complete
ballots). Outputs results/trace_gossip/e3_complete.csv."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import common
from common import log
from kemeny_exact import kemeny_exact
from ranked_pairs import ranked_pairs
from scenario_gen import Scenario, TraceModel, disseminate, parse_bgl_file, sample_conflict_group
from tau import positions, tau

OUT = os.path.join(common.RESULTS, "trace_gossip")


def ensure_scenario(tm, seed, M, conflict, cfg):
    m = cfg["model"]
    return sample_conflict_group(tm, seed, M, conflict,
                                 obs=m.get("obs", 0.9), noise=m.get("noise", 0.05),
                                 skew_us=m.get("skew_us", 500.0))


def complete_scenario(sc, seed):
    logs, cps, nab = disseminate(sc, seed, loss=0.0)
    return Scenario(sc.ops, sc.D, logs, sc.causal_edges, sc.adj, cps, nab,
                    sc.partitions, sc.leader_idx, sc.skew, sc.N,
                    sc.causal_density, sc.conflict_groups)


def violated_pairs(order, causal_pairs):
    pos = positions(order)
    return [(a, b) for a, b in causal_pairs if pos[a] > pos[b]]


def main():
    os.makedirs(OUT, exist_ok=True)
    cfg = common.load_config()
    ops_by_node = parse_bgl_file(cfg["data"]["raw_file"], max_ops=cfg["data"]["max_ops"])
    tm = TraceModel(ops_by_node, cfg["model"]["N"])
    rows = []
    for M in (4, 5, 6, 7, 8):
        for t in range(24):
            seed = 7000 + M * 100 + t
            sc = complete_scenario(ensure_scenario(tm, seed, M, "high", cfg), seed)
            rp_sigma = ranked_pairs(sc.replica_logs, sc.D)
            rp_tau = sum(tau(rp_sigma, rl) for rl in sc.replica_logs)
            t0 = time.perf_counter()
            ex_sigma, ex_tau = kemeny_exact(sc.replica_logs, sc.D)
            ex_ms = (time.perf_counter() - t0) * 1000
            rows.append({"M": M, "trial": t, "rp_exact": (rp_tau == ex_tau),
                         "rp_tau": rp_tau, "kemeny_tau": ex_tau,
                         "excess_pct": (rp_tau / ex_tau - 1.0) * 100 if ex_tau else 0.0,
                         "kemeny_ms": ex_ms,
                         "rp_violations": len(violated_pairs(rp_sigma, sc.causal_pairs)),
                         "kemeny_violations": len(violated_pairs(ex_sigma, sc.causal_pairs)),
                         "n_causal": len(sc.causal_pairs)})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e3_complete.csv"), index=False)
    summary = df.groupby("M").agg(
        rp_exact_rate=("rp_exact", "mean"), avg_excess_pct=("excess_pct", "mean"),
        rp_viol=("rp_violations", "sum"), km_viol=("kemeny_violations", "sum"),
        n_causal=("n_causal", "mean")).round(4)
    log.info("trace E3c summary:\n%s", summary.to_string())
    print(summary.to_string())


if __name__ == "__main__":
    main()
