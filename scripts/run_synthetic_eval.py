"""Synthetic experiment re-run (paper §6 Table 3 data source, with the effective
normalization τ̂ fix).

Covers:
- E1  causal decomposition validation (low/high, six strategies)
- E2  end-to-end comparison (high, six strategies)
- E3  Ranked Pairs vs exact Kemeny (M=4..8)
- E5  performance and scalability (M=5..100)
- E6a partition asymmetry (minority 10%..50%)

Generator: synthetic_model.SyntheticModel (N=10, K=8, pool ~500 operations)
Partition structure: low → 7/3 two partitions; high → 4/3/3 three partitions
(leader from the largest partition)
Output: results/synthetic/{e1_causal_decomp,e2_end2end,e3_rp_vs_kemeny,e5_perf,e6a_asymmetry}.csv
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

import common
from common import log
from baselines import all_strategies, merge_leader, merge_lww, merge_ranked_pairs, merge_vc
from kemeny_exact import kemeny_exact
from metrics import evaluate
from ranked_pairs import ranked_pairs
from synthetic_model import SyntheticModel, build_synthetic_scenario
from tau import tau

N_REPLICAS = 10
M_OPS = 24
TRIALS = 15
SEED = 42
JITTER = 60.0  # arrival-jitter magnitude (µs), same order as ts spacing → real
# disagreement between replicas on concurrent pairs

SYNTH_OUT = os.path.join(common.RESULTS, "synthetic")


def ensure_scenario(sm, seed, M, conflict, obs=0.9, noise=0.05, jitter=JITTER):
    return build_synthetic_scenario(sm, seed, M, conflict, obs=obs, noise=noise,
                                    jitter=jitter)


def run_trial(sm, seed, M, conflict, strategies):
    sc = ensure_scenario(sm, seed, M, conflict)
    out = {"trial": seed, "M": M, "conflict": conflict,
           "causal_density": sc.causal_density,
           "group_sizes": sc.conflict_groups}
    for name, fn in strategies.items():
        t0 = time.perf_counter()
        sigma, coverage, unresolved = fn(sc, seed=seed)
        dt_ms = (time.perf_counter() - t0) * 1000
        m = evaluate(sc, sigma, coverage, unresolved, name)
        m["time_ms"] = dt_ms
        out[name] = m
    return out, sc


def run_e1(sm):
    log.info("=== [synthetic] E1: causal decomposition validation ===")
    strategies = all_strategies()
    rows = []
    for conflict in ("low", "high"):
        for t in range(TRIALS):
            res, _ = run_trial(sm, SEED * 1000 + t, M_OPS, conflict, strategies)
            for name, m in res.items():
                if name in ("trial", "M", "conflict", "causal_density", "group_sizes"):
                    continue
                rows.append({
                    "conflict": conflict, "trial": res["trial"], "strategy": name,
                    "M": res["M"], "causal_density": res["causal_density"],
                    "tau_causal": m["tau_causal"], "tau_contested": m["tau_contested"],
                    "tauhat": m["tauhat"], "info_retention": m["info_retention"],
                })
    df = pd.DataFrame(rows)
    os.makedirs(SYNTH_OUT, exist_ok=True)
    df.to_csv(os.path.join(SYNTH_OUT, "e1_causal_decomp.csv"), index=False)
    summary = df.groupby(["conflict", "strategy"])[
        ["tau_causal", "tau_contested", "tauhat", "info_retention"]].mean().round(4)
    log.info("E1 summary:\n%s", summary.to_string())
    return df


def run_e2(sm):
    log.info("=== [synthetic] E2: end-to-end comparison (high conflict) ===")
    strategies = all_strategies()
    rows = []
    for t in range(TRIALS):
        res, _ = run_trial(sm, SEED * 5000 + t, M_OPS, "high", strategies)
        for name, m in res.items():
            if name in ("trial", "M", "conflict", "causal_density", "group_sizes"):
                continue
            rows.append({
                "trial": res["trial"], "strategy": name, "M": res["M"],
                "ops_retained": m["ops_retained"], "auto_coverage": m["auto_coverage"],
                "info_retention": m["info_retention"], "tau_causal": m["tau_causal"],
                "tau_contested": m["tau_contested"], "semantic_validity": m["semantic_validity"],
                "gini": m["gini"], "time_ms": m["time_ms"],
            })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(SYNTH_OUT, "e2_end2end.csv"), index=False)
    summary = df.groupby("strategy")[
        ["ops_retained", "auto_coverage", "info_retention", "tau_causal",
         "semantic_validity", "gini", "time_ms"]].mean().round(4)
    log.info("E2 summary:\n%s", summary.to_string())
    return df


def run_e3(sm):
    log.info("=== [synthetic] E3: Ranked Pairs vs exact Kemeny ===")
    rows = []
    for M in (4, 5, 6, 7, 8):
        for t in range(24):
            sc = ensure_scenario(sm, 7000 + M * 100 + t, M, "high")
            rp_sigma = ranked_pairs(sc.replica_logs, sc.D)
            rp_tau = sum(tau(rp_sigma, rl) for rl in sc.replica_logs)
            t0 = time.perf_counter()
            ex_sigma, ex_tau = kemeny_exact(sc.replica_logs, sc.D)
            ex_ms = (time.perf_counter() - t0) * 1000
            rows.append({
                "M": M, "trial": t, "rp_exact": (rp_tau == ex_tau),
                "rp_tau": rp_tau, "kemeny_tau": ex_tau,
                "excess_pct": (rp_tau / ex_tau - 1.0) * 100 if ex_tau else 0.0,
                "kemeny_ms": ex_ms,
            })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(SYNTH_OUT, "e3_rp_vs_kemeny.csv"), index=False)
    summary = df.groupby("M").agg(
        rp_exact_rate=("rp_exact", "mean"),
        avg_excess_pct=("excess_pct", "mean"),
        max_excess_pct=("excess_pct", "max"),
        kemeny_ms=("kemeny_ms", "mean")).round(4)
    log.info("E3 summary:\n%s", summary.to_string())
    return df


def run_e5(sm):
    log.info("=== [synthetic] E5: performance and scalability ===")
    rows = []
    for M in (5, 8, 10, 15, 20, 30, 50, 100):
        for t in range(12):
            sc = ensure_scenario(sm, 9000 + M * 10 + t, M, "high")
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
    df.to_csv(os.path.join(SYNTH_OUT, "e5_perf.csv"), index=False)
    summary = df.groupby("M")[
        ["tau_total_ms", "rp_ms", "lww_ms", "vc_ms", "merge_thr_ops_s"]].quantile(0.5).round(4)
    log.info("E5 summary(p50):\n%s", summary.to_string())
    return df


def run_e6a(sm):
    log.info("=== [synthetic] E6a: partition asymmetry ===")
    rows = []
    for frac in (0.10, 0.20, 0.30, 0.40, 0.50):
        minority_n = max(1, int(round(N_REPLICAS * frac)))
        for t in range(TRIALS):
            seed = SEED * 9000 + int(frac * 100) * 1000 + t
            sc = ensure_scenario(sm, seed, M_OPS, "high")
            reps = list(range(N_REPLICAS))
            random.Random(seed).shuffle(reps)
            sc.partitions = [reps[:N_REPLICAS - minority_n], reps[N_REPLICAS - minority_n:]]
            sc.leader_idx = sc.partitions[0][0]
            for name, fn in (("leader", merge_leader), ("lww", merge_lww),
                             ("ranked_pairs", merge_ranked_pairs)):
                sigma, cov, unr = fn(sc, seed=seed)
                m = evaluate(sc, sigma, cov, unr, name)
                rows.append({"minority_frac": frac, "trial": t, "strategy": name,
                             "ops_retained": m["ops_retained"],
                             "info_retention": m["info_retention"],
                             "tauhat": m["tauhat"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(SYNTH_OUT, "e6a_asymmetry.csv"), index=False)
    summary = df.groupby(["minority_frac", "strategy"])[
        ["ops_retained", "info_retention"]].mean().round(4)
    log.info("E6a summary:\n%s", summary.to_string())
    return df


def main():
    sm = SyntheticModel(N=N_REPLICAS, seed=SEED)
    log.info("synthetic model: %d ops, %d replicas, %d keys", len(sm.ops), sm.N, sm.K)
    run_e1(sm)
    run_e2(sm)
    run_e3(sm)
    run_e5(sm)
    run_e6a(sm)
    log.info("synthetic experiments done; results written to %s", SYNTH_OUT)


if __name__ == "__main__":
    main()
