"""Phase 3: experiment execution E1–E6a (core validation).

E1  causal decomposition validation (low/high conflict, six strategies; includes
    τcausal detection under LWW with large clock skew)
E1b counterexample reproduction from paper §5.3.3 (deterministic demonstration of
    exact τ counting when consistent constraints are violated)
E2  end-to-end comparison (high conflict, all strategies, metric table)
E3  Ranked Pairs vs exact Kemeny (M=4..8)
E4  real-time τ monitoring (Cassandra live storage: steady → divergence → heal +
    sensitivity sweep)
E5  performance and scalability (M=5..100: τ/RP/LWW/VC runtime + merge throughput)
E6a partition asymmetry (minority 10%..50%)
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
from baselines import all_strategies, merge_ranked_pairs
from kemeny_exact import kemeny_exact
from metrics import evaluate
from ranked_pairs import ranked_pairs
from scenario_gen import TraceModel, parse_bgl_file, sample_conflict_group
from tau import tau, tauhat


def ensure_scenario(tm, seed, M, conflict, cfg, skew_scale=1.0):
    m = cfg["model"]
    sc = sample_conflict_group(tm, seed, M, conflict,
                               obs=m.get("obs", 0.9), noise=m.get("noise", 0.05),
                               skew_us=m.get("skew_us", 500.0))
    if skew_scale != 1.0:
        sc.skew = {r: v * skew_scale for r, v in sc.skew.items()}
    return sc


def run_trial(tm, seed, M, conflict, strategies, cfg, skew_scale=1.0):
    sc = ensure_scenario(tm, seed, M, conflict, cfg, skew_scale)
    out = {"trial": seed, "M": M, "conflict": conflict,
           "causal_density": sc.causal_density,
           "group_sizes": sc.conflict_groups}
    for name, fn in strategies.items():
        t0 = time.perf_counter()
        sigma, coverage, unresolved = fn(sc, seed=seed)
        dt_ms = (time.perf_counter() - t0) * 1000
        m = evaluate(sc, sigma, coverage, unresolved, name)
        m["time_ms"] = dt_ms
        m["causal_density"] = sc.causal_density
        out[name] = m
    return out, sc


def run_e1(tm, cfg):
    log.info("=== E1: causal decomposition validation ===")
    strategies = all_strategies()
    rows = []
    for conflict in ("low", "high"):
        for t in range(cfg["model"]["trials"]):
            res, _ = run_trial(tm, cfg["model"]["seed"] * 1000 + t,
                               cfg["model"]["M"], conflict, strategies, cfg)
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
    common.ensure_results()
    df.to_csv(os.path.join(common.RESULTS, "e1_causal_decomp.csv"), index=False)
    summary = df.groupby(["conflict", "strategy"])[
        ["tau_causal", "tau_contested", "tauhat", "info_retention"]].mean().round(4)
    log.info("E1 summary:\n%s", summary.to_string())
    return df


def run_e1b(tm):
    """Paper §5.3.3 counterexample: exact τ counting when a consistent constraint
    is violated (deterministic)."""
    log.info("=== E1b: paper counterexample reproduction (τ detects causal disorder) ===")
    ops = {0: {"ts": 1.0, "replica": 0, "issuer": 0, "otype": "incr", "key": 0},
           1: {"ts": 2.0, "replica": 0, "issuer": 0, "otype": "incr", "key": 0},
           2: {"ts": 3.0, "replica": 0, "issuer": 0, "otype": "incr", "key": 0},
           3: {"ts": 4.0, "replica": 0, "issuer": 0, "otype": "incr", "key": 0}}
    # 3 replicas, a=0 ≻ b=1 consistent (every replica containing both has a before b)
    replica_logs = [[0, 1, 2, 3], [0, 1, 2, 3], [0, 1, 2, 3]]
    causal_pairs = [(0, 1)]
    n_ab = {(0, 1): 3}
    bad_order = [1, 2, 3, 0]  # bad order that local search may produce: b ≻ z1 ≻ z2 ≻ a
    from tau import tau_causal_order, tauhat

    t_causal = tau_causal_order(bad_order, causal_pairs, n_ab)
    t_total = sum(tau(bad_order, rl) for rl in replica_logs)
    log.info("counterexample: τ_causal=%s (expected 3=n_ab), τ_total=%s, tauhat=%s",
             t_causal, t_total, round(tauhat(t_total, 3, 4), 4))
    rows = [{"test": "counterexample", "tau_causal": t_causal,
             "tau_total": t_total, "tauhat": tauhat(t_total, 3, 4)}]
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(common.RESULTS, "e1b_counterexample.csv"), index=False)
    return df


def run_e2(tm, cfg):
    log.info("=== E2: end-to-end comparison (high conflict) ===")
    strategies = all_strategies()
    rows = []
    t = cfg["model"]["seed"] * 5000
    for _ in range(cfg["model"]["trials"]):
        t += 1
        res, _ = run_trial(tm, t, cfg["model"]["M"], "high", strategies, cfg)
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
    df.to_csv(os.path.join(common.RESULTS, "e2_end2end.csv"), index=False)
    summary = df.groupby("strategy")[
        ["ops_retained", "auto_coverage", "info_retention", "tau_causal",
         "semantic_validity", "gini", "time_ms"]].mean().round(4)
    log.info("E2 summary:\n%s", summary.to_string())
    return df


def run_e3(tm, cfg):
    log.info("=== E3: Ranked Pairs vs exact Kemeny ===")
    rows = []
    for M in (4, 5, 6, 7, 8):
        for t in range(24):
            sc = ensure_scenario(tm, 7000 + M * 100 + t, M, "high", cfg)
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
    df.to_csv(os.path.join(common.RESULTS, "e3_rp_vs_kemeny.csv"), index=False)
    summary = df.groupby("M").agg(
        rp_exact_rate=("rp_exact", "mean"),
        avg_excess_pct=("excess_pct", "mean"),
        max_excess_pct=("excess_pct", "max"),
        kemeny_ms=("kemeny_ms", "mean")).round(4)
    log.info("E3 summary:\n%s", summary.to_string())
    return df


def run_e5(tm, cfg):
    log.info("=== E5: performance and scalability ===")
    rows = []
    N = cfg["model"]["N"]
    for M in (5, 8, 10, 15, 20, 30, 50, 100):
        for t in range(12):
            sc = ensure_scenario(tm, 9000 + M * 10 + t, M, "high", cfg)
            # τ_total runtime
            t0 = time.perf_counter()
            total = sum(tau(merge_ranked_pairs(sc, seed=t)[0], rl) for rl in sc.replica_logs)
            tau_ms = (time.perf_counter() - t0) * 1000
            # RP runtime
            t0 = time.perf_counter()
            sigma = ranked_pairs(sc.replica_logs, sc.D)
            rp_ms = (time.perf_counter() - t0) * 1000
            # LWW runtime
            from baselines import merge_lww
            t0 = time.perf_counter()
            merge_lww(sc, seed=t)
            lww_ms = (time.perf_counter() - t0) * 1000
            from baselines import merge_vc
            t0 = time.perf_counter()
            merge_vc(sc, seed=t)
            vc_ms = (time.perf_counter() - t0) * 1000
            rows.append({"M": M, "trial": t, "tau_total_ms": tau_ms, "rp_ms": rp_ms,
                         "lww_ms": lww_ms, "vc_ms": vc_ms,
                         "merge_thr_ops_s": M / rp_ms * 1000 if rp_ms else 0.0,
                         "rp_tau": total})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(common.RESULTS, "e5_perf.csv"), index=False)
    summary = df.groupby("M")[
        ["tau_total_ms", "rp_ms", "lww_ms", "vc_ms", "merge_thr_ops_s"]].quantile(0.5).round(4)
    log.info("E5 summary(p50):\n%s", summary.to_string())
    return df


def run_e6a(tm, cfg):
    log.info("=== E6a: partition asymmetry ===")
    rows = []
    N = cfg["model"]["N"]
    t = cfg["model"]["seed"] * 9000
    for frac in (0.10, 0.20, 0.30, 0.40, 0.50):
        minority_n = max(1, int(round(N * frac)))
        for _ in range(15):
            t += 1
            sc = ensure_scenario(tm, t, cfg["model"]["M"], "high", cfg)
            # Override partitions: majority = N - minority_n
            reps = list(range(N))
            random.Random(t).shuffle(reps)
            sc.partitions = [reps[:N - minority_n], reps[N - minority_n:]]
            sc.leader_idx = sc.partitions[0][0]
            from baselines import merge_leader, merge_lww, merge_ranked_pairs

            for name, fn in (("leader", merge_leader), ("lww", merge_lww),
                             ("ranked_pairs", merge_ranked_pairs)):
                sigma, cov, unr = fn(sc, seed=t)
                m = evaluate(sc, sigma, cov, unr, name)
                rows.append({"minority_frac": frac, "trial": _, "strategy": name,
                             "ops_retained": m["ops_retained"],
                             "info_retention": m["info_retention"],
                             "tauhat": m["tauhat"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(common.RESULTS, "e6a_asymmetry.csv"), index=False)
    summary = df.groupby(["minority_frac", "strategy"])[
        ["ops_retained", "info_retention"]].mean().round(4)
    log.info("E6a summary:\n%s", summary.to_string())
    return df


def main():
    cfg = common.load_config()
    ds = cfg["data"]
    ops_by_node = parse_bgl_file(ds["raw_file"], max_ops=ds["max_ops"])
    tm = TraceModel(ops_by_node, cfg["model"]["N"])
    log.info("trace model: %d ops, %d replicas", len(tm.ops), tm.N)

    run_e1(tm, cfg)
    run_e1b(tm)
    run_e2(tm, cfg)
    run_e3(tm, cfg)
    run_e5(tm, cfg)
    run_e6a(tm, cfg)
    log.info("core experiments done; results written to %s", common.RESULTS)


if __name__ == "__main__":
    main()
