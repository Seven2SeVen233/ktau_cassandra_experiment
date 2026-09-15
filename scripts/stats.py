"""Statistical tests (paper §6.9 Statistical Reliability / Appendix A.5).

Input: per-trial CSVs (trace data under results/ and synthetic data under
results/synthetic/). For metrics such as info_retention / ops_retained /
semantic_validity / tau_causal / time_ms:
  - mean ± std;
  - 95% confidence interval (t distribution, n≥3; n<3 recorded as N/A);
  - pairwise paired Wilcoxon signed-rank test between strategies (two-tailed
    α=0.05, paired by trial);
    all-zero differences (strategies with isomorphic outputs, e.g.,
    CRDT+LWW ≡ LWW) are honestly marked as tied.

Output:
  results/statistics_trace_summary.csv, results/statistics_trace_wilcoxon.csv
  results/synthetic/statistics_summary.csv, results/synthetic/statistics_wilcoxon.csv
  results/statistics.md (one table per experiment + key conclusions)
"""
import os
import sys
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from scipy import stats

import common
from common import log

ALPHA = 0.05

# (file name, grouping columns, metric columns). The trial column is uniformly
# "trial" and the strategy column uniformly "strategy".
EXPERIMENTS = [
    {"name": "E1", "file": "e1_causal_decomp.csv", "group_cols": ["conflict"],
     "metrics": ["tau_causal", "tau_contested", "tauhat", "info_retention"]},
    {"name": "E2", "file": "e2_end2end.csv", "group_cols": [],
     "metrics": ["ops_retained", "auto_coverage", "info_retention", "tau_causal",
                 "tau_contested", "semantic_validity", "gini", "time_ms"]},
    {"name": "E6a", "file": "e6a_asymmetry.csv", "group_cols": ["minority_frac"],
     "metrics": ["ops_retained", "info_retention", "tauhat"]},
]

TRIAL_COL = "trial"
STRAT_COL = "strategy"
WILCOX_METRIC = "info_retention"


def t_crit(n):
    return stats.t.ppf(1 - ALPHA / 2, n - 1) if n >= 3 else None


def summarize(df, group_cols, metrics):
    """Per (group, strategy, metric) → mean/std/n/95%CI."""
    rows = []
    groups = [(g_name, g) for g_name, g in df.groupby(group_cols)] if group_cols else [((), df)]
    for key_vals, g in groups:
        for strat, sg in g.groupby(STRAT_COL):
            for m in metrics:
                v = sg[m].dropna()
                n = len(v)
                if n == 0:
                    continue
                mean = float(v.mean())
                std = float(v.std(ddof=1)) if n > 1 else 0.0
                tc = t_crit(n)
                ci_low = ci_high = np.nan
                if tc is not None and std > 0:
                    half = tc * std / np.sqrt(n)
                    ci_low, ci_high = mean - half, mean + half
                row = {"strategy": strat, "metric": m, "n": n, "mean": mean,
                       "std": std, "ci95_low": ci_low, "ci95_high": ci_high}
                if group_cols:
                    kv = key_vals if isinstance(key_vals, tuple) else (key_vals,)
                    row.update(dict(zip(group_cols, kv)))
                rows.append(row)
    return pd.DataFrame(rows)


def wilcoxon(df, group_cols):
    """Pairwise paired Wilcoxon between strategies (metric = info_retention),
    paired by trial."""
    rows = []
    groups = [(g_name, g) for g_name, g in df.groupby(group_cols)] if group_cols else [((), df)]
    for key_vals, g in groups:
        piv = g.pivot_table(index=TRIAL_COL, columns=STRAT_COL, values=WILCOX_METRIC)
        strats = sorted(piv.columns)
        for a, b in combinations(strats, 2):
            x = piv[a].dropna()
            y = piv[b].dropna()
            idx = x.index.intersection(y.index)
            x, y = x[idx], y[idx]
            n = len(x)
            if n < 2:
                p, w, note = np.nan, np.nan, "insufficient"
            elif np.allclose(np.asarray(x - y, dtype=float), 0.0):
                p, w, note = 1.0, 0.0, "tied"
            else:
                try:
                    w, p = stats.wilcoxon(x, y, alternative="two-sided", zero_method="wilcox")
                    note = ""
                except Exception as exc:  # occasional degenerate case, honestly marked
                    p, w, note = np.nan, np.nan, f"error:{type(exc).__name__}"
            row = {"strategy_a": a, "strategy_b": b, "metric": WILCOX_METRIC,
                   "n": n, "W": w, "p": p,
                   "significant": bool(isinstance(p, float) and p < ALPHA), "note": note}
            if group_cols:
                kv = key_vals if isinstance(key_vals, tuple) else (key_vals,)
                row.update(dict(zip(group_cols, kv)))
            rows.append(row)
    return pd.DataFrame(rows)


def fmt_cell(r):
    """mean±std (95%CI) cell formatting."""
    lo, hi = r["ci95_low"], r["ci95_high"]
    if np.isnan(lo) or np.isnan(hi):
        return f"{r['mean']:.3f}±{r['std']:.3f} (n={int(r['n'])})"
    return (f"{r['mean']:.3f}±{r['std']:.3f} "
            f"({lo:.3f},{hi:.3f}) n={int(r['n'])}")


def render_md(sum_df, wil_df, group_cols, metrics):
    """Render the statistics table for a single experiment. group_cols=[] → single
    table; otherwise one table per group."""
    lines = []
    groups = [(g_name, g) for g_name, g in sum_df.groupby(group_cols)] if group_cols else [((), sum_df)]
    for gname, g in groups:
        label = "" if not group_cols else f"({group_cols[0]} = {gname})"
        lines.append(f"\n### {label}")
        lines.append("| strategy | " + " | ".join(metrics) + " |")
        lines.append("|" + "---|" * (len(metrics) + 1))
        for strat, sg in g.groupby("strategy"):
            cells = {}
            for m in metrics:
                r = sg[sg["metric"] == m]
                cells[m] = fmt_cell(r.iloc[0]) if len(r) else "—"
            lines.append("| " + strat + " | " + " | ".join(cells[m] for m in metrics) + " |")
        wg = wil_df
        if group_cols:
            kv = gname if isinstance(gname, tuple) else (gname,)
            wg = wil_df[wil_df[group_cols[0]] == kv[0]]
        sig = wg[(wg["significant"]) & (wg["note"] == "")]
        tie = wg[wg["note"] == "tied"]
        notes = []
        if len(sig):
            notes.append("Significant differences (p<0.05): " + "; ".join(
                f"{r['strategy_a']} vs {r['strategy_b']} (p={r['p']:.4f})"
                for r in sig.to_dict("records")))
        if len(tie):
            notes.append("Isomorphic (indistinguishable): " + "; ".join(
                f"{r['strategy_a']} ≡ {r['strategy_b']}" for r in tie.to_dict("records")))
        if notes:
            lines.append("")
            lines.append("> " + "; ".join(notes))
    return "\n".join(lines)


def run_dir(results_dir, prefix, out_lines):
    if not os.path.isdir(results_dir):
        log.warning("directory does not exist: %s", results_dir)
        return
    sum_frames, wil_frames = [], []
    for exp in EXPERIMENTS:
        path = os.path.join(results_dir, exp["file"])
        if not os.path.exists(path):
            log.warning("missing %s", path)
            continue
        df = pd.read_csv(path)
        sum_df = summarize(df, exp["group_cols"], exp["metrics"])
        wil_df = wilcoxon(df, exp["group_cols"])
        sum_frames.append(sum_df)
        wil_frames.append(wil_df)
        log.info("%s: %s rows, %d trials/strategies", exp["name"], path,
                 df[TRIAL_COL].nunique())
        if WILCOX_METRIC in exp["metrics"]:
            out_lines.append(f"\n## {exp['name']} — statistics")
            out_lines.append(render_md(sum_df, wil_df, exp["group_cols"], exp["metrics"]))
    if not sum_frames:
        return
    sum_all = pd.concat(sum_frames, ignore_index=True)
    wil_all = pd.concat(wil_frames, ignore_index=True)
    sum_all.to_csv(os.path.join(results_dir, f"{prefix}_summary.csv"), index=False)
    wil_all.to_csv(os.path.join(results_dir, f"{prefix}_wilcoxon.csv"), index=False)
    log.info("statistics written to %s directory", results_dir)


def main():
    common.ensure_results()
    out_lines = ["# Statistical test results (mean±std / 95%CI / paired Wilcoxon)\n",
                 f"> α = {ALPHA}, two-tailed; 95%CI uses the t distribution; "
                 "Wilcoxon is paired by trial. n<3 is recorded as N/A; strategies "
                 "with isomorphic outputs (all-zero differences) are recorded as "
                 "tied (p=1.0, not testable).\n"]
    run_dir(os.path.join(common.RESULTS, "synthetic"), "statistics_synthetic", out_lines)
    run_dir(common.RESULTS, "statistics_trace", out_lines)
    md = "\n".join(out_lines)
    out = os.path.join(common.RESULTS, "statistics.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    log.info("statistics summary generated: %s", out)
    print(md)


if __name__ == "__main__":
    main()
