"""Phase 5: 结果汇总分析 → results/experiment_report.md + 控制台摘要。

读取 E1–E6a、perf_*.csv，输出量化表格与结论要点。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import common
from common import log


def _load(name):
    path = os.path.join(common.RESULTS, name)
    if not os.path.exists(path):
        log.warning("缺少结果文件: %s", name)
        return None
    return pd.read_csv(path)


def fmt(x, nd=4):
    try:
        return f"{x:.{nd}f}"
    except Exception:
        return str(x)


def main():
    common.ensure_results()
    lines = ["# Kendall τ / Ranked Pairs 实验报告\n"]
    lines.append("> 由 analyze_results.py 自动汇总生成。数据源：results/*.csv。\n")

    # ---- E1 因果分解 ----
    df = _load("e1_causal_decomp.csv")
    if df is not None:
        lines.append("## E1 τ 距离因果分解（均值）\n")
        lines.append("| conflict | strategy | τ_causal | τ_contested | τ̂ | 信息保留率 |")
        lines.append("|---|---|---|---|---|---|")
        g = df.groupby(["conflict", "strategy"])[
            ["tau_causal", "tau_contested", "tauhat", "info_retention"]].mean()
        for (conf, strat), r in g.iterrows():
            lines.append(f"| {conf} | {strat} | {r['tau_causal']:.4f} | "
                         f"{r['tau_contested']:.4f} | {r['tauhat']:.4f} | {r['info_retention']:.4f} |")
        lines.append("")

    # ---- E1b 反例 ----
    df = _load("e1b_counterexample.csv")
    if df is not None:
        r = df.iloc[0]
        lines.append("## E1b 论文反例复现\n")
        lines.append(f"- 一致约束被违反时 τ_causal = {r['tau_causal']:.0f}（= n_ab），"
                     f"τ_total = {r['tau_total']:.0f}，τ̂ = {r['tauhat']:.4f}。"
                     "τ 能精确计数被违反的因果约束，具备确定性。\n")

    # ---- E2 端到端 ----
    df = _load("e2_end2end.csv")
    if df is not None:
        lines.append("## E2 端到端对比（高冲突）\n")
        lines.append("| strategy | 操作保留 | 自动覆盖 | 信息保留 | τ_causal | 语义有效 | Gini | 耗时(ms) |")
        lines.append("|---|---|---|---|---|---|---|---|")
        g = df.groupby("strategy")[
            ["ops_retained", "auto_coverage", "info_retention", "tau_causal",
             "semantic_validity", "gini", "time_ms"]].mean()
        for strat, r in g.iterrows():
            lines.append(f"| {strat} | {r['ops_retained']:.4f} | {r['auto_coverage']:.4f} | "
                         f"{r['info_retention']:.4f} | {r['tau_causal']:.4f} | "
                         f"{r['semantic_validity']:.4f} | {r['gini']:.4f} | {r['time_ms']:.4f} |")
        lines.append("")

    # ---- E3 RP vs Kemeny ----
    df = _load("e3_rp_vs_kemeny.csv")
    if df is not None:
        lines.append("## E3 Ranked Pairs vs 精确 Kemeny\n")
        lines.append("| M | RP=精确Kemeny比例 | 平均超额% | 最大超额% | Kemeny耗时(ms) |")
        lines.append("|---|---|---|---|---|")
        g = df.groupby("M").agg(
            rp_exact_rate=("rp_exact", "mean"),
            avg_excess_pct=("excess_pct", "mean"),
            max_excess_pct=("excess_pct", "max"),
            kemeny_ms=("kemeny_ms", "mean"))
        for M, r in g.iterrows():
            lines.append(f"| {M} | {r['rp_exact_rate']:.3f} | {r['avg_excess_pct']:.4f} | "
                         f"{r['max_excess_pct']:.4f} | {r['kemeny_ms']:.4f} |")
        lines.append("")

    # ---- E4 监控 ----
    df = _load("e4_monitor.csv")
    if df is not None:
        lines.append("## E4 τ 实时监控\n")
        lines.append("| drift_max | 检测延迟(s) | maxlag@检测 | 稳态误报 | 峰值τ̂ | "
                     "分区峰值τ̂ | jac分区min | jac愈合max |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for _, r in df.iterrows():
            det = fmt(r["detect_delay_s"]) if pd.notna(r["detect_delay_s"]) else "N/A"
            ml = int(r["maxlag_at_detect"]) if pd.notna(r["maxlag_at_detect"]) else "N/A"
            jpm = fmt(r["jac_partition_min"]) if pd.notna(r["jac_partition_min"]) else "N/A"
            jhm = fmt(r["jac_heal_max"]) if pd.notna(r["jac_heal_max"]) else "N/A"
            lines.append(f"| {r['drift_max']:.2f} | {det} | {ml} | "
                         f"{int(r['false_alarms_steady'])} | {r['peak_tauhat']:.4f} | "
                         f"{r['peak_partition_tauhat']:.4f} | {jpm} | {jhm} |")
        lines.append("")
        lines.append("> 轨迹数据：`results/e4_monitor_series.csv`（trial、phase、τ̂、maxlag、"
                     "jaccard）。漂移阶段 maxlag≡0 而 τ̂ 上升，证明 τ 可检测 binary lag "
                     "不可见的排序分歧；分区阶段 τ̂≈0 而 Jaccard 下降，证明二者互补。\n")

    # ---- E5 性能 ----
    df = _load("e5_perf.csv")
    if df is not None:
        lines.append("## E5 性能与扩展性（p50）\n")
        lines.append("| M | τ_total(ms) | RP(ms) | LWW(ms) | VC(ms) | 合并吞吐(ops/s) |")
        lines.append("|---|---|---|---|---|---|")
        g = df.groupby("M")[
            ["tau_total_ms", "rp_ms", "lww_ms", "vc_ms", "merge_thr_ops_s"]].quantile(0.5)
        for M, r in g.iterrows():
            lines.append(f"| {M} | {r['tau_total_ms']:.3f} | {r['rp_ms']:.3f} | "
                         f"{r['lww_ms']:.3f} | {r['vc_ms']:.3f} | {r['merge_thr_ops_s']:.1f} |")
        lines.append("")

    # ---- E6a 分区不对称 ----
    df = _load("e6a_asymmetry.csv")
    if df is not None:
        lines.append("## E6a 分区不对称（少数派比例扫描）\n")
        lines.append("| 少数派比例 | strategy | 操作保留 | 信息保留 | τ̂ |")
        lines.append("|---|---|---|---|---|")
        g = df.groupby(["minority_frac", "strategy"])[
            ["ops_retained", "info_retention", "tauhat"]].mean()
        for (fr, strat), r in g.iterrows():
            lines.append(f"| {fr:.2f} | {strat} | {r['ops_retained']:.4f} | "
                         f"{r['info_retention']:.4f} | {r['tauhat']:.4f} |")
        lines.append("")

    # ---- perf ----
    df = _load("perf_host.csv")
    if df is not None:
        lines.append("## 集群资源利用率（docker stats 采样均值）\n")
        lines.append("| 节点 | CPU% | 内存(MB) | 网络收(MB) | 网络发(MB) |")
        lines.append("|---|---|---|---|---|")
        g = df.groupby("node")[["cpu_pct", "mem_mb", "net_rx", "net_tx"]].mean()
        for node, r in g.iterrows():
            lines.append(f"| {node} | {r['cpu_pct']:.1f} | {r['mem_mb']:.0f} | "
                         f"{r['net_rx']:.1f} | {r['net_tx']:.1f} |")
        lines.append("")

    df = _load("perf_cql_latency.csv")
    if df is not None:
        p = dict(zip(df["metric"], df["ms"]))
        lines.append("## CQL 往返延迟（ms）\n")
        lines.append(f"- p50 = {p.get('p50', 'N/A')}, p95 = {p.get('p95', 'N/A')}, "
                     f"p99 = {p.get('p99', 'N/A')}\n")

    out = os.path.join(common.RESULTS, "experiment_report.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log.info("报告已生成: %s", out)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
