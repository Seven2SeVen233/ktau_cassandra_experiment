"""Trace dissemination-premise re-run (option A consistency): E1/E2/E6a under
complete ballots.

Reuses run_experiments' scenario construction (sample_conflict_group, obs=0.9,
skew=500µs), then runs the six strategies after disseminate (complete ballots).
Outputs to results/trace_gossip/.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import common
from common import log
from baselines import all_strategies, merge_leader, merge_lww, merge_ranked_pairs
from metrics import evaluate
from scenario_gen import Scenario, TraceModel, disseminate, parse_bgl_file, sample_conflict_group
from stats import summarize, wilcoxon

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


def run_e1(tm, cfg):
    log.info("=== [trace-gossip] E1: causal decomposition (complete ballots) ===")
    strategies = all_strategies()
    rows = []
    for conflict in ("low", "high"):
        for t in range(cfg["model"]["trials"]):
            seed = cfg["model"]["seed"] * 1000 + t
            sc = complete_scenario(ensure_scenario(tm, seed, cfg["model"]["M"], conflict, cfg), seed)
            for name, fn in strategies.items():
                sigma, cov, unr = fn(sc, seed=seed)
                m = evaluate(sc, sigma, cov, unr, name)
                rows.append({"conflict": conflict, "trial": t, "strategy": name,
                             "M": cfg["model"]["M"], "causal_density": sc.causal_density,
                             "tau_causal": m["tau_causal"], "tau_contested": m["tau_contested"],
                             "tauhat": m["tauhat"], "info_retention": m["info_retention"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e1_complete.csv"), index=False)
    log.info("E1 summary:\n%s", df.groupby(["conflict", "strategy"])[
        ["tau_causal", "tau_contested", "tauhat", "info_retention"]].mean().round(4).to_string())
    return df


def run_e2(tm, cfg):
    log.info("=== [trace-gossip] E2: end-to-end (complete ballots, high conflict) ===")
    strategies = all_strategies()
    rows = []
    t = cfg["model"]["seed"] * 5000
    for _ in range(cfg["model"]["trials"]):
        t += 1
        sc = complete_scenario(ensure_scenario(tm, t, cfg["model"]["M"], "high", cfg), t)
        for name, fn in strategies.items():
            import time as _t

            t0 = _t.perf_counter()
            sigma, cov, unr = fn(sc, seed=t)
            dt_ms = (_t.perf_counter() - t0) * 1000
            m = evaluate(sc, sigma, cov, unr, name)
            m["time_ms"] = dt_ms
            rows.append({"trial": _, "strategy": name, "M": cfg["model"]["M"],
                         "ops_retained": m["ops_retained"], "auto_coverage": m["auto_coverage"],
                         "info_retention": m["info_retention"], "tau_causal": m["tau_causal"],
                         "tau_contested": m["tau_contested"], "semantic_validity": m["semantic_validity"],
                         "gini": m["gini"], "time_ms": m["time_ms"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e2_complete.csv"), index=False)
    log.info("E2 summary:\n%s", df.groupby("strategy")[
        ["ops_retained", "auto_coverage", "info_retention", "tau_causal",
         "semantic_validity", "gini", "time_ms"]].mean().round(4).to_string())
    return df


def run_e6a(tm, cfg):
    log.info("=== [trace-gossip] E6a: partition asymmetry (complete ballots) ===")
    rows = []
    N = cfg["model"]["N"]
    t = cfg["model"]["seed"] * 9000
    for frac in (0.10, 0.20, 0.30, 0.40, 0.50):
        minority_n = max(1, int(round(N * frac)))
        for _ in range(15):
            t += 1
            sc = complete_scenario(ensure_scenario(tm, t, cfg["model"]["M"], "high", cfg), t)
            reps = list(range(N))
            random.Random(t).shuffle(reps)
            sc.partitions = [reps[:N - minority_n], reps[N - minority_n:]]
            sc.leader_idx = sc.partitions[0][0]
            for name, fn in (("leader", merge_leader), ("lww", merge_lww),
                             ("ranked_pairs", merge_ranked_pairs)):
                sigma, cov, unr = fn(sc, seed=t)
                m = evaluate(sc, sigma, cov, unr, name)
                rows.append({"minority_frac": frac, "trial": _, "strategy": name,
                             "ops_retained": m["ops_retained"],
                             "info_retention": m["info_retention"],
                             "tauhat": m["tauhat"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e6a_complete.csv"), index=False)
    log.info("E6a summary:\n%s", df.groupby(["minority_frac", "strategy"])[
        ["ops_retained", "info_retention"]].mean().round(4).to_string())
    return df


def main():
    os.makedirs(OUT, exist_ok=True)
    cfg = common.load_config()
    ops_by_node = parse_bgl_file(cfg["data"]["raw_file"], max_ops=cfg["data"]["max_ops"])
    tm = TraceModel(ops_by_node, cfg["model"]["N"])
    log.info("trace model: %d ops, %d replicas", len(tm.ops), tm.N)

    e1 = run_e1(tm, cfg)
    e2 = run_e2(tm, cfg)
    e6a = run_e6a(tm, cfg)

    exp1 = {"name": "E1", "group_cols": ["conflict"],
            "metrics": ["tau_causal", "tau_contested", "tauhat", "info_retention"]}
    exp2 = {"name": "E2", "group_cols": [],
            "metrics": ["ops_retained", "auto_coverage", "info_retention", "tau_causal",
                        "tau_contested", "semantic_validity", "gini", "time_ms"]}
    exp6 = {"name": "E6a", "group_cols": ["minority_frac"],
            "metrics": ["ops_retained", "info_retention", "tauhat"]}
    sums, wils = [], []
    for exp, df in ((exp1, e1), (exp2, e2), (exp6, e6a)):
        sums.append(summarize(df, exp["group_cols"], exp["metrics"]))
        wils.append(wilcoxon(df, exp["group_cols"]))
    pd.concat(sums, ignore_index=True).to_csv(
        os.path.join(OUT, "statistics_complete_summary.csv"), index=False)
    pd.concat(wils, ignore_index=True).to_csv(
        os.path.join(OUT, "statistics_complete_wilcoxon.csv"), index=False)
    log.info("trace dissemination re-run done; results written to %s", OUT)


if __name__ == "__main__":
    main()
