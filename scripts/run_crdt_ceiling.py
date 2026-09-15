# -*- coding: utf-8 -*-
"""§6.5 CRDT ceiling experiment (complete ballots under the dissemination
premise): non-commutative operation ratio sweep.

- noncomm ratio x ∈ {0, 0.1, ..., 1.0}: incr = 1−x, set = x/2, cas = x/2
- 15 trials per x (high conflict, complete ballots after dissemination)
- strategies: crdt_pure / crdt_lww / lww / ranked_pairs / vc
- metrics: semantic_validity, auto_coverage, info_retention
Output: results/synthetic_gossip/e3_crdt_ceiling.csv
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import common
from common import log
from baselines import all_strategies
from metrics import evaluate
from scenario_gen import Scenario, disseminate
from synthetic_model import SyntheticModel, build_synthetic_scenario

OUT = os.path.join(common.RESULTS, "synthetic_gossip")
N = 10
M = 24
TRIALS = 15
SEED = 42
JITTER = 60.0
NONCOMM = [round(x, 1) for x in [i / 10 for i in range(11)]]


def complete_scenario(sc, seed):
    logs, cps, nab = disseminate(sc, seed, loss=0.0, jitter=JITTER)
    return Scenario(sc.ops, sc.D, logs, sc.causal_edges, sc.adj, cps, nab,
                    sc.partitions, sc.leader_idx, sc.skew, sc.N,
                    sc.causal_density, sc.conflict_groups)


def main():
    os.makedirs(OUT, exist_ok=True)
    strategies = all_strategies()
    rows = []
    for x in NONCOMM:
        sm = SyntheticModel(N=N, K=8, seed=SEED, incr_ratio=1.0 - x,
                            set_ratio=x / 2)
        for t in range(TRIALS):
            seed = SEED * 15000 + int(x * 10) * 1000 + t
            sc0 = build_synthetic_scenario(sm, seed, M, "high", obs=0.9, noise=0.05,
                                           jitter=JITTER)
            sc = complete_scenario(sc0, seed)
            for name, fn in strategies.items():
                sigma, cov, unr = fn(sc, seed=seed)
                m = evaluate(sc, sigma, cov, unr, name)
                rows.append({"noncomm": x, "trial": t, "strategy": name,
                             "semantic_validity": m["semantic_validity"],
                             "auto_coverage": m["auto_coverage"],
                             "info_retention": m["info_retention"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e3_crdt_ceiling.csv"), index=False)
    summary = df.groupby(["noncomm", "strategy"])[
        ["semantic_validity", "auto_coverage", "info_retention"]].mean().round(4)
    log.info("CRDT ceiling summary:\n%s", summary.to_string())
    print(summary.to_string())


if __name__ == "__main__":
    main()
