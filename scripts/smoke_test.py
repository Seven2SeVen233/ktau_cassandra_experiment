"""核心模块冒烟测试：τ、Ranked Pairs、Kemeny、场景生成、基线、指标。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import log

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE = os.path.join(BASE, "data", "BGL_2k.log")

from scenario_gen import TraceModel, parse_bgl_file, sample_conflict_group
from tau import tau, tauhat, info_retention, gini
from ranked_pairs import ranked_pairs
from kemeny_exact import kemeny_exact
from baselines import all_strategies
from metrics import evaluate

cfg = {"data": {"raw_file": TRACE, "max_ops": 2000},
       "model": {"N": 8, "M": 24, "seed": 42}}


def test_tau():
    a = [1, 2, 3, 4]
    b = [1, 3, 2, 4]
    assert tau(a, b) == 1, tau(a, b)
    assert tau(a, a) == 0
    assert tau(a, list(reversed(a))) == 6
    log.info("tau ok")


def test_rp_and_kemeny():
    rl = [[1, 2, 3], [1, 3, 2], [2, 1, 3]]
    op_set = {1, 2, 3}
    sigma = ranked_pairs(rl, op_set)
    assert sorted(sigma) == [1, 2, 3]
    ex, t = kemeny_exact(rl, op_set)
    assert t == sum(tau(ex, x) for x in rl)
    log.info("ranked_pairs=%s kemeny=%s tau_opt=%s", sigma, ex, t)


def test_scenario():
    ops_by_node = parse_bgl_file(TRACE, max_ops=2000)
    tm = TraceModel(ops_by_node, 8)
    assert len(tm.ops) > 1000, len(tm.ops)
    sc = sample_conflict_group(tm, 42, 24, "high")
    assert len(sc.D) == 24
    # 各副本日志为 D 的子集
    union = set().union(*sc.replica_logs)
    assert union <= sc.D
    # 一致因果约束被所有包含副本遵守
    for a, b in sc.causal_pairs:
        for rl in sc.replica_logs:
            if a in rl and b in rl:
                assert rl.index(a) < rl.index(b), (a, b)
    # τ̂ 值域
    sigma = ranked_pairs(sc.replica_logs, sc.D)
    total = sum(tau(sigma, rl) for rl in sc.replica_logs)
    th = tauhat(total, 8, 24)
    assert 0 <= th <= 1, th
    assert info_retention(total, 8, 24) >= 0.0
    log.info("scenario ok: causal_density=%.3f groups=%s", sc.causal_density, sc.conflict_groups)


def test_strategies():
    ops_by_node = parse_bgl_file(TRACE, max_ops=2000)
    tm = TraceModel(ops_by_node, 8)
    sc = sample_conflict_group(tm, 7, 24, "high")
    strategies = all_strategies()
    for name, fn in strategies.items():
        sigma, cov, unr = fn(sc, seed=7)
        m = evaluate(sc, sigma, cov, unr, name)
        assert 0 <= m["info_retention"] <= 1
        assert m["tau_causal"] >= 0
        assert 0 <= m["auto_coverage"] <= 1
        log.info("strategy=%-12s cov=%.2f unr=%-3d ret=%.3f τcausal=%s τcont=%.3f sem=%.2f",
                 name, m["auto_coverage"], m["unresolved"], m["info_retention"],
                 m["tau_causal"], m["tau_contested"], m["semantic_validity"])
    log.info("strategies ok")


if __name__ == "__main__":
    test_tau()
    test_rp_and_kemeny()
    test_scenario()
    test_strategies()
    log.info("ALL SMOKE TESTS PASSED")
