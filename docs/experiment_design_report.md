# Kendall τ Log Reconciliation Validation Experiments — Experiment Design Report

> Paper basis: *Kendall Tau Distance as a Quality Metric for Diverged Log Reconciliation* (Haoyang Chen, ICSDC)
> Experiment platform: Docker + Cassandra 4.1 (`cassandra:4.1`, verified locally available)
> Data source: Loghub BGL real log trace (gitcode mirror → GitHub → Zenodo multi-source fallback)
> Version: v0.1 (pending review)

---

## 1. Experiment objectives

Based on the paper's core claim — **Kendall τ distance can serve as a unified metric for post-partition log reconciliation quality** — this experiment systematically validates the following claims using **real log traces (Loghub BGL) + a real database platform (Cassandra 4.1 cluster)**:

| # | Validation target | Corresponding paper claim |
|------|---------|-------------|
| G1 | τ distance's ability to measure log inconsistency (accuracy + sensitivity) | §5.1 metric definition, §5.3 causal decomposition, §5.5 fine-grained discrimination |
| G2 | Effectiveness and efficiency of Ranked Pairs post-partition merge | §5.3.3, §6.2, §6.7 |
| G3 | Real-time reliability of τ-based inconsistency monitoring | §2.4 (monitoring gap), §8.4 future work |
| G4 | Systematic justification of τ (theoretical basis + empirical performance) | §5 in full, §6.8 conclusions |
| G5 | Controlled comparisons: CRDT (pure + LWW fallback), LWW and other baselines | §6.4, §6.5 |
| G6 | Performance data: throughput, algorithm runtime, resource utilization, network latency | §6.7, §7.2 |

---

## 2. Assumptions and terminology clarification

1. **"CV" = CRDT (Conflict-free Replicated Data Types)**: "CV" in requirement 4 is a typo; this report designs for CRDT. It implements **LWW**, **CRDT (pure)**, **CRDT+LWW fallback**, and **Ranked Pairs** as required options, and additionally provides three low-cost extended baselines — **Vector Clock (VC)**, **Leader overwrite**, and **exact Kemeny** (recommended to enable, to fully reproduce paper Tables 3/4).
2. **Logical replicas vs physical nodes**: the Cassandra cluster is the **execution/storage platform**; the N "replica logs" in the paper model are **logical replicas** whose local log tables are stored in Cassandra. The two are decoupled, which both faithfully follows the paper model and controls physical resource overhead (default N=8 logical replicas, 4 physical nodes).
3. **BGL is a supercomputer log, not a database log**: Loghub BGL (Blue Gene/L supercomputer) is the most widely used public real system log benchmark. This experiment **re-semanticizes it as operation logs of a distributed store** (see the §5.3 mapping), satisfying "real-trace-driven" and faithfully following the paper's "operation log reconciliation" model.
4. **Cassandra 4.1 is intrinsically an LWW system**: it uses timestamps for value-level conflict resolution. On one hand this experiment uses Cassandra as the operation-log platform carrying the paper model (core path); on the other hand it provides an **optional real physical partition experiment** (E6b) that measures divergence of Cassandra's intrinsic LWW behavior under real partitions and quantifies it with τ.
5. **No global-total-order assumption**: consistent with the paper, none of the evaluation metrics depend on a global ground-truth total order.

---

## 3. Overall architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Docker host (local)                        │
│                                                                    │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│   │ cass-1   │ │ cass-2   │ │ cass-3   │ │ cass-4   │             │
│   │ (seed)   │ │          │ │          │ │          │             │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘             │
│        └────────── ktau-net (bridge; can stop/start nodes to partition) ──┘
│                                                                    │
│   ┌───────────────────────────────────────────────────────────┐   │
│   │ coordinator (Python experiment driver, runs in local venv)  │   │
│   │   fetch_trace → ingest_trace → scenario_gen → run_experiments│ │
│   │   tau / ranked_pairs / kemeny_exact / baselines / monitor  │   │
│   │   perf_collect / analyze_report                            │   │
│   └───────────────────────────────────────────────────────────┘   │
│        │ CQL driver(9042)          │ docker stats(host side)       │
└──────────────────────────────────────────────────────────────────┘
```

**Component responsibilities**

| Component | Description |
|------|------|
| cass-1..4 | Cassandra 4.1 cluster (RF=2), stores raw trace data, per-logical-replica local logs, monitoring time series |
| coordinator | Core experiment logic (Python + cassandra-driver): data fetch, ingest, scenario generation, merge algorithms, τ computation, monitoring, performance collection, analysis and figures |
| host-side scripts | Periodic `docker stats` sampling (CPU/memory/network IO), time-aligned with experiments |
| data flow | trace file → raw log table → derived operations/causal graph → per-replica local log tables → merge/metrics → result CSVs → figures/reports |

**Key design decision**: merge algorithms (Ranked Pairs / LWW / CRDT) run in the coordinator, which reads each logical replica's log, merges into a total order σ, then computes τ and the remaining metrics — consistent with the paper's §6 experimental paradigm; Cassandra provides real log storage, replication, and concurrent write pressure, giving the "real database" platform property.

---

## 4. Environment setup plan

### 4.1 Cluster topology and hardware resource allocation

Default: 4-node Cassandra cluster + 1 coordinator process (local host). Resources can be adjusted in `.env`.

| Container | Image | vCPU | Memory | Heap | Role |
|------|------|------|------|--------|------|
| cass-1 | cassandra:4.1 | 2 | 3 GB | MAX_HEAP_SIZE=1G | seed |
| cass-2 | cassandra:4.1 | 2 | 3 GB | MAX_HEAP_SIZE=1G | data node |
| cass-3 | cassandra:4.1 | 2 | 3 GB | MAX_HEAP_SIZE=1G | data node (partition experiment target) |
| cass-4 | cassandra:4.1 | 2 | 3 GB | MAX_HEAP_SIZE=1G | data node |
| coordinator | local Python 3.11 venv | 1 | 1 GB | — | experiment driver |

> The minimum cluster size is 3 nodes (1 seed + 2). The default 4 nodes leave headroom for RF=2 + the partition experiment (the cluster still serves after isolating 1 node). If local memory is tight, reduce to 3 nodes (RF=2 still satisfies post-partition quorum semantics).

### 4.2 docker-compose.yml design points

```yaml
# Key configuration (final file at ktau_cassandra_experiment/docker-compose.yml)
services:
  cass-1:
    image: cassandra:4.1
    container_name: ktau-cass-1
    environment:
      CASSANDRA_CLUSTER_NAME: ktau
      CASSANDRA_SEEDS: cass-1
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack1
      MAX_HEAP_SIZE: 1G
      HEAP_NEWSIZE: 256M
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
    ports: ["9042:9042", "7000:7000"]
    deploy: { resources: { limits: { cpus: "2.0", memory: 3G } } }
    healthcheck:
      test: ["CMD-SHELL", "cqlsh -e 'select release_version from system.local' >/dev/null 2>&1"]
      interval: 30s
      retries: 30
  cass-2/3/4:  # CASSANDRA_SEEDS: cass-1, no port mapping or internal only
    ...
networks:
  ktau-net: { driver: bridge }
```

- Cluster readiness: `nodetool status` all `UN` + `cqlsh` healthcheck passing.
- Network partition control (E6b physical partition): `docker network disconnect ktau-net ktau-cass-3` / `connect`, controllable and reversible.
- Clock-skew/noise injection (optional): `tc netem` (inject delay and jitter via `nsenter`/`tc` inside `docker exec`), used to verify τ rises under LWW with clock skew.

### 4.3 Environment initialization flow (Phase 0)

1. `docker compose up -d` → wait for the cluster to be UN;
2. `init_cluster.py`: create keyspace `ktau` (SimpleStrategy, RF=2), all data tables (§5.5), materialized views and indexes;
3. Baseline connectivity validation: CQL ping per node + `nodetool status` snapshot written to `results/env_snapshot.csv`.

---

## 5. Data layer: Loghub trace acquisition and ingest

### 5.1 Dataset selection and format

**Default BGL (Blue Gene/L)**, from Loghub (user-specified gitcode mirror):
- Scale: 4,747,963 messages (≈708 MB), spanning ~7 months;
- Line format (space-separated 9 fields): `Label Timestamp Date Node NodeRepeat Type Component Level Content`
  - `Label`: `-` means normal; a positive integer means alert/anomaly (this experiment reuses it for "operation semantic type");
  - `Timestamp`: `yyyy-mm-dd-hh.mm.ss.uuuuuu`;
  - `Node`: e.g., `R01-M1-N0-C:J16-U01` — **naturally corresponds to a logical replica id**;
  - `Type` (e.g., 41/150), `Component` (e.g., rpcserv), `Level` (INFO/WARN/ERROR/FATAL/SEVERE).
- Backup dataset: **HDFS** (Hadoop distributed file system logs, closer to "distributed storage/database" semantics), switchable with `--dataset hdfs`.

### 5.2 Automated fetch script `fetch_trace.py`

Multi-source sequential fallback; stops on the first success; only well-formed content is ingested:

| Priority | Source | Description |
|--------|----|------|
| 1 | gitcode mirror (user-specified) | `https://gitcode.com/gh_mirrors/lo/loghub/raw/master/BGL/BGL.log*` |
| 2 | GitHub raw (logpai/loghub) | raw files under the BGL directory |
| 3 | Zenodo official archive | Loghub official DOI archive (BGL.tar.gz), the true source of the dataset |

- Supports resumable download, `--max-lines` (default 500k lines, configurable, controls experiment scale) and line/field count validation;
- If all sources are unreachable: explicit warning + fallback to a **synthetic trace generator** (same format), keeping the experiment pipeline unbroken, with the data source marked in the report.

### 5.3 Log → operation-log mapping (key design decision)

| BGL field | Maps to | Description |
|----------|--------|------|
| Each log line | one operation op | obtains a globally unique op_id |
| Timestamp | operation occurrence time | basis for LWW timestamps and causal edges |
| Node | owning logical replica | operations on the same Node in order = local order |
| Level / Label | operation semantic type | INFO→`incr` (commutative); WARN/ERROR→`set`; FATAL/SEVERE/alert→`cas` (conditional, non-commutative) |
| (Node, Type) | conflict key | same-key concurrent non-commutative operations form a conflict group |
| Content | semantic payload | basis for judging CAS semantic validity (relative to the issuing replica's local state) |

**Causal graph construction** (paper §4.1 model implementation):
- Within a Node: the sequential log forms happens-before edges (high causal density);
- Across Nodes: edges are added with probability p by time-window similarity, thereby **tuning the global causal density** (default targets: low conflict 35%, high conflict 10%, aligned with paper §6 settings);
- Each operation is assigned a vector clock (dependencies + local counter).

**Conflict groups**: concurrency-graph connected components; operations across groups are causally ordered and can be merged by fast-forward; only operations within a group need reconciliation. Both the paper and measurements show conflict groups are usually much smaller than the full divergent set.

### 5.4 Scenario generator `scenario_gen.py`

For each logical replica i (i=1..N), generate local log Li (aligned with paper §6.1 workload model):
1. take a **causally consistent subsequence** of the full operation set (topological-order sampling, with a drop ratio from observation noise);
2. apply **adjacent-swap noise** to concurrent pairs (arrival jitter, `--noise`);
3. set a per-replica **clock skew δi** (`--skew`); LWW timestamp = local sequence position + offset;
4. output: per-replica logs (written to the Cassandra `replica_logs` table) + scenario metadata (causal density, concurrency graph, conflict-group partition, ground-truth constraint set).

### 5.5 Cassandra Schema (keyspace `ktau`)

| Table | Primary key | Purpose |
|----|------|------|
| `trace_raw` | (source, line_no) | raw trace lines (reproducible) |
| `trace_ops` | (dataset, op_id) | parsed operations: type, timestamp, node, key, semantic payload |
| `causal_edges` | (dataset, src, dst) | causal graph edge set (for τcausal validation) |
| `replica_logs` | (trial, replica, seq) CLUSTERING | per-trial per-replica local logs |
| `merge_results` | (trial, strategy, group_id) | per-strategy merge results and metrics |
| `monitor_series` | (trial, sample_ts, replica) | real-time τ monitoring time series |
| `perf_samples` | (phase, ts) | docker stats + latency + throughput samples |

---

## 6. Software module design (`ktau_cassandra_experiment/scripts/`)

### 6.1 τ distance module `tau.py` (paper §5.1)

- `tau(σ, Li)`: `|{(a,b)∈D² : a≻_σ b ∧ b≻_Li a}|` — pairwise inversion count;
- `tau_total(σ) = Σ_i τ(σ, Li)`; normalized `τ̂ = τ_total / (N·M(M−1)/2)`; **information retention = 1 − τ̂**;
- **Causal decomposition** (paper Prop 2): `τ_total = τ_causal + τ_contested`; each violated consistent causal constraint a→b contributes exactly n_{a,b};
- Auxiliary: per-replica distance vector d_i (for Gini fairness), Prop 1 upper-bound self-check (observed 1−τ̂ ≥ 0.5).
- Implementation notes: pairwise comparisons accelerated by indexing (inverted index on op positions), complexity O(M²N) (for τ_total); incremental updates in the monitoring scenario.

### 6.2 Ranked Pairs module `ranked_pairs.py` (Tideman algorithm)

1. For each operation pair, compute margin(a,b)=n(a≻b)−n(b≻a);
2. Lock edges in descending margin order; skip edges that create cycles (union-find cycle detection);
3. Output total order σ (for operations within a conflict group; groups are joined causally by fast-forward);
4. Complexity O(M² log M), consistent with paper §7.

### 6.3 Exact Kemeny reference `kemeny_exact.py` (for validation, M≤8)

- Brute-force enumeration over M! permutations for `arg min Σ τ(σ,Li)`;
- Used in E3: quantify the gap between RP and the theoretical optimum (aligned with paper §6.2: at M=8, 62% exact, average excess ≤1.6%).

### 6.4 Baseline algorithms `baselines.py`

| Strategy | Implementation | Expected behavior (paper §5.4/§6.4) |
|------|------|------|
| Leader overwrite (optional) | retain majority-partition operations, in leader order | low operation retention (truncation); τ low only on surviving operations |
| LWW (required) | sort by (replica clock + offset) timestamps | fully automatic, full retention; low information retention (timestamp fiat) |
| Pure CRDT (required) | merge only commutative (incr) operations; mark non-commutative concurrent writes pending | semantically perfect but narrow coverage (drops sharply under high conflict) |
| CRDT + LWW fallback (required) | commutative via CRDT, non-commutative falls back to LWW | full coverage but LWW quality |
| Vector Clock (optional) | guarantee causal edges only; random tie-break on concurrent pairs | τcausal=0, high τcontested, extremely low automation coverage |
| Ranked Pairs (primary) | §6.2 | full retention, fully automatic, highest information retention |

### 6.5 Real-time τ monitoring module `monitor.py` (paper §2.4/§8.4 direction)

- A background thread incrementally reads each replica's log from `replica_logs` every Δ (default 1s), computing:
  - current τ̂ (relative to the current optimal merged order / majority order), per-replica τ distance, Gini;
  - Jaccard similarity with the operation set (auxiliary, to distinguish "degraded" from "fully partitioned" phases);
- The time series is written to `monitor_series` and also printed to stdout;
- **Alerting mechanism**: an alert fires when τ̂ exceeds threshold θ (default 0.05), and the detection latency is recorded;
- Compared with the paper's "binary lag metric": also outputs the maximum replica lag (in operations), validating τ's **sub-threshold detection** capability (τ rises before order-of-magnitude divergence appears).

### 6.6 Performance and resource collection `perf_collect.py` + host-side scripts

- Throughput: CQL writes (batch/sync) ops/s, merge throughput (M ops/ms);
- Module runtime: `time.perf_counter` records runtime of τ_total, RP, LWW, exact Kemeny, per-replica τ (p50/p95/p99);
- Resources: host-side 2s sampling of `docker stats` (CPU%, memory, network IO), timestamps aligned with experiments;
- Network latency: client CQL round-trip RTT (p50/p95) + optional `tc netem` injected skew scenarios;
- All results are written to `results/` (CSV).

### 6.7 Analysis and figures `analyze_report.py`

Generates: causal decomposition bar chart, end-to-end comparison (radar/table), non-commutative ratio sweep, minority-size sweep, τ̂ time series (monitoring), runtime-vs-scale log-log plot; and produces a LaTeX/Markdown experiment report draft.

---

## 7. Experiment flow (phases)

```
Phase 0 environment init  →  Phase 1 data ingest  →  Phase 2 scenario generation
Phase 3 experiment execution (E1–E6)  →  Phase 4 results/performance collection  →  Phase 5 analysis and report
```

Each phase has an independent script + result validation (e.g., row counts, τ range [0,1], Prop 1 upper-bound self-check, fixed random seeds for reproducibility).

---

## 8. Experiment matrix and expected results

**Common defaults**: N=8 logical replicas, M=24/group (main experiments), M≤8 (validation experiments), trial=30, low conflict (35% causal, 7:3 partition) / high conflict (10% causal, 4:3:3 partition).

| Experiment | Design | Key metrics | Expected (vs paper) |
|------|------|---------|-----------------|
| **E1 causal decomposition validation** | decompose τ_total under low/high conflict for six strategies | τ_causal, τ_contested, τ̂ | τ_causal=0 for all strategies; τ_contested grows 27–50% under high conflict (paper §6.3) |
| **E2 end-to-end comparison** | all strategies under high conflict | retention, automation coverage, info retention, causal violations, semantic validity, Gini | RP highest info retention (paper: 63.9% vs LWW 58.1% vs VC 52.5%); baselines exhibit the structural failure modes predicted by paper §5.4 |
| **E3 RP vs exact Kemeny** | M=4..8 brute-force comparison | RP exact rate, average τ excess rate | RP 62–100% exact, excess ≤1.6% (paper §6.2) |
| **E4 monitoring real-time/sensitivity** | steady state → gradual divergence injection (write-rate/replica-disagreement sweep) | τ̂ trajectory, detection latency, false-alarm rate (steady), sub-threshold detection | τ̂ rises monotonically with divergence; τ detects gradual divergence earlier than binary lag (paper §2.4/§8.4) |
| **E5 performance and scalability** | conflict-group size M=5..100 sweep | τ/RP runtime, merge throughput, CQL ops/s, CPU/memory, RTT | RP sub-millisecond (M≤15), hundreds of ms at M=100; O(M² log M) (paper §6.7) |
| **E6a partition asymmetry** | minority partition 10%→50% sweep | leader overwrite retention, RP vs LWW info retention | retention = majority share one-to-one; RP stably beats LWW by 4–5 points (paper §6.6) |
| **E6b real physical partition (optional)** | `docker network disconnect` isolates cass-3, bidirectional writes, measure after healing | per-key value versions per node, τ measures intrinsic LWW divergence | validates real Cassandra LWW behavior + measurability of its divergence with τ |

---

## 9. Fair-comparison protocol for controlled experiments

1. **Same input**: all algorithms consume exactly the same replica log set (same trial, same seed); same M/N/noise/skew implementation;
2. **Same environment**: within a round, algorithms run sequentially in the same coordinator to avoid resource-competition bias; runtime uses `perf_counter`, taking percentiles over multiple runs;
3. **Same metrics**: all metrics are uniformly computed by `metrics.py`, eliminating caliber differences;
4. **Statistical tests**: key differences such as RP vs LWW undergo paired Wilcoxon signed-rank tests + 95% CI (bootstrap), rather than mean-only comparison;
5. **Random seed management**: the global seed is fixed (default 42, overridable); all trials are reproducible.

---

## 10. Performance data collection checklist

| Category | Metric | Collection method |
|------|------|---------|
| Throughput | ingest ops/s, scenario-write ops/s, CQL batch-write ops/s, merge throughput ops/ms | coordinator counting + timing |
| Algorithm runtime | τ_total, per-replica τ, RP, LWW, VC, exact Kemeny (M≤8) | perf_counter, p50/p95/p99 |
| Resources | per-node CPU%, memory, network IO (rx/tx) | host-side `docker stats` 2s sampling |
| Network | client CQL RTT p50/p95; optional RTT distribution under netem injection | client measurement |
| Correctness | retention/automation coverage/info retention/causal violations/semantic validity/Gini/detection latency/false-alarm rate | `metrics.py` |

---

## 11. Result analysis and report deliverables

- **Check paper conclusions item by item** (the expected column of the §8 matrix), quantifying agreement/discrepancy and explaining (workload differences are the expected source of discrepancy);
- Output: `results/` (raw CSVs + figures) + `docs/experiment_report.md` (experiment design, execution, result analysis, conclusions);
- Answer explicitly: whether τ measures inconsistency accurately and sensitively, whether RP is effective and efficient, whether monitoring is real-time and reliable, and τ's superiority and boundaries vs LWW/CRDT.

---

## 12. Risks and mitigations

| Risk | Mitigation |
|------|------|
| gitcode/Zenodo fetch failure | multi-source fallback + synthetic trace fallback (source marked in report) |
| insufficient local resources (4×3G memory) | 3-node downgrade config + `.env` tuning |
| BGL semantic-mapping distortion | document mapping decisions; cross-validate with the HDFS backup dataset |
| high RP runtime at large M | E5 sets an explicit scale bound (M=100 is the extreme case) and reports actual O(M² log M) |
| monitoring incremental updates introducing bias | cross-validate incremental vs full τ (full recomputation every 10 samples) |

---

## 13. Deliverables checklist

1. `ktau_cassandra_experiment/`: docker-compose.yml, config.yaml, all Python modules
2. Loghub fetch script and ingested data (trace_raw / trace_ops / replica_logs in Cassandra)
3. `results/`: raw data CSVs + all figures + performance samples
4. `docs/experiment_design_report.md` (this document) + `docs/experiment_report.md` (final report)

---

## 14. Decisions pending confirmation (to be decided at review)

1. **Is "CV" confirmed as CRDT**? And should the optional extensions (VC / Leader overwrite / exact Kemeny) be enabled — recommended to enable, low cost and fully reproduces paper Tables 3/4;
2. **Cluster size**: does 4 nodes (2 vCPU/3G/node) fit local resources? Can be reduced to 3 nodes;
3. **Dataset**: default BGL; should the HDFS dataset also be run for cross-validation?
4. **Experiment parameters**: are N=8, M=24, trial=30, monitoring Δ=1s acceptable?
5. **Real physical partition experiment E6b** (`docker network disconnect`): should it be included as required scope?
