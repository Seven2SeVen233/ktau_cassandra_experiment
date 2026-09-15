# -*- coding: utf-8 -*-
"""Synthetic experiment re-run (causally constrained model: partially observed
ballots + CF-RP, no dissemination phase).

Consistent with the revised paper model:
- ballots = each replica's partially observed log (obs = 0.9, no dissemination)
- τ-minimization strategy = causally constrained Ranked Pairs (CF-RP, see
  ranked_pairs.ranked_pairs_causal)
- additionally reports the "detect-and-repair" measure: causal-pair violations of
  plain RP (no causal pre-locking) = repair cost

Covers: e1 causal decomposition / e2 end-to-end / e3 CF-RP vs constrained exact
Kemeny / e5 performance / e6a partition asymmetry / crdt ceiling. Outputs to
results/synthetic_cf/.
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import common
from common import log
from baselines import (all_strategies, merge_lww, merge_ranked_pairs,
                       merge_ranked_pairs_unconstrained, merge_vc, merge_leader)
from kemeny_exact import (count_causal_violations, kemeny_exact,
                          kemeny_exact_constrained)
from metrics import evaluate
from synthetic_model import SyntheticModel, build_synthetic_scenario
from tau import tau

N_REPLICAS = 10
M_OPS = 24
TRIALS = 15
SEED = 42
JITTER = 60.0
OBS = 0.9
NOISE = 0.05

SYNTH_OUT = os.path.join(common.RESULTS, "synthetic_cf")


def ensure_scenario(sm, seed, M, conflict):
    return build_synthetic_scenario(sm, seed, M, conflict, obs=OBS, noise=NOISE,
                                    jitter=JITTER)


def run_e1(sm):
    log.info("=== [cf] E1: causal decomposition (partial observation + CF-RP) ===")
    strategies = all_strategies()
    rows = []
    for conflict in ("low", "high"):
        for t in range(TRIALS):
            seed = SEED * 1000 + t
            sc = ensure_scenario(sm, seed, M_OPS, conflict)
            for name, fn in strategies.items():
                sigma, cov, unr = fn(sc, seed=seed)
                m = evaluate(sc, sigma, cov, unr, name)
                rows.append({
                    "conflict": conflict, "trial": t, "strategy": name,
                    "tau_causal": m["tau_causal"], "tau_contested": m["tau_contested"],
                    "info_retention": m["info_retention"],
                })
            # repair-cost measure for unconstrained RP
            sigma_u, _, _ = merge_ranked_pairs_unconstrained(sc, seed=seed)
            m_u = evaluate(sc, sigma_u, 1.0, 0, "rp_unconstrained")
            rows.append({
                "conflict": conflict, "trial": t, "strategy": "rp_unconstrained",
                "tau_causal": m_u["tau_causal"], "tau_contested": m_u["tau_contested"],
                "info_retention": m_u["info_retention"],
                "repair_swaps": count_causal_violations(sigma_u, sc.causal_edges),
            })
    df = pd.DataFrame(rows)
    os.makedirs(SYNTH_OUT, exist_ok=True)
    df.to_csv(os.path.join(SYNTH_OUT, "e1_causal_decomp.csv"), index=False)
    summary = df.groupby(["conflict", "strategy"])[
        ["tau_causal", "tau_contested", "info_retention"]].mean().round(3)
    log.info("E1 summary:\n%s", summary.to_string())
    return df


def run_e2(sm):
    log.info("=== [cf] E2: end-to-end (high conflict, partial observation + CF-RP) ===")
    strategies = all_strategies()
    rows = []
    for t in range(TRIALS):
        seed = SEED * 5000 + t
        sc = ensure_scenario(sm, seed, M_OPS, "high")
        for name, fn in strategies.items():
            sigma, cov, unr = fn(sc, seed=seed)
            m = evaluate(sc, sigma, cov, unr, name)
            rows.append({
                "trial": t, "strategy": name,
                "ops_retained": m["ops_retained"], "auto_coverage": m["auto_coverage"],
                "info_retention": m["info_retention"], "tau_causal": m["tau_causal"],
                "tau_contested": m["tau_contested"],
                "semantic_validity": m["semantic_validity"], "gini": m["gini"],
            })
        sigma_u, _, _ = merge_ranked_pairs_unconstrained(sc, seed=seed)
        m_u = evaluate(sc, sigma_u, 1.0, 0, "rp_unconstrained")
        rows.append({
            "trial": t, "strategy": "rp_unconstrained",
            "ops_retained": m_u["ops_retained"], "auto_coverage": m_u["auto_coverage"],
            "info_retention": m_u["info_retention"], "tau_causal": m_u["tau_causal"],
            "tau_contested": m_u["tau_contested"],
            "semantic_validity": m_u["semantic_validity"], "gini": m_u["gini"],
            "repair_swaps": count_causal_violations(sigma_u, sc.causal_edges),
        })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(SYNTH_OUT, "e2_end2end.csv"), index=False)
    summary = df.groupby("strategy")[
        ["ops_retained", "auto_coverage", "info_retention", "tau_causal",
         "semantic_validity", "gini"]].mean().round(4)
    log.info("E2 summary:\n%s", summary.to_string())
    return df


def run_e3(sm):
    log.info("=== [cf] E3: CF-RP vs constrained exact Kemeny (M=4..8) ===")
    rows = []
    for M in (4, 5, 6, 7, 8):
        for t in range(24):
            seed = 7000 + M * 100 + t
            sc = ensure_scenario(sm, seed, M, "high")
            cf_sigma = merge_ranked_pairs(sc, seed=t)[0]
            cf_tau = sum(tau(cf_sigma, rl) for rl in sc.replica_logs)
            ex_tau = kemeny_exact(sc.replica_logs, sc.D)[1]
            t0 = time.perf_counter()
            cx_sigma, cx_tau = kemeny_exact_constrained(sc.replica_logs, sc.D,
                                                        sc.causal_edges)
            cx_ms = (time.perf_counter() - t0) * 1000
            sigma_u, _, _ = merge_ranked_pairs_unconstrained(sc, seed=t)
            u_tau = sum(tau(sigma_u, rl) for rl in sc.replica_logs)
            rows.append({
                "M": M, "trial": t,
                "rp_exact_constrained": (cf_tau == cx_tau),
                "rp_tau": cf_tau, "constrained_kemeny_tau": cx_tau,
                "unconstrained_kemeny_tau": ex_tau,
                "excess_pct": (cf_tau / cx_tau - 1.0) * 100 if cx_tau else 0.0,
                "rp_unconstrained_tau": u_tau,
                "unconstrained_excess_pct": (u_tau / cx_tau - 1.0) * 100 if cx_tau else 0.0,
                "rp_unc_causal_viol": count_causal_violations(sigma_u, sc.causal_edges),
                "constrained_ms": cx_ms,
            })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(SYNTH_OUT, "e3_rp_vs_kemeny.csv"), index=False)
    summary = df.groupby("M").agg(
        rp_exact_rate=("rp_exact_constrained", "mean"),
        avg_excess_pct=("excess_pct", "mean"),
        max_excess_pct=("excess_pct", "max"),
        unconstrained_excess=("unconstrained_excess_pct", "mean"),
        viol_trials_frac=("rp_unc_causal_viol", lambda s: (s > 0).mean()),
        viol_mean=("rp_unc_causal_viol", "mean")).round(4)
    log.info("E3 summary:\n%s", summary.to_string())
    print(summary.to_string())
    return df


def run_e5(sm):
    log.info("=== [cf] E5: performance (CF-RP) ===")
    rows = []
    for M in (5, 8, 10, 15, 20, 30, 50, 100):
        for t in range(12):
            sc = ensure_scenario(sm, 9000 + M * 10 + t, M, "high")
            t0 = time.perf_counter()
            merge_ranked_pairs(sc, seed=t)
            rp_ms = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            merge_ranked_pairs_unconstrained(sc, seed=t)
            rp_unc_ms = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            merge_lww(sc, seed=t)
            lww_ms = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            merge_vc(sc, seed=t)
            vc_ms = (time.perf_counter() - t0) * 1000
            rows.append({"M": M, "trial": t, "rp_ms": rp_ms, "rp_unc_ms": rp_unc_ms,
                         "lww_ms": lww_ms, "vc_ms": vc_ms,
                         "merge_thr_ops_s": M / rp_ms * 1000 if rp_ms else 0.0})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(SYNTH_OUT, "e5_perf.csv"), index=False)
    summary = df.groupby("M")[["rp_ms", "rp_unc_ms", "lww_ms", "vc_ms",
                               "merge_thr_ops_s"]].quantile(0.5).round(4)
    log.info("E5 summary(p50):\n%s", summary.to_string())
    return df


def run_e6a(sm):
    log.info("=== [cf] E6a: partition asymmetry (partial observation) ===")
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
                             "info_retention": m["info_retention"], "tauhat": m["tauhat"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(SYNTH_OUT, "e6a_asymmetry.csv"), index=False)
    summary = df.groupby(["minority_frac", "strategy"])[
        ["ops_retained", "info_retention"]].mean().round(4)
    log.info("E6a summary:\n%s", summary.to_string())
    return df


def run_crdt_ceiling(sm):
    log.info("=== [cf] CRDT ceiling (partial observation) ===")
    strategies = {"crdt_pure": all_strategies()["crdt_pure"],
                  "crdt_lww": all_strategies()["crdt_lww"],
                  "lww": all_strategies()["lww"],
                  "ranked_pairs": merge_ranked_pairs,
                  "vc": all_strategies()["vc"]}
    rows = []
    for x in [round(i / 10, 1) for i in range(11)]:
        smx = SyntheticModel(N=N_REPLICAS, K=8, seed=SEED, incr_ratio=1.0 - x,
                             set_ratio=x / 2)
        for t in range(TRIALS):
            seed = SEED * 15000 + int(x * 10) * 1000 + t
            sc = build_synthetic_scenario(smx, seed, M_OPS, "high", obs=OBS,
                                          noise=NOISE, jitter=JITTER)
            for name, fn in strategies.items():
                sigma, cov, unr = fn(sc, seed=seed)
                m = evaluate(sc, sigma, cov, unr, name)
                rows.append({"noncomm": x, "trial": t, "strategy": name,
                             "semantic_validity": m["semantic_validity"],
                             "auto_coverage": m["auto_coverage"],
                             "info_retention": m["info_retention"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(SYNTH_OUT, "e3_crdt_ceiling.csv"), index=False)
    summary = df.groupby(["noncomm", "strategy"])[
        ["semantic_validity", "auto_coverage", "info_retention"]].mean().round(4)
    log.info("CRDT ceiling summary:\n%s", summary.to_string())
    return df


def main():
    sm = SyntheticModel(N=N_REPLICAS, seed=SEED)
    log.info("synthetic model: %d ops, %d replicas", len(sm.ops), sm.N)
    run_e1(sm)
    run_e2(sm)
    run_e3(sm)
    run_e5(sm)
    run_e6a(sm)
    run_crdt_ceiling(sm)
    log.info("done; results written to %s", SYNTH_OUT)


if __name__ == "__main__":
    main()
