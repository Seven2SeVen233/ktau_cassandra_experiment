﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿# -*- coding: utf-8 -*-
"""生成附录 Fig. A1：E4 实时监控五阶段轨迹图（τ̂ 与 Jaccard）。"""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["mathtext.fontset"] = "stix"

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "fig_e4_trajectory.png")

rows = []
with open(os.path.join(BASE, "e4_monitor_series.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        rows.append(r)

# 按 trial 分组
by_trial = {}
for r in rows:
    by_trial.setdefault(r["trial"], []).append(r)

# phase 颜色
PHASE_COLOR = {
    "steady": "#d0d0d0",
    "drift": "#ff9999",
    "converge": "#ffe08a",
    "partition": "#9fc5ff",
    "heal": "#b7e1b7",
}

fig, axes = plt.subplots(2, 2, figsize=(10, 6))
for ax, (trial, data) in zip(axes.flat, by_trial.items()):
    data = sorted(data, key=lambda r: float(r["sample_ts"]))
    x = list(range(len(data)))
    tauhat = [float(r["tauhat"]) for r in data]
    jac = [float(r["jaccard"]) for r in data]
    # 阶段区间着色
    for phase in PHASE_COLOR:
        xs = [xi for xi, r in zip(x, data) if r["phase"] == phase]
        if xs:
            ax.axvspan(min(xs) - 0.5, max(xs) + 0.5, color=PHASE_COLOR[phase],
                       alpha=0.45, label=phase)
    ax.plot(x, tauhat, "o-", color="#c00000", lw=1.6, ms=4, label=r"$\hat{\tau}$")
    ax.plot(x, jac, "s--", color="#1f4e79", lw=1.4, ms=4, label="Jaccard")
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("sample index (1 s)")
    ax.set_ylabel("value")
    ax.set_title(f"trial {trial}, drift_max = {float(data[0]['drift_max']):.2f}", fontsize=9)
    ax.grid(alpha=0.3)
    if trial == "20001":
        ax.legend(fontsize=7, ncol=2, loc="upper right")

fig.suptitle("Fig. A1. Live monitoring: $\\hat{\\tau}$ vs. operation-set Jaccard through the "
             "steady / drift / converge / partition / heal phases", fontsize=10, y=0.99)
fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig(OUT, dpi=200, bbox_inches="tight")
print("saved", OUT)
