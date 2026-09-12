# Section 7. Real-Trace Validation on a Production-Grade Platform

> New independent section for the paper *Kendall Tau Distance as a Quality Metric for Diverged Log Reconciliation*.
> Insert after §6 (Empirical Evaluation), before §7 (Practical Feasibility); renumber the original §7–§9 as §8–§10.
> All numbers below are drawn from the experiment suite `ktau_cassandra_experiment/` (raw CSVs in `results/`, aggregated report in `results/experiment_report.md`); the suite is seed-fixed and fully reproducible.

---

## 7.1 Motivation and Experimental Design Background

The evaluation of §6 uses synthetic workloads in which partition balance, causal density, observation noise, and clock skew are controlled to expose worst-case behavior. Section 8.1 identifies synthetic workloads as the primary threat to validity and lists validation on production traces as the clearest direction for future work. This section closes that gap: we replay **real system logs from the Loghub benchmark collection** on a **production-grade Cassandra 4.1 cluster**, and re-run the full measurement suite of §6 against these trace-driven scenarios. The goals are threefold: (i) confirm that the causal-decomposition theory (Prop. 2, Prop. 4(a)) and the RP-as-τ-optimum proxy (§6.2) hold on data not constructed by our generator; (ii) quantify how the metric and the strategy ranking behave when the workload is *moderate* rather than adversarially skewed; and (iii) validate the online-monitoring claim of §2.4 and the monitoring agenda of §8.4 with a live, time-series experiment.

**Trace data.** We use the BGL log (Blue Gene/L, LLNL) as the primary trace, with the HDFS log (Hadoop distributed file system) as a cross-check. Both are standard public benchmarks from the Loghub collection [loghub]. Each log line is mapped to an operation under the semanticization of §6.1: the issuing node becomes the logical replica (node id hashed to the N=8 replicas), the line timestamp becomes the operation timestamp (LWW basis), and the Level/Label field determines the operation type (INFO→incr commutative; WARN/ERROR→set; FATAL/SEVERE/alert→cas conditional). A causal DAG is constructed from within-node temporal adjacency plus cross-node probabilistic edges, with the cross-edge probability tuned by binary search so that the resulting causal density matches the target (low conflict: ≈35%; high conflict: ≈10%), mirroring §6.1.

**Platform.** The scenarios are materialized on a 4-node Cassandra 4.1 cluster (RF=2) deployed with Docker Compose; the coordinator (Python + cassandra-driver) reads the per-replica logs from the cluster, runs the reconciliation strategies, and writes results back. All strategies consume identical replica-log inputs per trial (fairness protocol of §6.1). Defaults: N=8 logical replicas mapped onto 4 physical nodes, M=24 divergent operations per conflict group, 30 trials, fixed seed 42, observation noise 5%, clock skew ≤500 µs. Log import throughput was 302 ops/s; CQL round-trip latency p50=3.4 ms / p95=4.7 ms / p99=6.2 ms; cluster CPU stayed below 8% per node with ≈1.4 GB memory per node, confirming negligible platform overhead for the measurement load.

## 7.2 Implementation Steps

1. **Trace acquisition and ingestion.** The BGL/HDFS traces are fetched from the Loghub mirror, parsed into typed operations (`trace_ops`), and imported into Cassandra.
2. **Scenario generation.** For each trial, M operations are sampled from the trace and organized into a single connected conflict group; a causal DAG is built to the target density; each replica's local log is a causally consistent subsequence with arrival jitter (§6.1).
3. **Reconciliation.** Six strategies run on identical inputs: leader overwrite, LWW, vector clocks, pure CRDT, CRDT+LWW fallback, and Ranked Pairs (bitset-accelerated transitive closure, O(M³/64) worst case).
4. **Metrics.** All metrics of §6.1 (operation retention, auto coverage, information retention 1−τ̂, τcausal, τcontested, semantic validity, Gini, wall-clock time) are computed by a single shared evaluator.
5. **Online monitoring (E4).** A live writer streams operations into the cluster while a monitor samples each replica's most recent window (20 ops) once per second and computes τ̂, max replica lag, and operation-set Jaccard similarity. The stream passes through five phases: steady state → *ordering drift* (per-replica in-place reshuffling of a random contiguous block of the window; no new operations, so maxlag≡0 and Jaccard≡1) → convergence → *set divergence* (operations delivered to only group A or B, so Jaccard falls while τ̂ stays ≈0) → healing. Detection latency, steady-state false alarms, and peak τ̂ are recorded per configuration.
6. **Validation.** Experiments E1/E1b (causal decomposition), E2 (end-to-end), E3 (RP vs. exact Kemeny), E4 (monitoring), E5 (performance scaling), E6a (partition asymmetry) are executed exactly as in §6, with only the workload source changed from synthetic to trace-driven.

## 7.3 Raw Results and Analysis

**Causal decomposition (E1, E1b).** Across all 30 trials, both conflict levels, and all six strategies, τcausal = 0.0000 — every strategy preserves all unanimous causal constraints on trace-driven data, confirming Prop. 4(a). To test the *detection* side of the metric, we replay the §5.3.3 counterexample (a local-search order b ≻ z1 ≻ z2 ≻ a violating the unanimous constraint a ≻ b): the metric returns τcausal = 3 = n_ab, τtotal = 9, and τ̂ = 0.5000, exactly as the theory predicts. Table 6 summarizes.

**End-to-end comparison (E2).** Table 7 reports 30-trial means. Two findings stand out. First, the *ranking is preserved but compressed*: Ranked Pairs retains 100.00% of ordering information on every trial (τ̂≡0, Gini≡0), while LWW/VC/CRDT drop to 99.95–99.91% on the subset of trials containing genuine contested pairs — the direction of the §6.4 gap (RP > LWW > VC) is unchanged, but its magnitude shrinks because trace-driven disagreements are far milder than the adversarial synthetic regime. Second, leader overwrite retains only 20.8% of operations (it keeps the leader replica's log only, an intentionally conservative implementation; see E6a below), confirming that leader-based reconciliation pays in element-set reduction rather than ordering quality.

**RP vs. exact Kemeny (E3).** Ranked Pairs reaches the exact Kemeny-Young optimum in 100% of trials at every size M=4..8 with zero excess τ. On moderate-disagreement trace scenarios the approximation is exact far more often than the 62–100% range reported in §6.2 for adversarial scenarios; the bitset-accelerated implementation completes M=100 in 8.05 ms (p50) versus 328 ms for the naive single-threaded implementation reported in §6.7.

**Online monitoring (E4).** This is the most informative new result. Fig. 7 shows the live trajectory of τ̂ and Jaccard through the five phases. During *ordering drift*, τ̂ rises from 0 to 0.28–0.38 while maxlag remains ≡0 and Jaccard remains ≡1.0: the metric detects an ordering divergence that binary lag and operation-set similarity cannot see, directly confirming the sub-threshold-detection claim of §2.4. During *set divergence*, τ̂ stays ≈0 while Jaccard drops to 0.42–0.43: the two signals are complementary, exactly as proposed in §8.4. Detection latency is 0.39–1.45 s (1–2 samples at a 1 s sampling period) with **zero false alarms** in the steady phase across all drift strengths; peak τ̂ (0.28–0.38) exceeds the alert threshold (0.05) by a wide margin. Table 8 summarizes.

**Performance and partition asymmetry (E5, E6a).** Fig. 6 holds on the trace platform: τ_total costs 0.12 ms at M=5 and 64.5 ms at M=100; RP sub-millisecond for M≤15, 8 ms at M=100; merge throughput 12k–377k ops/s. As minority partition size grows 10%→50%, leader operation retention falls monotonically (29.2%→16.7% under the conservative leader-replica-log model; the majority-union model of §6.6 would scale with majority size as reported there), while full-retention strategies stay flat with RP at 100% information retention and LWW at 99.96–99.98%.

## 7.4 Comparison with the Theoretical Model

| Claim (Prop. / §) | Prediction | Observed (trace) | Verdict |
|---|---|---|---|
| Prop. 2: every violated causal constraint contributes exactly n_ab | τcausal = 3 = n_ab on §5.3.3 counterexample | τcausal = 3, τtotal = 9, τ̂ = 0.5 | ✅ exact |
| Prop. 4(a): Condorcet-consistent methods satisfy all unanimous constraints | τcausal = 0 for RP on any input | τcausal = 0, all 30 trials, both conflict levels | ✅ confirmed |
| §6.2: RP approximates the τ-optimum | near-exact on moderate disagreement | 100% exact at M≤8, zero excess | ✅ stronger than synthetic |
| §5.5: Gini complements τ on inversion-distribution fairness | RP fair, LWW concentrates inversions | Gini: RP≡0; LWW=0.875 on contested trials | ✅ confirmed |
| §2.4 / §8.4: τ as early-warning signal, complementary to Jaccard | τ rises on ordering-only divergence; Jaccard falls on set divergence | τ̂ 0→0.28–0.38 while maxlag≡0; Jaccard→0.42 while τ̂≈0 | ✅ first empirical confirmation |
| §6.4: strategy ranking | RP > LWW > VC on info retention | ordering preserved but magnitude compressed (99.91–100% range) | ✅ direction, workload-sensitive magnitude |

**Key finding.** On real traces the *qualitative* predictions of the theory hold without exception — causal exactness, RP optimality, Gini fairness, and the τ/Jaccard complementarity — while the *quantitative* gaps among full-retention strategies shrink substantially because genuine contested pairs are rare in a single-source timestamped log. The metric's discriminative power is therefore workload-sensitive by design: it is most informative exactly where it matters (ordering-conflict-dense and monitoring regimes), and harmlessly close in benign regimes. This refines, rather than contradicts, the §6.4 baseline numbers, which characterize the adversarial end of the spectrum.

**Reproducibility.** The full suite, including trace files, Docker Compose topology, scripts, and all raw CSVs, is archived with the project; random seeds are fixed (42) and every CSV row is per-trial, so all tables here can be regenerated by re-running the pipeline.

---

## Tables (drafts for the paper)

**Table 6. Causal decomposition on trace-driven scenarios (E1/E1b; N=8, M=24, 30 trials, both conflict levels).**
Strategy | τ_causal | τ_contested (mean) | τ̂ | Info. retention | Gini (contested trials)
---|---|---|---|---|---
Leader overwrite | 0.0000 | 0.0000 | 0.0000 | 1.0000* | 0.0000
LWW | 0.0000 | 0.5000 | 0.0002 | 0.9998 | 0.861
Vector clocks | 0.0000 | 0.5000 | 0.0002 | 0.9998 | 0.861
Pure CRDT | 0.0000 | 0.5000 | 0.0002 | 0.9998 | 0.861
CRDT + LWW fallback | 0.0000 | 0.5000 | 0.0002 | 0.9998 | 0.861
Ranked Pairs | 0.0000 | **0.0000** | 0.0000 | **1.0000** | **0.0000**
*On the 20.8% of operations retained; §5.3.3 counterexample replay: τ_causal = 3 = n_ab, τ_total = 9, τ̂ = 0.5000. Gini averaged over the 9 contested trials (0.875 on 8 of them, 0.75 on one); RP is 0.0000 on every trial.

**Table 7. End-to-end quality on trace scenarios (E2, high conflict, N=8, M=24, 30-trial means).**
Strategy | Ops ret. | Auto cov. | Info ret. | Caus. viol. | Sem. valid. | Gini | Time (ms)
---|---|---|---|---|---|---|---
Leader overwrite | 20.8% | 100% | 100%* | 0.0 | 100% | 0.000 | 0.006
LWW | 100% | 100% | 99.98% | 0.0 | 82.2% | 0.258 | 0.022
Vector clocks | 100% | 90.8% | 99.98% | 0.0 | 82.2% | 0.258 | 0.051
Pure CRDT | 100% | 90.8% | 99.98% | 0.0 | 82.2% | 0.258 | 0.016
CRDT + LWW fallback | 100% | 100% | 99.98% | 0.0 | 82.2% | 0.258 | 0.013
Ranked Pairs | 100% | 100% | **100.0%** | 0.0 | 82.8% | **0.000** | 0.369
*On surviving operations. Info. retention = 1 − τ̂ (normalized over the full group; per-trial values 0.9991–1.0000).

**Table 8. Live monitoring (E4): detection of ordering drift invisible to lag and set similarity.**
drift_max | Detect delay (s) | maxlag@detect | Steady false alarms | Peak τ̂ (drift) | Peak τ̂ (partition) | Jaccard min (partition) | Jaccard @heal
---|---|---|---|---|---|---|---
0.10 | 1.448 | 0 | 0 | 0.3112 | 0.0000 | 0.4286 | 0.9527
0.20 | 0.391 | 0 | 0 | 0.3612 | 0.0000 | 0.4184 | 0.9490
0.40 | 0.716 | 0 | 0 | 0.2829 | 0.0000 | 0.4286 | 0.9261
0.60 | 0.490 | 0 | 0 | 0.3822 | 0.0000 | 0.4286 | 0.9762

**Fig. 7 (draft caption).** Live τ̂ and Jaccard trajectories through five phases (trial, drift_max=0.2). Steady: τ̂=0, Jaccard≈0.95. Drift: τ̂ rises to 0.36 while maxlag≡0 and Jaccard≡1.0. Converge: τ̂ returns toward 0. Partition: τ̂≈0 while Jaccard drops to 0.42. Heal: Jaccard recovers to 0.95. The two signals respond in disjoint failure modes, confirming complementarity.
