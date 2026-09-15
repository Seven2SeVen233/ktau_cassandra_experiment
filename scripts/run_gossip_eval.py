"""Dissemination-premise experiment (option A validation): complete ballots
(disseminated ballots) + degraded dissemination diagnosis.

A revised experiment design based on the §4.1 dissemination assumption
(causally ordered gossip makes ballots complete and causally closed):

- E1c causal decomposition (low/high, six strategies, complete ballots)
- E2c end-to-end (high, six strategies, complete ballots)
- E3c Ranked Pairs vs exact Kemeny (M=4..8, complete ballots) + consistent-pair
  satisfaction check (Prop 3)
- E6ac partition asymmetry (complete ballots, leader/lww/ranked_pairs)
- D1  degraded dissemination diagnosis (5% loss): only causal pairs with an
      "exactly-one observation" replica can be violated, and when violated,
      τcausal exactly equals Σ n_ab (Prop 2 counting)
- structural check (structure.csv): ballot lengths / exactly-one observation counts

Output: results/synthetic_gossip/
  e1_complete.csv e2_complete.csv e3_complete.csv e6a_complete.csv
  d1_degraded.csv structure.csv
  statistics_complete_summary.csv statistics_complete_wilcoxon.csv
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import common
from common import log
from baselines import all_strategies, merge_leader, merge_lww, merge_ranked_pairs
from kemeny_exact import kemeny_exact
from metrics import evaluate
from ranked_pairs import ranked_pairs
from scenario_gen import Scenario, disseminate, dissemination_structure
from stats import summarize, wilcoxon
from synthetic_model import SyntheticModel, build_synthetic_scenario
from tau import positions, tau, tau_causal_order

N_REPLICAS = 10
M_OPS = 24
TRIALS = 15
SEED = 42
JITTER = 60.0
LOSS = 0.05  # degraded dissemination loss rate

OUT = os.path.join(common.RESULTS, "synthetic_gossip")


def complete_scenario(sc, seed, loss=0.0):
    """Return a new Scenario after the dissemination phase (complete/degraded
    ballots)."""
    new_logs, causal_pairs, n_ab = disseminate(sc, seed, loss=loss, jitter=JITTER)
    return Scenario(sc.ops, sc.D, new_logs, sc.causal_edges, sc.adj, causal_pairs,
                    n_ab, sc.partitions, sc.leader_idx, sc.skew, sc.N,
                    sc.causal_density, sc.conflict_groups)


def violated_pairs(order, causal_pairs):
    pos = positions(order)
    return [(a, b) for a, b in causal_pairs if pos[a] > pos[b]]


def run_e1(sm):
    log.info("=== [gossip] E1c: causal decomposition (complete ballots) ===")
    strategies = all_strategies()
    rows = []
    for conflict in ("low", "high"):
        for t in range(TRIALS):
            sc0 = build_synthetic_scenario(sm, SEED * 1000 + t, M_OPS, conflict,
                                           obs=0.9, noise=0.05, jitter=JITTER)
            sc = complete_scenario(sc0, SEED * 1000 + t)
            for name, fn in strategies.items():
                sigma, cov, unr = fn(sc, seed=SEED * 1000 + t)
                m = evaluate(sc, sigma, cov, unr, name)
                rows.append({"conflict": conflict, "trial": t, "strategy": name,
                             "M": M_OPS, "causal_density": sc.causal_density,
                             "tau_causal": m["tau_causal"], "tau_contested": m["tau_contested"],
                             "tauhat": m["tauhat"], "info_retention": m["info_retention"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e1_complete.csv"), index=False)
    log.info("E1c summary:\n%s", df.groupby(["conflict", "strategy"])[
        ["tau_causal", "tau_contested", "tauhat", "info_retention"]].mean().round(4).to_string())
    return df


def run_e2(sm):
    log.info("=== [gossip] E2c: end-to-end (complete ballots, high conflict) ===")
    strategies = all_strategies()
    rows = []
    for t in range(TRIALS):
        sc0 = build_synthetic_scenario(sm, SEED * 5000 + t, M_OPS, "high",
                                       obs=0.9, noise=0.05, jitter=JITTER)
        sc = complete_scenario(sc0, SEED * 5000 + t)
        for name, fn in strategies.items():
            t0 = time.perf_counter()
            sigma, cov, unr = fn(sc, seed=SEED * 5000 + t)
            dt_ms = (time.perf_counter() - t0) * 1000
            m = evaluate(sc, sigma, cov, unr, name)
            m["time_ms"] = dt_ms
            rows.append({"trial": t, "strategy": name, "M": M_OPS,
                         "ops_retained": m["ops_retained"], "auto_coverage": m["auto_coverage"],
                         "info_retention": m["info_retention"], "tau_causal": m["tau_causal"],
                         "tau_contested": m["tau_contested"], "semantic_validity": m["semantic_validity"],
                         "gini": m["gini"], "time_ms": m["time_ms"]})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e2_complete.csv"), index=False)
    log.info("E2c summary:\n%s", df.groupby("strategy")[
        ["ops_retained", "auto_coverage", "info_retention", "tau_causal",
         "semantic_validity", "gini", "time_ms"]].mean().round(4).to_string())
    return df


def run_e3(sm):
    log.info("=== [gossip] E3c: RP vs exact Kemeny + consistent-pair check (complete ballots) ===")
    rows = []
    for M in (4, 5, 6, 7, 8):
        for t in range(24):
            sc0 = build_synthetic_scenario(sm, 7000 + M * 100 + t, M, "high",
                                           obs=0.9, noise=0.05, jitter=JITTER)
            sc = complete_scenario(sc0, 7000 + M * 100 + t)
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
                "rp_violations": len(violated_pairs(rp_sigma, sc.causal_pairs)),
                "kemeny_violations": len(violated_pairs(ex_sigma, sc.causal_pairs)),
                "n_causal": len(sc.causal_pairs),
            })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "e3_complete.csv"), index=False)
    log.info("E3c summary:\n%s", df.groupby("M").agg(
        rp_exact_rate=("rp_exact", "mean"), avg_excess_pct=("excess_pct", "mean"),
        rp_viol=("rp_violations", "sum"), km_viol=("kemeny_violations", "sum"),
        n_causal=("n_causal", "mean")).round(4).to_string())
    return df


def run_e6a(sm):
    log.info("=== [gossip] E6ac: partition asymmetry (complete ballots) ===")
    rows = []
    for frac in (0.10, 0.20, 0.30, 0.40, 0.50):
        minority_n = max(1, int(round(N_REPLICAS * frac)))
        for t in range(TRIALS):
            seed = SEED * 9000 + int(frac * 100) * 1000 + t
            sc0 = build_synthetic_scenario(sm, seed, M_OPS, "high",
                                           obs=0.9, noise=0.05, jitter=JITTER)
            sc = complete_scenario(sc0, seed)
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
    df.to_csv(os.path.join(OUT, "e6a_complete.csv"), index=False)
    log.info("E6ac summary:\n%s", df.groupby(["minority_frac", "strategy"])[
        ["ops_retained", "info_retention"]].mean().round(4).to_string())
    return df


def run_d1(sm):
    """Degraded dissemination diagnosis: 5% loss → exactly-one observation cases;
    verify violations occur only on exactly-one pairs and are counted exactly."""
    log.info("=== [gossip] D1: degraded dissemination diagnosis (loss %.0f%%) ===", LOSS * 100)
    rows = []
    struct_rows = []
    for t in range(TRIALS):
        sc0 = build_synthetic_scenario(sm, SEED * 3000 + t, M_OPS, "high",
                                       obs=0.9, noise=0.05, jitter=JITTER)
        sc = complete_scenario(sc0, SEED * 3000 + t, loss=LOSS)
        st = dissemination_structure(sc, sc.replica_logs)
        struct_rows.append({"trial": t, "loss": LOSS, **st})
        rp_sigma = ranked_pairs(sc.replica_logs, sc.D)
        m = evaluate(sc, rp_sigma, 1.0, 0, "ranked_pairs")
        # Pairwise check: every violated pair must have an exactly-one observer
        pos = positions(rp_sigma)
        bad = 0
        for a, b in sc.causal_pairs:
            if pos[a] > pos[b]:
                exactly_one = sum(1 for rl in sc.replica_logs if (a in rl) != (b in rl))
                if exactly_one == 0:
                    bad += 1
        rows.append({"trial": t, "exactly_one": st["exactly_one_observers"],
                     "tau_causal": m["tau_causal"], "tau_contested": m["tau_contested"],
                     "violations_without_exactly_one": bad})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "d1_degraded.csv"), index=False)
    log.info("D1 summary:\n%s", df.mean().round(4).to_string())
    pd.DataFrame(struct_rows).to_csv(os.path.join(OUT, "structure_d1.csv"), index=False)
    return df


def main():
    os.makedirs(OUT, exist_ok=True)
    sm = SyntheticModel(N=N_REPLICAS, seed=SEED)
    log.info("synthetic model: %d ops, %d replicas", len(sm.ops), sm.N)

    # Complete-ballot structure check (E1 scenarios, loss=0)
    struct = []
    for t in range(TRIALS):
        sc0 = build_synthetic_scenario(sm, SEED * 1000 + t, M_OPS, "high",
                                       obs=0.9, noise=0.05, jitter=JITTER)
        sc = complete_scenario(sc0, SEED * 1000 + t)
        struct.append({"trial": t, "loss": 0.0,
                       **dissemination_structure(sc, sc.replica_logs),
                       "n_ab_min": min(sc.n_ab.values()) if sc.n_ab else 0,
                       "n_ab_max": max(sc.n_ab.values()) if sc.n_ab else 0})
    pd.DataFrame(struct).to_csv(os.path.join(OUT, "structure.csv"), index=False)
    log.info("structure check(loss=0): min_len=%s max_len=%s exactly_one=%s n_ab∈[%s,%s]",
             min(r["min_len"] for r in struct), max(r["max_len"] for r in struct),
             sum(r["exactly_one_observers"] for r in struct),
             min(r["n_ab_min"] for r in struct), max(r["n_ab_max"] for r in struct))

    e1 = run_e1(sm)
    e2 = run_e2(sm)
    e3 = run_e3(sm)
    e6a = run_e6a(sm)
    d1 = run_d1(sm)

    # Statistics (E1/E2/E6a, complete ballots)
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
    log.info("dissemination-premise experiments done; results written to %s", OUT)


if __name__ == "__main__":
    main()
