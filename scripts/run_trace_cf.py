# -*- coding: utf-8 -*-
"""Trace causally constrained re-run (dissemination dropped): partially observed
ballots + CF-RP, outputs to results/trace_cf/.

Reuses run_trace_gossip's scenario construction (sample_conflict_group,
obs=0.9, skew=500µs), but no longer calls disseminate -- the ballots are simply
each replica's partially observed log.
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import common
from common import log
from baselines import (all_strategies, merge_leader, merge_lww, merge_ranked_pairs,
                       merge_ranked_pairs_unconstrained)
from kemeny_exact import count_causal_violations, kemeny_exact_constrained
from metrics import evaluate
from scenario_gen import TraceModel, parse_bgl_file, sample_conflict_group
from stats import summarize, wilcoxon

OUT = os.path.join(common.RESULTS, "trace_cf")


def ensure_scenario(tm, seed, M, conflict, cfg):
    m = cfg["model"]
    return sample_conflict_group(tm, seed, M, conflict,
                                 obs=m.get("obs", 0.9), noise=m.get("noise", 0.05),
                                 skew_us=m.get("skew_us", 500.0))


def run_e1(tm, cfg):
    log.info("=== [trace-cf] E1: causal decomposition (partial observation) ===")
    strategies = all_strategies()
    rows = []
    for conflict in ("low", "high"):
        for t in range(cfg["model"]["trials"]):
            seed = cfg["model"]["seed"] * 1000 + t
            sc = ensure_scenario(tm, seed, cfg["model"]["M"], conflict, cfg)
            for name, fn in strategies.items():
                sigma, cov, unr = fn(sc, seed=seed)
                m = evaluate(sc, sigma, cov, unr, name)
                rows.append({"conflict": conflict, "trial": t, "strategy": name,
                             "tau_causal": m["tau_causal"], "tau_contested": m["tau_contested"],
                             "info_retention": m["info_retention"]})
            su, _, _ = merge_ranked_pairs_unconstrained(sc, seed=seed)
            mu = evaluate(sc, su, 1.0, 0, "rp_unconstrained")
            rows.append({"conflict": conflict, "trial": t, "strategy": "rp_unconstrained",
                         "tau_causal": mu["tau_causal"], "tau_contested": mu["tau_contested"],
                         "info_retention": mu["info_retention"],
                         "repair_swaps": count_causal_violations(su, sc.causal_edges)})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e1.csv"), index=False)
    log.info("E1 summary:\n%s", df.groupby(["conflict", "strategy"])[
        ["tau_causal", "tau_contested", "info_retention"]].mean().round(3).to_string())
    return df


def run_e2(tm, cfg):
    log.info("=== [trace-cf] E2: end-to-end (high conflict, partial observation) ===")
    strategies = all_strategies()
    rows = []
    t = cfg["model"]["seed"] * 5000
    for _ in range(cfg["model"]["trials"]):
        t += 1
        sc = ensure_scenario(tm, t, cfg["model"]["M"], "high", cfg)
        for name, fn in strategies.items():
            t0 = time.perf_counter()
            sigma, cov, unr = fn(sc, seed=t)
            dt_ms = (time.perf_counter() - t0) * 1000
            m = evaluate(sc, sigma, cov, unr, name)
            rows.append({"trial": _, "strategy": name,
                         "ops_retained": m["ops_retained"], "auto_coverage": m["auto_coverage"],
                         "info_retention": m["info_retention"], "tau_causal": m["tau_causal"],
                         "tau_contested": m["tau_contested"], "semantic_validity": m["semantic_validity"],
                         "gini": m["gini"], "time_ms": dt_ms})
        su, _, _ = merge_ranked_pairs_unconstrained(sc, seed=t)
        mu = evaluate(sc, su, 1.0, 0, "rp_unconstrained")
        rows.append({"trial": _, "strategy": "rp_unconstrained",
                     "ops_retained": mu["ops_retained"], "auto_coverage": mu["auto_coverage"],
                     "info_retention": mu["info_retention"], "tau_causal": mu["tau_causal"],
                     "tau_contested": mu["tau_contested"], "semantic_validity": mu["semantic_validity"],
                     "gini": mu["gini"], "time_ms": 0.0,
                     "repair_swaps": count_causal_violations(su, sc.causal_edges)})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e2.csv"), index=False)
    log.info("E2 summary:\n%s", df.groupby("strategy")[
        ["ops_retained", "auto_coverage", "info_retention", "tau_causal",
         "semantic_validity", "gini", "time_ms"]].mean().round(4).to_string())
    return df


def run_e3(tm, cfg):
    log.info("=== [trace-cf] E3: CF-RP vs constrained exact Kemeny ===")
    rows = []
    for M in (4, 5, 6, 7, 8):
        for t in range(24):
            sc = ensure_scenario(tm, 7000 + M * 100 + t, M, "high", cfg)
            cf = merge_ranked_pairs(sc, seed=t)[0]
            from tau import tau as _tau
            cf_tau = sum(_tau(cf, rl) for rl in sc.replica_logs)
            t0 = time.perf_counter()
            cx, cx_tau = kemeny_exact_constrained(sc.replica_logs, sc.D, sc.causal_edges)
            cx_ms = (time.perf_counter() - t0) * 1000
            su, _, _ = merge_ranked_pairs_unconstrained(sc, seed=t)
            u_tau = sum(_tau(su, rl) for rl in sc.replica_logs)
            rows.append({"M": M, "trial": t, "rp_exact": (cf_tau == cx_tau),
                         "excess_pct": (cf_tau / cx_tau - 1.0) * 100 if cx_tau else 0.0,
                         "rp_unc_causal_viol": count_causal_violations(su, sc.causal_edges),
                         "constrained_ms": cx_ms})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e3.csv"), index=False)
    log.info("E3 summary:\n%s", df.groupby("M").agg(
        rp_exact_rate=("rp_exact", "mean"),
        avg_excess_pct=("excess_pct", "mean"),
        viol_frac=("rp_unc_causal_viol", lambda s: (s > 0).mean())).round(4).to_string())
    return df


def run_e6a(tm, cfg):
    log.info("=== [trace-cf] E6a: partition asymmetry (partial observation) ===")
    rows = []
    N = cfg["model"]["N"]
    t = cfg["model"]["seed"] * 9000
    for frac in (0.10, 0.20, 0.30, 0.40, 0.50):
        minority_n = max(1, int(round(N * frac)))
        for _ in range(15):
            t += 1
            sc = ensure_scenario(tm, t, cfg["model"]["M"], "high", cfg)
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
                             "info_retention": m["info_retention"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e6a.csv"), index=False)
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
    e3 = run_e3(tm, cfg)
    e6a = run_e6a(tm, cfg)

    sums, wils = [], []
    for exp, df in (
        ({"name": "E1", "group_cols": ["conflict"],
          "metrics": ["tau_causal", "tau_contested", "info_retention"]}, e1),
        ({"name": "E2", "group_cols": [],
          "metrics": ["ops_retained", "auto_coverage", "info_retention", "tau_causal",
                      "tau_contested", "semantic_validity", "gini", "time_ms"]}, e2),
        ({"name": "E6a", "group_cols": ["minority_frac"],
          "metrics": ["ops_retained", "info_retention"]}, e6a),
    ):
        sums.append(summarize(df, exp["group_cols"], exp["metrics"]))
        wils.append(wilcoxon(df, exp["group_cols"]))
    pd.concat(sums, ignore_index=True).to_csv(
        os.path.join(OUT, "statistics_summary.csv"), index=False)
    pd.concat(wils, ignore_index=True).to_csv(
        os.path.join(OUT, "statistics_wilcoxon.csv"), index=False)
    log.info("trace causally constrained re-run done; results written to %s", OUT)


if __name__ == "__main__":
    main()
