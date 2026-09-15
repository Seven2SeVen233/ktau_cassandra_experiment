# -*- coding: utf-8 -*-
"""synthetic_cf statistics (§6.9 / Table A5 data source)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from stats import summarize, wilcoxon

BASE = r"c:\Users\34333\OneDrive\Desktop\Kendall-tau\ktau_cassandra_experiment\results\synthetic_cf"

e2 = pd.read_csv(os.path.join(BASE, "e2_end2end.csv"))
e2 = e2[e2["strategy"].isin(
    ["ranked_pairs", "crdt_pure", "lww", "vc", "crdt_lww", "leader"])].copy()

metrics = ["ops_retained", "auto_coverage", "info_retention", "tau_causal",
           "semantic_validity", "gini"]
sums = summarize(e2, [], metrics)
wils = wilcoxon(e2, [])
sums.to_csv(os.path.join(BASE, "statistics_summary.csv"), index=False)
wils.to_csv(os.path.join(BASE, "statistics_wilcoxon.csv"), index=False)
print(sums.to_string())

# Pairwise significance vs ranked_pairs (key rows of Table A5)
w = wils[wils["strategy_a"] == "ranked_pairs"]
print("\n=== wilcoxon vs ranked_pairs (info_retention) ===")
print(w[w["metric"] == "info_retention"].to_string(index=False))
print("synthetic statistics done")
