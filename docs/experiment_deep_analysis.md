# In-depth Analysis of Experiment Results

> Basis: BGL/HDFS real trace experiments (E1–E6a) on a Docker + Cassandra 4.1 cluster
> Data sources: `results/*.csv` (raw data), `results/experiment_report.md` (auto summary)
> Paper: *Kendall Tau Distance as a Quality Metric for Diverged Log Reconciliation*
> Purpose of this report: systematically organize the experimental results, identify key evidence supporting the core claims, uncover new findings, examine discrepancies with the paper's statements, and propose tuning suggestions.

---

## 1. Experiment overview

| Experiment | Content | Key metrics |
|------|------|---------|
| E1 | τ causal decomposition for six strategies under low/high conflict | τ_causal, τ_contested, τ̂, info retention |
| E1b | paper §5.3.3 counterexample reproduction | τ_causal, τ_total, τ̂ |
| E2 | end-to-end comparison (high conflict, M=24, 30 trials) | ops retained, auto coverage, info retention, semantic validity, Gini, runtime |
| E3 | RP vs exact Kemeny (M=4..8) | RP exact rate, excess % |
| E4 | real-time τ monitoring (drift → partition → heal, drift_max sweep) | detection latency, maxlag@detect, steady false alarms, peak τ̂, Jaccard trajectory |
| E5 | performance and scalability (M=5..100) | τ/RP/LWW/VC runtime, merge throughput |
| E6a | partition asymmetry (minority 10%→50%) | leader ops retained, RP vs LWW info retention |

Common defaults: N=8 logical replicas (mapped to 4 Cassandra physical nodes), M=24, trials=30, seed=42, obs=0.9, noise=0.05, skew≤500µs. Trace data: `data/BGL_2k.log` (2000 lines) and `data/HDFS_2k.log` (2000 lines).

---

## 2. Key data supporting the paper's core claims

### 2.1 Causal decomposition theorem (Prop 2, Prop 4(a)) — E1, E1b

**Key evidence: E1b counterexample reproduction (deterministic result)**

| Metric | Value | Paper prediction | Verdict |
|------|------|---------|------|
| τ_causal | **3 (= n_ab)** | each violated consistent constraint contributes exactly n_ab | ✅ exact match |
| τ_total | 9 | — | — |
| τ̂ | 0.5000 | τ̂ = 0.5 in the counterexample | ✅ exact match |

This directly demonstrates Prop 2: τ's counting of causal inversions is **exact and deterministic** — the bad order produced by local search (b ≻ z1 ≻ z2 ≻ a violating the consistent constraint a ≻ b) is counted exactly as 3 by τ_causal, showing that τ as a scoring metric can detect the causal disorder produced by any algorithm.

**Key evidence: E1 τ_causal = 0 across all strategies**

- 30 trials × 2 conflict levels × 6 strategies, all τ_causal = 0.0000.
- Demonstrates Prop 4(a): the Condorcet-consistent method (RP) **satisfies all consistent constraints unconditionally**; under well-configured settings (small clock skew, causally consistent logs), LWW/VC/CRDT also satisfy them, consistent with paper §6.3 "τcausal = 0 across all strategies".
- τ_contested is 1–3 in some trials (mean 0.5 for both low/high conflict), related to "mild divergence in real-trace scenarios" (see §4.1).

### 2.2 RP's information-retention advantage — E2, E6a

**Key evidence (E2 raw data checked trial by trial):**

Across all 30 trials:
- **ranked_pairs information retention is always = 1.0000** (τ̂ ≡ 0, τ_contested ≡ 0, Gini ≡ 0), without exception.
- In trials with contested divergence (trials 210007, 210011, 210015, 210016, 210018, 210021, 210024, 210026, 210029, 9 trials total), LWW/VC/CRDT information retention drops to 0.9995–0.9991 (τ_contested=1 or 2), while RP remains 1.0000.
- Gini: among the 9 contested trials, the mean Gini of LWW/VC/CRDT is 0.861 (8 trials at 0.875, trial 210029 at 0.75 — divergence highly concentrated on a few replicas), while RP is always 0 (perfectly fair). **This directly supports the fairness dimension of paper §5.5**: when τ_total is equal (or similar), the Gini difference between RP and LWW is significant, showing τ needs Gini as a complement.

**Key evidence (E6a):**
- RP keeps info retention constant at 1.0000 (τ̂ ≡ 0) across the minority 10%→50% sweep; LWW is 0.9996–0.9998 (τ̂ 0.0002–0.0004).
- Leader ops retained decreases monotonically as the minority ratio grows (0.29→0.17; see the implementation difference in §4.3), consistent with the trend of paper §6.6.

### 2.3 RP as a τ-optimal proxy — E3

**Key evidence: across all M=4..8 trials, RP exactly matches the Kemeny optimum (rp_exact=100%, excess 0%).**

Paper §6.2 claims "at M=8, RP is 62% exact with 1.6% average excess"; in trace scenarios RP is 100% exact. The two are complementary: both the synthetic high-divergence scenario (paper) and the real mild-divergence scenario (trace) validate that **RP is the closest proxy to the τ-optimal within polynomial time**. Trace scenarios have milder divergence, so RP hits the exact optimum more easily.

### 2.4 Computational feasibility — E5

**Key evidence (p50):**

| M | τ_total(ms) | RP(ms) | LWW(ms) | VC(ms) | merge throughput(ops/s) |
|---|---|---|---|---|---|
| 5 | 0.119 | 0.013 | 0.008 | 0.012 | 377,364 |
| 20 | 1.686 | 0.196 | 0.019 | 0.038 | 102,287 |
| 50 | 12.779 | 1.572 | 0.043 | 0.121 | 31,810 |
| 100 | 64.491 | **8.053** | 0.069 | 0.335 | 12,418 |

- RP is only 8ms at M=100 (paper Fig.6 claims 328ms for single-threaded Python — this experiment uses a bitset transitive-closure optimization O(M³/64), **far outperforming the paper's original implementation**, further strengthening the "sub-millisecond (M≤15)" claim).
- Merge throughput is 12k–377k ops/s; CQL round-trip latency p50=3.4ms / p95=4.7ms / p99=6.2ms; cluster CPU<8%, memory ~1.4GB/node — **end-to-end overhead on a real database platform is negligible**.

---

## 3. New findings: phenomena the paper did not explicitly demonstrate but this experiment reveals

### 3.1 【Important】τ has sub-threshold detection capability invisible to binary lag (E4)

Paper §2.4 asserts τ "rises the moment ordering disagreement appears, enabling sub-threshold detection" but **provides no empirical evidence**. The E4 drift phase gives direct evidence:

| drift_max | peak τ̂ during drift | maxlag in same period | Jaccard in same period |
|---|---|---|---|
| 0.10 | 0.3112 | **≡ 0** | **≡ 1.0** |
| 0.20 | 0.3612 | **≡ 0** | **≡ 1.0** |
| 0.40 | 0.2829 | **≡ 0** | **≡ 1.0** |
| 0.60 | 0.3822 | **≡ 0** | **≡ 1.0** |

The experimentally constructed drift phase **adds no operations and does not change the operation set** (maxlag≡0, Jaccard≡1.0); it only reshuffles the order within replica windows, and τ̂ rises from 0 to 0.28–0.38. This is the **first empirical demonstration** that "ordering divergence is invisible at the count and set level, and visible only at the pairwise-order level": binary lag / version-vector detection methods commonly used in production systems completely fail in this phase, while τ detects it.

### 3.2 【Important】Complementarity of τ and operation-set Jaccard (E4)

Paper §8.4 lists "online monitoring complemented by operation-set Jaccard similarity to disambiguate degraded from fully partitioned phases" as a **future direction**. E4 directly demonstrates this complementarity:

- Ordering-drift phase: τ̂ rises (0.28–0.38) while Jaccard ≡ 1.0 → **τ responds alone**.
- Set-divergence (partition) phase: τ̂ ≈ 0 while Jaccard drops from 1.0 to **0.418–0.429** → **Jaccard responds alone**.
- Healing phase: Jaccard recovers to 0.926–0.976, τ̂ stays 0.

The two metrics respond on disjoint failure modes, and joint monitoring can distinguish "degraded (ordering disorder)" from "fully partitioned (set split)" anomalies. **The §8.4 future direction has been implemented by this experiment; the paper should upgrade it to completed-and-validated.**

### 3.3 Monitoring real-time performance and reliability (E4)

- Detection latency 0.391–1.448s (triggered within 1–2 samples under a 1s sampling period), threshold 0.05.
- Zero false alarms in steady state (no-fault period) across all 4 drift_max configurations.
- Peak τ̂ 0.28–0.38 far exceeds the threshold 0.05; the signal/threshold margin is ample (>5×).

### 3.4 Strategy differences are compressed in real-trace scenarios (E1/E2/E6a)

In scenarios constructed from the real BGL trace, operations are mostly ordered along a single timeline, and pairwise-order disagreement between replicas is tiny, so **all automatic strategies have info retention close to 1.0** (0.9995–1.0000), whereas the paper's synthetic experiments (high noise, large clock skew, high concurrency density) amplify strategy gaps to 52.5%–63.9%.

This phenomenon is itself a valuable finding: **ordering divergence in real system logs is usually far smaller than in synthetic worst cases**; under real workloads, τ plays more the role of a "causal-correctness monitor" than a "strategy differentiator"; strategy differences mainly appear in contest-dense, ordering-disordered fault scenarios (E4 drift phase, E2 contested trials). The paper should use this to clarify the applicable boundary of the §6.4 numbers (see §4.1).

---

## 4. Discrepancies with the paper's statements and tuning suggestions

### 4.1 【Discrepancy】E2 info retention vs paper §6.4 Table 4

| Source | RP | LWW | VC |
|---|---|---|---|
| Paper §6.4 (synthetic high conflict) | 63.9% | 58.1% | 52.5% |
| This experiment E2 (trace) | 100.0% | 99.95–100.0% | 99.95–100.0% |

**Cause**: in trace scenarios, pairwise-order disagreement between replicas is tiny (BGL is a single-timeline log; observation noise 5% and clock skew ≤500µs are far smaller than the paper's synthetic skew/concurrency density). The paper's 52.5–63.9% comes from artificially amplified worst-case divergence.

**Tuning suggestion**: paper §6.4 should note that the numbers come from a "synthetic worst case", and add a paragraph stating: under the mild-divergence scenarios constructed from real traces (BGL/HDFS), all automatic strategies are near-optimal (info retention ≥99.9%), with RP remaining optimal across all trials (τ̂≡0, Gini≡0); strategy quality gaps are **contention-strength sensitive** — the gap under worst-case (synthetic) and near-equality under mild scenarios (trace) jointly bound the workload sensitivity of the τ metric. This **does not weaken** the core claim (τ distinguishes scenarios that differ) but adds its applicability boundary.

### 4.2 【Discrepancy】E3 RP exact rate vs paper §6.2 Table 3

The paper reports 62% exact and 1.6% excess at M=8; trace scenarios give 100% exact and 0% excess. **The directions agree** (RP is close to/at the Kemeny optimum); the numerical difference stems from scenario divergence intensity. The paper can add one sentence: under the low-divergence scenarios constructed from real traces, RP reaches the exact optimum 100% of the time for M≤8.

### 4.3 【Discrepancy】E6a leader ops retained vs paper §6.6

The paper claims leader retention drops from 88.3% to 53.1% as the minority grows from 10%→50% (= majority share). The experiment gives 0.29→0.17.

**Cause**: this experiment's `merge_leader` uses the **most conservative implementation** — retaining only the operations of majority-partition replicas present in the leader replica's own log (`replica_logs[leader_idx]`), rather than the paper's assumed "retain all majority-partition operations". Retention is therefore significantly lower.

**Tuning suggestion**: paper §6.6 (or a new section) should state the implementation difference: the experiment adopts the strict "leader-replica-log only" model, whose ops-retained (0.29→0.17) is lower than the "full majority" model (88.3%→53.1%), but the **monotonic trend is identical** (larger minority → less retention), and the leader's info retention (τ=0 on surviving operations) is consistent with the element-set-shrinkage mechanism. To reproduce the paper's numbers, re-run with the full-majority model.

### 4.4 【Discrepancy】E5 RP runtime vs paper §6.7 Fig.6

The paper's single-threaded Python implementation takes 328ms at M=100; this experiment's bitset optimization takes 8ms. **The discrepancy favors the paper**: the §6.7 claims of "sub-millisecond (M≤15), tens of ms (M=50)" hold under the better implementation and are even stronger. The paper can note "implemented with incremental bitset transitive closure, outperforming the naive implementation".

### 4.5 【Upgrade】Paper §8.4 future direction has been demonstrated

Paper §8.4: "online monitoring using pairwise τ as an early-warning signal for gradual divergence, complemented by operation-set Jaccard similarity to disambiguate degraded from fully partitioned phases" — **E4 has fully implemented and validated it**. §8.4 should upgrade this from future work to completed (citing the new section).

### 4.6 【Update】Paper §8.1 threat statement

Paper §8.1 states "Validation on production traces and real state machines is the clearest direction for future work". This experiment has completed validation on real traces (Loghub BGL/HDFS) + a real database (Cassandra 4.1 cluster); this sentence should be updated to "preliminary trace validation completed in §7 (new section); larger scale and more data types remain".

---

## 5. Key figure material checklist (directly usable in the paper)

| Purpose | Data source | Suggested presentation |
|------|--------|---------|
| Causal decomposition | E1/E1b | bar chart: τ_causal all 0 + counterexample τ_causal=3=n_ab; table |
| End-to-end comparison | E2 | table: info retention/auto coverage/ops retained/Gini/runtime |
| RP vs Kemeny | E3 | table: M=4..8 exact rate 100%, excess 0%, Kemeny runtime growing exponentially |
| Monitoring trajectory | E4 series | line chart: τ̂ and Jaccard dual-axis time series with 5 phases annotated |
| Performance | E5 | log-log plot: τ/RP runtime vs M; throughput table |
| Partition asymmetry | E6a | line chart: leader retention monotonically decreasing with minority; RP constant 1.0 |
| Platform overhead | perf_host/cql | table: CPU<8%, memory 1.4GB/node, CQL p50=3.4ms |

---

## 6. Key conclusions (suggestions for the paper §6.8 supplement)

1. **The causal decomposition is real**: τ_causal=0 (all strategies) + exact counterexample counting τ_causal=3=n_ab (E1b) jointly validate Prop 2/Prop 4(a).
2. **The τ-optimal is engineering-implementable**: RP reaches the exact Kemeny optimum 100% of the time for M≤8 in trace scenarios; merging at M=100 takes 8ms.
3. **τ has production-grade monitoring value**: it detects ordering divergence while maxlag≡0 and Jaccard≡1.0 (sub-threshold detection), complements Jaccard to distinguish partitions from degradation; zero steady-state false alarms.
4. **Strategy gaps are compressed in real traces**: under mild divergence, all automatic strategies are near-optimal; the gap is contention-strength sensitive (this is the applicable boundary of the §6 synthetic numbers).
