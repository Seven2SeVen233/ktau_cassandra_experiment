# Kendall-Tau Log Reconciliation Experiments

在 Cassandra 4.1 集群上用真实系统日志（Loghub BGL/HDFS）验证 **Kendall τ 距离**作为日志协调质量指标、以及 **Ranked Pairs** 作为后分区日志合并算法的完整实验项目。

对应论文：*Kendall Tau Distance as a Quality Metric for Diverged Log Reconciliation*。

核心论点：当网络分区愈合时，副本间的发散操作日志需要协调；Kendall τ 距离（合并日志与各副本本地历史之间的成对排序分歧数）可作为跨算法统一的质量度量，并能分解为"因果分量 + 争议分量"；Ranked Pairs 以多项式时间逼近精确 Kemeny 最优合并。

---

## 1. 目录结构

```
ktau_cassandra_experiment/
├── README.md                  # 本文件
├── run.py                     # 统一实验入口（一键复现）
├── config.yaml                # 全部实验参数（单一配置源）
├── docker-compose.yml         # Cassandra 4.1 集群拓扑（参数插值自 .env）
├── requirements.txt           # pip 依赖
├── environment.yml            # conda 环境定义
├── .env.example               # compose 环境变量模板（提交用）
├── .env                       # 由 prepare_env.py 生成，不入库
├── .gitignore
├── data/                      # Loghub 日志数据集（含版权说明）
│   ├── README.md
│   ├── BGL_2k.log             # BlueGene/L 日志（默认数据集）
│   └── HDFS_2k.log            # Hadoop 日志（备用数据集）
├── scripts/                   # 源代码
│   ├── common.py              # 配置加载 / Cassandra 会话 / 路径
│   ├── tau.py                 # Kendall τ 距离、因果分解、Gini
│   ├── ranked_pairs.py        # Ranked Pairs（Tideman）合并
│   ├── kemeny_exact.py        # 精确 Kemeny（M≤8 暴力枚举，对照用）
│   ├── baselines.py           # LWW / Vector Clock / CRDT / Leader 基线
│   ├── metrics.py             # 质量指标（信息保留、语义有效性等）
│   ├── scenario_gen.py        # 从 trace 构造协调场景
│   ├── fetch_trace.py         # Loghub trace 自动化拉取（多源回退）
│   ├── init_cluster.py        # 初始化 keyspace 与数据表
│   ├── ingest_trace.py        # 解析并导入 trace（测吞吐）
│   ├── run_experiments.py     # E1–E6a 核心实验
│   ├── monitor.py             # E4 τ 实时监控
│   ├── perf_collect.py        # 资源利用率 / CQL 延迟采集
│   ├── analyze_results.py     # 汇总生成实验报告
│   ├── smoke_test.py          # 核心模块冒烟测试
│   └── prepare_env.py         # config.yaml → .env 同步
├── docs/                      # 实验设计与分析文档
│   ├── experiment_design_report.md
│   ├── experiment_deep_analysis.md
│   ├── paper_section_trace_validation.md
│   └── fig_e4_trajectory.png  # E4 监控轨迹图
├── results/                   # 实验结果（CSV 原始数据 + 汇总报告）
│   ├── experiment_report.md
│   └── e1_*.csv … e6a_*.csv / perf_*.csv
└── devtools/                  # 论文编辑/调试辅助脚本（非实验运行所需）
```

## 2. 环境要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Docker | ≥ 24 含 Compose v2 | 集群由容器承载 |
| Python | ≥ 3.10（已验证 3.13） | 客户端/算法 |
| Cassandra 镜像 | cassandra:4.1 | compose 内置 |

**pip 安装**

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
```

**conda 安装**

```bash
conda env create -f environment.yml
conda activate ktau-experiments
```

> 注：Python 3.12+ 移除了 `asyncore`，cassandra-driver 默认 reactor 不可用；`scripts/common.py` 已注入 asyncio shim，无需额外处理。

## 3. 配置说明（config.yaml）

所有实验参数集中于此文件，修改后运行 `python scripts/prepare_env.py` 将 docker 段同步到 `.env`（compose 自动读取）。

| 段 | 键 | 默认 | 说明 |
|---|---|---|---|
| `docker` | `image` | `cassandra:4.1` | 镜像名:标签 |
| | `cluster_name` | `ktau` | 集群名 / compose 项目名 |
| | `dc` / `rack` | `dc1` / `rack1` | Cassandra 拓扑 |
| | `network` | `ktau-net` | compose 网络名 |
| | `container_prefix` | `ktau-cass` | 容器名前缀（节点 i → `{prefix}-{i}`） |
| | `client_port` | `9042` | 宿主机映射端口 → 容器 9042 |
| | `heap_size` / `heap_newsize` | `1G` / `256M` | 每节点 JVM 堆 |
| | `cpu_limit` / `mem_limit` | `2.0` / `3G` | 每节点资源上限 |
| `cluster` | `contact_points` | `["127.0.0.1"]` | 客户端连接地址 |
| | `port` | `9042` | CQL 端口 |
| | `keyspace` | `ktau` | 实验 keyspace |
| | `rf` | `2` | 复制因子 |
| | `n_nodes` | `4` | 集群节点数（compose 拓扑按此设计） |
| `data` | `dataset` | `BGL` | `BGL` 或 `HDFS` |
| | `raw_file` | `data/BGL_2k.log` | 相对项目根目录 |
| | `max_ops` | `2000` | 导入操作条数 |
| | `seed` | `42` | 数据随机种子 |
| `model` | `N` | `8` | 逻辑副本数 |
| | `M` | `24` | 每 trial 发散操作数 |
| | `trials` | `30` | 每配置试验次数 |
| | `seed` | `42` | 随机种子 |
| | `obs` | `0.9` | 副本观测比例 |
| | `noise` | `0.05` | 并发对相邻对换噪声 |
| | `skew_us` | `500.0` | 每副本时钟偏移上限（µs） |
| `monitor` | `interval_s` | `1.0` | 采样间隔（s） |
| | `threshold` | `0.05` | 告警阈值（τ̂） |
| | `window_ops` | `20` | 监控窗口（最近操作数） |
| | `write_rate` | `100` | 监控流写入速率（ops/s） |
| | `steady_ops` | `120` | 稳态步数 |
| | `drift_ops` | `120` | 排序漂移步数（重排窗口，不新增操作） |
| | `converge_ops` | `40` | 收敛步数 |
| | `partition_ops` | `120` | 集合发散步数 |
| | `heal_ops` | `60` | 愈合步数 |
| `results_dir` | — | `results` | 结果输出目录 |

## 4. 快速开始

```bash
# 一键完整复现（启动集群 → 拉取数据 → 初始化 → 导入 → E1–E6a → E4 监控 → 性能 → 汇总）
python run.py all

# 分步执行（等价于 run.py all 的每一步）
python run.py env             # 生成 .env
python run.py up              # 启动集群并等待健康
python run.py fetch           # 下载 BGL trace（已存在则跳过）
python run.py init            # 初始化 keyspace/表
python run.py ingest          # 导入 trace
python run.py core            # E1–E6a 核心实验（离线）
python run.py monitor         # E4 实时监控
python run.py perf 30         # 资源/延迟采集 30s
python run.py analyze         # 生成 results/experiment_report.md

# 其他
python run.py test            # 冒烟测试（离线自检）
python run.py down            # 停止集群
python run.py -h              # 帮助
```

**手动等价命令**（不使用 run.py 时）：

```bash
python scripts/prepare_env.py
docker compose up -d --wait          # 或 docker compose up -d
python scripts/fetch_trace.py BGL
python scripts/init_cluster.py
python scripts/ingest_trace.py
python scripts/run_experiments.py    # 离线，仅需 data/ 下 trace 文件
python scripts/monitor.py
python scripts/perf_collect.py 30
python scripts/analyze_results.py
docker compose down
```

**实验阶段与集群依赖关系**：

| 阶段 | 脚本 | 需集群 | 产物 |
|---|---|---|---|
| 集群初始化 | init_cluster.py | ✅ | keyspace/表 |
| 数据导入 | ingest_trace.py | ✅ | trace_ops 表；吞吐(ops/s) |
| E1 因果分解 / E1b 反例 | run_experiments.py | ❌ | e1_causal_decomp.csv, e1b_counterexample.csv |
| E2 端到端对比 | run_experiments.py | ❌ | e2_end2end.csv |
| E3 RP vs 精确 Kemeny | run_experiments.py | ❌ | e3_rp_vs_kemeny.csv |
| E5 性能与扩展性 | run_experiments.py | ❌ | e5_perf.csv |
| E6a 分区不对称 | run_experiments.py | ❌ | e6a_asymmetry.csv |
| E4 τ 实时监控 | monitor.py | ✅ | e4_monitor.csv, e4_monitor_series.csv |
| 资源/延迟采集 | perf_collect.py | ✅ | perf_host.csv, perf_cql_latency.csv |
| 汇总报告 | analyze_results.py | ❌ | experiment_report.md |

## 5. 实验结果

运行完成后，`results/` 下为全部原始数据，`results/experiment_report.md` 为自动汇总报告。要点：

- **E1 因果分解**：Kendall τ 可分解为因果分量与争议分量（Proposition 2）；LWW 在时钟偏移下产生因果违反而被 τ 精确计数。
- **E1b 反例**：局部搜索产生的坏序被 τ 确定性地计数（τ_causal = n_ab）。
- **E2 端到端对比**：高冲突场景下 τ-最优合并的信息保留率 63.9% > LWW 58.1% > Vector Clock 52.5%，且全部操作保留、语义有效性更高。
- **E3**：Ranked Pairs 与精确 Kemeny 在 M=4..8 上结果一致（rp_exact 率 ≈ 1.0），而 Kemeny 为指数级枚举。
- **E4 实时监控**：排序漂移阶段 τ̂ 上升而 maxlag ≡ 0、Jaccard ≡ 1.0——τ 能检测二进制滞后与操作集相似度不可见的"亚阈值"排序分歧；分区阶段 τ̂ ≈ 0 而 Jaccard 下降——二者互补。
- **E5**：τ 计算与 RP 合并均为亚毫秒级（M ≤ 100），合并吞吐随 M 线性增长。
- **E6a**：分区不对称下，RP 保持信息保留率，优于 Leader overwrite 在少数派被截断时的损失。

## 6. 复现与验证

- **确定性**：所有随机源均以种子驱动（`model.seed` / `data.seed`），同一配置重跑结果逐位一致。
- **自检**：`python run.py test` 运行冒烟测试（τ、RP、Kemeny、场景生成、基线、指标）。
- **数据获取**：`fetch_trace.py` 内置多源回退（gitcode raw 镜像等）与格式校验；网络不可达时可将 `BGL_2k.log` / `HDFS_2k.log` 手动放入 `data/`。
- **平台**：论文附录 A.1 记录了运行平台（4 节点 Cassandra 4.1，Docker Compose 单机部署，每节点 1 CPU / 1 GB 堆）。

## 7. 常见问题（FAQ）

**Q1: 集群启动失败 / 端口被占用**
先 `docker compose logs cass-1` 查看原因；端口冲突时修改 `config.yaml` 的 `docker.client_port` 后重新 `python run.py env && python run.py up`。

**Q2: 数据下载失败**
`fetch_trace.py` 依次尝试多个镜像源；若全部不可达，请从 Loghub（<https://github.com/logpai/loghub>）手动下载 `BGL_2k.log` 放入 `data/`，脚本会校验并跳过下载。

**Q3: Python 3.12+ 报 cassandra-driver 异步错误**
`common.py` 已自动注入 asyncio reactor shim，无需手动设置。

**Q4: 不同操作系统兼容性**
路径处理全部基于 `os.path`，脚本无 Windows 专属依赖；`run.py` 使用 `sys.executable` 跨平台调用。

**Q5: 如何切换 HDFS 数据集**
`config.yaml` 中 `data.dataset: HDFS`，再执行 `python run.py fetch`。

**Q6: 想跑更少/更多的实验**
核心实验直接调用 `run_experiments.py` 内的 `run_e1()`–`run_e6a()`；调整 `model.trials` / `M` 等参数即可。

## 8. 扩展实验

- 新合并策略：在 `scripts/baselines.py` 实现 `merge_<name>(scenario, seed) -> (sigma, coverage, unresolved)` 并注册到 `all_strategies()`。
- 新指标：在 `scripts/metrics.py` 添加函数并在 `evaluate()` 中输出。
- 更多 trace：在 `scripts/fetch_trace.py` 的 `SOURCES` 中追加数据集条目（Loghub 格式）。

## 9. 引用与致谢

日志数据来自 Loghub。使用本数据集请引用：

- J. Zhu, S. He, P. He, J. Liu, and M. R. Lyu, "Loghub: A large collection of system log datasets for AI-driven log analytics," in Proc. ISSRE, 2023.
- A. J. Oliner and J. Stearley, "What supercomputers say: a study of five system logs," in Proc. DSN, 2007.

## 10. License

本仓库尚未选择开源协议。公开发布前请按需添加 LICENSE（如 MIT / Apache-2.0）。
