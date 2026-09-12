# Kendall τ 日志协调验证实验 —— 实验设计报告

> 论文依据：《Kendall Tau Distance as a Quality Metric for Diverged Log Reconciliation》（Haoyang Chen, ICSDC）
> 实验平台：Docker + Cassandra 4.1（`cassandra:4.1`，已验证本地镜像可用）
> 数据来源：Loghub BGL 真实日志 trace（gitcode 镜像 → GitHub → Zenodo 多源回退）
> 版本：v0.1（待审阅）

---

## 1. 实验目标

依据论文核心观点——**Kendall τ 距离可作为后分区日志协调质量的统一度量**，本实验用**真实日志 trace（Loghub BGL）+ 真实数据库平台（Cassandra 4.1 集群）**系统性验证以下论断：

| 编号 | 验证目标 | 对应论文论断 |
|------|---------|-------------|
| G1 | τ 距离衡量日志不一致的能力（准确性 + 敏感性） | §5.1 度量定义、§5.3 因果分解、§5.5 细粒度判别 |
| G2 | Ranked Pairs 后分区合并的有效性与效率 | §5.3.3、§6.2、§6.7 |
| G3 | τ 实时监控的不一致检测实时性与可靠性 | §2.4（monitoring gap）、§8.4 future work |
| G4 | 系统性论证 τ 的合理性（理论依据 + 实际表现） | §5 全章、§6.8 结论 |
| G5 | 对照实验：CRDT（纯 + LWW 回退）、LWW 等基线 | §6.4、§6.5 |
| G6 | 性能数据：吞吐、算法耗时、资源利用率、网络延迟 | §6.7、§7.2 |

---

## 2. 前提假设与术语澄清

1. **"CV" = CRDT（Conflict-free Replicated Data Types）**：需求 4 中"CV"为笔误，本报告按 CRDT 设计；同时实现 **LWW**、**CRDT（纯）**、**CRDT+LWW 回退**、**Ranked Pairs** 四者必选，另提供 **Vector Clock（VC）**、**Leader overwrite**、**精确 Kemeny** 三个低成本扩展对照（推荐启用，用于复现论文表 3/表 4 全貌）。
2. **逻辑副本 vs 物理节点**：Cassandra 集群是**执行/存储平台**；论文模型中的 N 个"副本日志"是**逻辑副本**，其局部日志表存放在 Cassandra 中。二者解耦，既忠实论文模型，又控制物理资源开销（默认 N=8 逻辑副本、4 个物理节点）。
3. **BGL 是超算日志而非数据库日志**：Loghub BGL（Blue Gene/L 超算）是公开最常用的真实系统日志 benchmark。本实验将其**重新语义化为分布式存储的操作日志**（见 §5.3 映射），满足"真实 trace 驱动"且忠实论文"操作日志协调"模型。
4. **Cassandra 4.1 本征是 LWW 系统**：其自身用时间戳做值级冲突解决。本实验一方面把 Cassandra 作为承载论文模型的操作日志平台（核心路径），另一方面提供**可选的真实物理分区实验**（E6b），测量 Cassandra 本征 LWW 行为在真实分区下的发散，并用 τ 度量之。
5. **无全局真序假设**：与论文一致，评估指标均不依赖全局 ground-truth 总序。

---

## 3. 总体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        Docker 主机（本机）                          │
│                                                                    │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│   │ cass-1   │ │ cass-2   │ │ cass-3   │ │ cass-4   │             │
│   │ (seed)   │ │          │ │          │ │          │             │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘             │
│        └────────── ktau-net（bridge，可对节点启停分区）────────┘    │
│                                                                    │
│   ┌───────────────────────────────────────────────────────────┐   │
│   │ coordinator（Python 实验驱动器，运行于本机 venv）            │   │
│   │   fetch_trace → ingest_trace → scenario_gen → run_experiments│ │
│   │   tau / ranked_pairs / kemeny_exact / baselines / monitor  │   │
│   │   perf_collect / analyze_report                            │   │
│   └───────────────────────────────────────────────────────────┘   │
│        │ CQL driver(9042)          │ docker stats(宿主机侧)        │
└──────────────────────────────────────────────────────────────────┘
```

**组件职责**

| 组件 | 说明 |
|------|------|
| cass-1..4 | Cassandra 4.1 集群（RF=2），承载 trace 原始数据、各逻辑副本局部日志、监控时间序列 |
| coordinator | 核心实验逻辑（Python + cassandra-driver）：数据拉取、导入、场景生成、合并算法、τ 计算、监控、性能采集、分析出图 |
| host 侧脚本 | `docker stats` 周期采样（CPU/内存/网络 IO），与实验时间戳对齐 |
| 数据流 | trace 文件 → 原始日志表 → 派生操作/因果图 → 各副本局部日志表 → 合并/度量 → 结果 CSV → 图表/报告 |

**关键设计决策**：合并算法（Ranked Pairs / LWW / CRDT）运行在 coordinator 中，读取各逻辑副本日志后合并出总序 σ，再计算 τ 与其余指标——与论文 §6 的实验范式一致；Cassandra 负责真实的日志存储、复制与并发写入压力，提供"真实数据库"平台属性。

---

## 4. 环境搭建方案

### 4.1 集群拓扑与硬件资源分配

默认 4 节点 Cassandra 集群 + 1 个 coordinator 进程（本机）。资源可在 `.env` 中调整。

| 容器 | 镜像 | vCPU | 内存 | 堆内存 | 角色 |
|------|------|------|------|--------|------|
| cass-1 | cassandra:4.1 | 2 | 3 GB | MAX_HEAP_SIZE=1G | seed |
| cass-2 | cassandra:4.1 | 2 | 3 GB | MAX_HEAP_SIZE=1G | 数据节点 |
| cass-3 | cassandra:4.1 | 2 | 3 GB | MAX_HEAP_SIZE=1G | 数据节点（分区实验靶点） |
| cass-4 | cassandra:4.1 | 2 | 3 GB | MAX_HEAP_SIZE=1G | 数据节点 |
| coordinator | 本机 Python 3.11 venv | 1 | 1 GB | — | 实验驱动器 |

> 集群最小规模为 3 节点（1 seed + 2）。默认 4 节点为 RF=2 + 分区实验（隔离 1 节点后集群仍可服务）留出余量。若本机内存紧张可降为 3 节点（RF=2 时仍满足分区后 quorum 语义）。

### 4.2 docker-compose.yml 设计要点

```yaml
# 关键配置（最终文件在 ktau_cassandra_experiment/docker-compose.yml）
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
  cass-2/3/4:  # CASSANDRA_SEEDS: cass-1, 无端口映射或仅内部
    ...
networks:
  ktau-net: { driver: bridge }
```

- 集群就绪判定：`nodetool status` 全部 `UN` + `cqlsh` healthcheck 通过。
- 网络分区控制（E6b 物理分区）：`docker network disconnect ktau-net ktau-cass-3` / `connect`，可控、可逆。
- 时钟偏移/噪声注入（可选）：`tc netem`（`docker exec` 内以 `nsenter`/`tc` 注入延迟与抖动），用于验证 LWW 在时钟偏移下 τ 升高。

### 4.3 环境初始化流程（Phase 0）

1. `docker compose up -d` → 等待集群 UN；
2. `init_cluster.py`：创建 keyspace `ktau`（SimpleStrategy, RF=2）、全部数据表（§5.5）、物化视图与索引；
3. 基线连通性验证：各节点 CQL ping + `nodetool status` 快照写入 `results/env_snapshot.csv`。

---

## 5. 数据层：Loghub Trace 获取与导入

### 5.1 数据集选择与格式

**默认 BGL（Blue Gene/L）**，来自 Loghub（用户指定 gitcode 镜像）：
- 规模：4,747,963 条消息（约 708 MB），时间跨度约 7 个月；
- 行格式（空格分隔 9 字段）：`Label Timestamp Date Node NodeRepeat Type Component Level Content`
  - `Label`：`-` 表示正常；正整数表示告警/异常（本实验将其重用于"操作语义类型"）；
  - `Timestamp`：`yyyy-mm-dd-hh.mm.ss.uuuuuu`；
  - `Node`：如 `R01-M1-N0-C:J16-U01` —— **天然对应逻辑副本编号**；
  - `Type`（如 41/150）、`Component`（如 rpcserv）、`Level`（INFO/WARN/ERROR/FATAL/SEVERE）。
- 备选数据集：**HDFS**（Hadoop 分布式文件系统日志，更接近"分布式存储/数据库"语义），支持 `--dataset hdfs` 一键切换。

### 5.2 自动化拉取脚本 `fetch_trace.py`

多源顺序回退，任一源成功即停；格式校验通过后才入库：

| 优先级 | 源 | 说明 |
|--------|----|------|
| 1 | gitcode 镜像（用户指定） | `https://gitcode.com/gh_mirrors/lo/loghub/raw/master/BGL/BGL.log*` |
| 2 | GitHub raw（logpai/loghub） | BGL 目录下 raw 文件 |
| 3 | Zenodo 官方归档 | Loghub 官方 DOI 归档（BGL.tar.gz），数据集真源 |

- 支持断点续传、`--max-lines`（默认 500k 行，可配置，控制实验规模）与行数/字段数校验；
- 全部源不可达时：显式告警 + 回退到**合成 trace 生成器**（同格式），保证实验流程不中断，并在报告中标注数据来源。

### 5.3 日志 → 操作日志的映射（关键设计决策）

| BGL 字段 | 映射为 | 说明 |
|----------|--------|------|
| 每条日志行 | 一个操作 op | 获得全局唯一 op_id |
| Timestamp | 操作发生时间 | 构造 LWW 时间戳 + 因果边的基础 |
| Node | 归属逻辑副本 | 同 Node 上操作顺序 = 本地顺序 |
| Level / Label | 操作语义类型 | INFO→`incr`（可交换）；WARN/ERROR→`set`；FATAL/SEVERE/告警→`cas`（条件、不可交换） |
| (Node, Type) | 冲突键 key | 同 key 并发不可交换操作构成冲突组 |
| Content | 语义载荷 | CAS 语义有效性的判定依据（相对发布副本本地状态） |

**因果图构建**（论文 §4.1 模型落地）：
- 同 Node 内：顺序日志构成 happens-before 边（高因果密度）；
- 跨 Node：按时间窗相似性以概率 p 添加边，从而**调节全局因果密度**（默认目标：低冲突 35%、高冲突 10%，对齐论文 §6 设置）；
- 每操作赋予向量时钟（依赖 + 本地计数器）。

**冲突组**：并发图连通分量；组间操作因果有序、可 fast-forward 合并；仅组内操作需协调。论文与实测均表明冲突组通常远小于发散全集。

### 5.4 场景生成器 `scenario_gen.py`

对每个逻辑副本 i（i=1..N）生成局部日志 Li（对齐论文 §6.1 workload 模型）：
1. 取操作全集的一个**因果一致子序列**（拓扑序采样，含观测噪声丢弃比例）；
2. 对并发对施加**相邻对换噪声**（到达抖动，`--noise`）；
3. 为每副本设定**时钟偏移 δi**（`--skew`），LWW 时间戳 = 本地顺序位置 + 偏移；
4. 输出：各副本日志（写入 Cassandra `replica_logs` 表）+ 场景元数据（因果密度、并发图、冲突组划分、真值约束集合）。

### 5.5 Cassandra Schema（keyspace `ktau`）

| 表 | 主键 | 用途 |
|----|------|------|
| `trace_raw` | (source, line_no) | 原始 trace 行（可复现） |
| `trace_ops` | (dataset, op_id) | 解析后的操作：类型、时间戳、node、key、语义载荷 |
| `causal_edges` | (dataset, src, dst) | 因果图边集（用于 τcausal 验证） |
| `replica_logs` | (trial, replica, seq) CLUSTERING | 每 trial 每副本的局部日志 |
| `merge_results` | (trial, strategy, group_id) | 各策略合并结果与指标 |
| `monitor_series` | (trial, sample_ts, replica) | τ 实时监控时间序列 |
| `perf_samples` | (phase, ts) | docker stats + 延迟 + 吞吐采样 |

---

## 6. 软件模块设计（`ktau_cassandra_experiment/scripts/`）

### 6.1 τ 距离模块 `tau.py`（论文 §5.1）

- `tau(σ, Li)`：`|{(a,b)∈D² : a≻_σ b ∧ b≻_Li a}|` —— 成对逆序计数；
- `tau_total(σ) = Σ_i τ(σ, Li)`；归一化 `τ̂ = τ_total / (N·M(M−1)/2)`；**信息保留率 = 1 − τ̂**；
- **因果分解**（论文 Prop 2）：`τ_total = τ_causal + τ_contested`；每个被违反的一致因果约束 a→b 精确贡献 n_{a,b}；
- 辅助：每副本距离向量 d_i（供 Gini 公平性计算）、Prop 1 上界自检（观测 1−τ̂ ≥ 0.5）。
- 实现要点：成对比较用索引加速（按 op 位置的倒排），复杂度 O(M²N)（对 τ_total），监控场景用增量更新。

### 6.2 Ranked Pairs 模块 `ranked_pairs.py`（Tideman 算法）

1. 对每个操作对统计 margin(a,b)=n(a≻b)−n(b≻a)；
2. 按 margin 降序锁定边；若成环则跳过（并查集判环）；
3. 输出总序 σ（对冲突组内操作；组间因果快进拼接）；
4. 复杂度 O(M² log M)，与论文 §7 一致。

### 6.3 精确 Kemeny 参考 `kemeny_exact.py`（验证用，M≤8）

- 暴力枚举 M! 全排列求 `arg min Σ τ(σ,Li)`；
- 用于 E3：量化 RP 与理论最优的差距（对齐论文 §6.2：M=8 时 62% 精确、平均超差 ≤1.6%）。

### 6.4 基线算法 `baselines.py`

| 策略 | 实现 | 预期行为（论文 §5.4/§6.4） |
|------|------|------|
| Leader overwrite（可选） | 保留多数派分区操作、按 leader 顺序 | 操作保留率低（截断），τ 只在幸存操作上低 |
| LWW（必选） | 按（副本时钟+偏移）时间戳排序 | 全自动、全保留，信息保留率低（timestamp fiat） |
| Pure CRDT（必选） | 仅合并可交换（incr）操作；不可交换并发写标记未决 | 语义完美但覆盖窄（高冲突下骤降） |
| CRDT + LWW 回退（必选） | 可交换走 CRDT，不可交换回退 LWW | 全覆盖但 LWW 质量 |
| Vector Clock（可选） | 只保证因果边，并发对随机 tie-break | τcausal=0，τcontested 高，自动化覆盖率极低 |
| Ranked Pairs（主策略） | §6.2 | 全保留、全自动、最高信息保留 |

### 6.5 τ 实时监控模块 `monitor.py`（论文 §2.4/§8.4 方向落地）

- 后台线程每 Δ（默认 1s）从 `replica_logs` 增量读取各副本日志，计算：
  - 当前 τ̂（相对当前最优合并序 / 多数派序）、每副本 τ 距离、Gini；
  - 与操作集 Jaccard 相似度（辅助区分"降级"与"完全分区"阶段）；
- 时间序列写入 `monitor_series`，同时 stdout 输出；
- **报警机制**：τ̂ 超阈值 θ（默认 0.05）触发告警，记录检测延迟；
- 与论文"binary lag 度量"对比：同时输出最大副本滞后（条数），验证 τ 的**亚阈值检测**能力（τ 在数量级分歧出现前即上升）。

### 6.6 性能与资源采集 `perf_collect.py` + host 侧脚本

- 吞吐：CQL 写入（批量/同步）ops/s、合并吞吐（M ops/ms）；
- 模块耗时：`time.perf_counter` 记录 τ_total、RP、LWW、精确 Kemeny、每副本 τ 的耗时（p50/p95/p99）；
- 资源：host 侧 2s 采样 `docker stats`（CPU%、内存、网络 IO），时间戳与实验对齐；
- 网络延迟：客户端 CQL 往返 RTT（p50/p95）+ 可选 `tc netem` 注入的偏移场景；
- 全部落盘 `results/`（CSV）。

### 6.7 分析与出图 `analyze_report.py`

生成：因果分解柱状图、端到端对比（雷达/表）、非可交换占比扫描、少数派规模扫描、τ̂ 时间序列（监控）、耗时-规模双对数图；并产出 LaTeX/Markdown 实验报告草稿。

---

## 7. 实验流程（阶段划分）

```
Phase 0 环境初始化  →  Phase 1 数据导入  →  Phase 2 场景生成
Phase 3 实验执行(E1–E6)  →  Phase 4 结果/性能收集  →  Phase 5 分析出报告
```

每阶段有独立脚本 + 结果校验（如数据行数、τ 值域 [0,1]、Prop 1 上界自检、随机种子固定保证可复现）。

---

## 8. 实验矩阵与预期结果

**公共默认**：N=8 逻辑副本、M=24/组（主实验）、M≤8（验证实验）、trial=30、低冲突(35% 因果, 7:3 分区) / 高冲突(10% 因果, 4:3:3 分区)。

| 实验 | 设计 | 关键指标 | 预期（对照论文） |
|------|------|---------|-----------------|
| **E1 因果分解验证** | 六策略在低/高冲突下分解 τ_total | τ_causal、τ_contested、τ̂ | 全策略 τ_causal=0；高冲突下 τ_contested 增长 27–50%（论文 §6.3） |
| **E2 端到端对比** | 高冲突下全部策略 | 保留率、自动化覆盖、信息保留、因果违反、语义有效、Gini | RP 信息保留最高（论文：63.9% vs LWW 58.1% vs VC 52.5%）；各基线呈现论文 §5.4 预测的结构性失败模式 |
| **E3 RP vs 精确 Kemeny** | M=4..8 暴力枚举对比 | RP 精确率、平均 τ 超差率 | RP 62–100% 精确、超差 ≤1.6%（论文 §6.2） |
| **E4 监控实时性/敏感性** | 稳态 → 逐步注入发散（写入速率/副本分歧度扫描） | τ̂ 轨迹、检测延迟、误报率（稳态）、亚阈值检测 | τ̂ 随分歧单调上升；τ 早于 binary lag 检测到渐进发散（论文 §2.4/§8.4） |
| **E5 性能与扩展性** | 冲突组规模 M=5..100 扫描 | τ/RP 耗时、合并吞吐、CQL ops/s、CPU/内存、RTT | RP 亚毫秒（M≤15）、M=100 数百 ms 量级；O(M² log M)（论文 §6.7） |
| **E6a 分区不对称** | 少数派分区 10%→50% 扫描 | leader overwrite 保留率、RP vs LWW 信息保留 | 保留率=多数派占比一一对应；RP 稳定超 LWW 4–5 点（论文 §6.6） |
| **E6b 真实物理分区（可选）** | `docker network disconnect` 隔离 cass-3，双向写入，愈合后测量 | 各节点每 key 值版本、τ 度量本征 LWW 发散 | 验证真实 Cassandra LWW 行为 + τ 对其发散的可测性 |

---

## 9. 对照实验公平性协议

1. **同输入**：所有算法消费完全相同副本日志集（同 trial 同种子）；同一 M/N/噪声/偏移实现；
2. **同环境**：同一轮次内算法顺序执行于同一 coordinator，避免资源竞争偏差；耗时用 `perf_counter`，多次取百分位；
3. **同度量**：统一由 `metrics.py` 计算全部指标，杜绝口径差异；
4. **统计检验**：RP vs LWW 等关键差异做配对 Wilcoxon 符号秩检验 + 95% CI（bootstrap），而非仅均值对比；
5. **随机种子管理**：全局 seed 固定（默认 42，可覆盖），全部 trial 可复现。

---

## 10. 性能数据收集清单

| 类别 | 指标 | 采集方式 |
|------|------|---------|
| 吞吐 | 导入 ops/s、场景写 ops/s、CQL 批量写 ops/s、合并吞吐 ops/ms | coordinator 计数 + 计时 |
| 算法耗时 | τ_total、每副本 τ、RP、LWW、VC、精确 Kemeny（M≤8） | perf_counter，p50/p95/p99 |
| 资源 | 各节点 CPU%、内存、网络 IO（rx/tx） | host 侧 `docker stats` 2s 采样 |
| 网络 | 客户端 CQL RTT p50/p95；可选 netem 注入下的 RTT 分布 | 客户端测量 |
| 正确性 | 保留率/自动化覆盖/信息保留/因果违反/语义有效/Gini/检测延迟/误报率 | `metrics.py` |

---

## 11. 结果分析与报告产出

- **对照论文结论逐条核对**（§8 矩阵预期列），量化一致/偏离之处并解释（工作负载差异为预期偏离来源）；
- 输出：`results/`（原始 CSV + 图）+ `docs/experiment_report.md`（实验设计、执行过程、结果分析、结论）；
- 明确回答：τ 是否准确敏感地度量不一致、RP 是否有效高效、监控是否实时可靠、τ 相比 LWW/CRDT 的优越性与边界。

---

## 12. 风险与缓解

| 风险 | 缓解 |
|------|------|
| gitcode/Zenodo 拉取失败 | 多源回退 + 合成 trace 兜底（报告标注来源） |
| 本机资源不足（4×3G 内存） | 3 节点降级配置 + `.env` 调参 |
| BGL 语义映射失真 | 文档化映射决策；备选 HDFS 数据集交叉验证 |
| 大规模 M 下 RP 耗时高 | E5 明确规模上限（M=100 为极端 case），并报告实际 O(M² log M) |
| 监控增量更新引入偏差 | 增量与全量 τ 交叉校验（每 10 个采样点全量复核一次） |

---

## 13. 交付物清单

1. `ktau_cassandra_experiment/`：docker-compose.yml、config.yaml、全部 Python 模块
2. Loghub 拉取脚本与导入数据（trace_raw / trace_ops / replica_logs 落于 Cassandra）
3. `results/`：原始数据 CSV + 全部图表 + 性能采样
4. `docs/experiment_design_report.md`（本文）+ `docs/experiment_report.md`（最终报告）

---

## 14. 待确认决策点（审阅时请拍板）

1. **"CV" 是否确认为 CRDT**？并是否启用可选扩展（VC / Leader overwrite / 精确 Kemeny）——推荐启用，成本低且完整复现论文表 3/表 4；
2. **集群规模**：4 节点（2 vCPU/3G/节点）是否适配本机资源？可降为 3 节点；
3. **数据集**：默认 BGL；是否同时运行 HDFS 数据集交叉验证？
4. **实验参数**：N=8、M=24、trial=30、监控 Δ=1s 是否接受？
5. **真实物理分区实验 E6b**（docker network disconnect）是否纳入必做范围？
