"""Phase 3-E4: τ 实时监控（Cassandra 实时存储驱动）。

设计（对齐论文 §8.4 未来方向，经离线轨迹模拟验证）：
- 稳态：所有副本按 ts 序收到全部操作 → τ̂≈0，binary lag=0
- 排序漂移：副本对同一操作集（集合一致 → maxlag=0）独立重排窗口
  （随机块置换，概率随 k 线性上升）→ τ̂ 单调上升而 binary lag 仍为 0
  → 验证 τ 的亚阈值/早期检测能力（论文 §5.1、§8.4）
- 收敛：全量规范投递，冲刷窗口分歧 → τ̂ 回落
- 集合发散：操作只投递到 A/B 两组副本 → Jaccard 下降、τ̂ 保持≈0
  → 验证 τ 与 Jaccard 互补（论文 §5.5、§8.4）
- 愈合：恢复全量投递 → τ̂≈0、Jaccard 回升

指标：τ̂ 轨迹、检测延迟、稳态误报率、峰值 τ̂、Jaccard、maxlag。
"""
import os
import random
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import common
from common import log
from ranked_pairs import ranked_pairs
from scenario_gen import TraceModel, parse_bgl_file
from tau import tau, tauhat, gini

# 各阶段步数 / 窗口 / 速率默认值（config.yaml 的 monitor 段可覆盖）
DEF = dict(window_ops=20, write_rate=100, steady_ops=120, drift_ops=120,
           converge_ops=40, partition_ops=120, heal_ops=60)


class LiveMonitor:
    def __init__(self, cfg, tm, trial_id, session, drift_max=0.4, threshold=0.05):
        self.cfg = cfg
        self.tm = tm
        self.trial = trial_id
        self.session = session
        self.N = cfg["model"]["N"]
        self.drift_max = drift_max
        self.threshold = threshold
        mon = {**DEF, **cfg.get("monitor", {})}
        self.window = mon["window_ops"]
        self.rate = mon["write_rate"]
        self.steady = mon["steady_ops"]
        self.drift = mon["drift_ops"]
        self.conv = mon["converge_ops"]
        self.partition = mon["partition_ops"]
        self.heal = mon["heal_ops"]
        ks = cfg["cluster"]["keyspace"]
        self.prep = session.prepare(
            f"INSERT INTO {ks}.replica_logs (trial, replica, seq, op_id) VALUES (?,?,?,?)")
        self.sel = session.prepare(
            f"SELECT op_id FROM {ks}.replica_logs WHERE trial=? AND replica=? "
            f"ORDER BY seq DESC LIMIT {self.window}")
        self.ins_mon = session.prepare(
            f"INSERT INTO {ks}.monitor_series (trial, sample_ts, tauhat, gini, maxlag, "
            f"ops_total, alert, phase) VALUES (?,?,?,?,?,?,?,?)")
        self.stop = threading.Event()
        self.samples = []
        # 每副本内存窗口：(seq, op) 列表，最新在前 —— 供漂移重排使用
        self.mem = [[] for _ in range(self.N)]
        self.seq = [0] * self.N

    # ---- writer ----
    def _wait(self, futs):
        for f in futs:
            f.result()

    def push(self, r, op):
        """将 op 写入副本 r 顶部（新 seq），并更新内存窗口。"""
        self.seq[r] += 1
        self.mem[r].insert(0, (self.seq[r], op))
        if len(self.mem[r]) > self.window:
            self.mem[r].pop()
        self.session.execute(self.prep, (self.trial, r, self.seq[r], op))

    def push_all(self, op):
        """将 op 写入全部副本（并行）。"""
        futs = []
        for r in range(self.N):
            self.seq[r] += 1
            self.mem[r].insert(0, (self.seq[r], op))
            if len(self.mem[r]) > self.window:
                self.mem[r].pop()
            futs.append(self.session.execute_async(
                self.prep, (self.trial, r, self.seq[r], op)))
        self._wait(futs)

    def push_grp(self, op, grp):
        """将 op 仅写入 grp 中的副本（并行）。"""
        futs = []
        for r in grp:
            self.seq[r] += 1
            self.mem[r].insert(0, (self.seq[r], op))
            if len(self.mem[r]) > self.window:
                self.mem[r].pop()
            futs.append(self.session.execute_async(
                self.prep, (self.trial, r, self.seq[r], op)))
        self._wait(futs)

    def reshuffle(self, r, rng, blk_frac=0.66):
        """将副本 r 窗口内一个随机连续块（约 blk_frac 长度）随机置换并写回。

        仅重排既有行的 seq 位置 → 操作集不变（maxlag=0），仅顺序分歧。
        用同分区原子批处理写回，避免读端看到"部分重排"的重复 op。
        """
        from cassandra.query import BatchStatement, BatchType

        n = len(self.mem[r])
        if n < 4:
            return
        blk = max(2, int(n * blk_frac))
        p = rng.randrange(0, n - blk + 1)
        sub = self.mem[r][p:p + blk]
        # 关键：把 op 与 seq 解绑，打乱 op 后重新配对写回，
        # 使 DB 中 seq→op 映射真正发散（按 seq 读取的窗口顺序随之变化）。
        seqs = [s for s, _ in sub]
        ops = [o for _, o in sub]
        rng.shuffle(ops)
        sub = list(zip(seqs, ops))
        self.mem[r][p:p + blk] = sub
        batch = BatchStatement(batch_type=BatchType.UNLOGGED)
        for s, o in sub:
            batch.add(self.prep, (self.trial, r, s, o))
        self.session.execute(batch)

    def run_writer(self):
        rng = random.Random(self.trial)
        all_ops = sorted(self.tm.all_op_ids, key=lambda o: self.tm.ops[o]["ts"])
        A = list(range(self.N // 2))
        B = list(range(self.N // 2, self.N))

        # mark 在阶段开始时打点：监控据此标注"当前阶段"，保证
        # 漂移期的采样被正确标记为 drift（用于检测延迟/稳态误报统计）。
        self.mark(0, "steady")
        # 稳态：全量规范投递
        for k in range(self.steady):
            self.push_all(all_ops[k])
            time.sleep(1.0 / self.rate)

        # 排序漂移：不新增 op，副本独立重排窗口（集合一致 → maxlag=0）
        self.mark(1, "drift")
        for k in range(self.drift):
            jit = self.drift_max * (k + 1) / self.drift
            for r in range(self.N):
                if rng.random() < jit:
                    self.reshuffle(r, rng)
            time.sleep(1.0 / self.rate)

        # 收敛：全量规范投递，冲刷窗口分歧
        self.mark(2, "converge")
        for k in range(self.conv):
            self.push_all(all_ops[self.steady + k])
            time.sleep(1.0 / self.rate)

        # 集合发散：op 只投递 A 或 B（Jaccard 下降，τ̂ 保持≈0）
        self.mark(3, "partition")
        for k in range(self.partition):
            op = all_ops[self.steady + self.conv + k]
            grp = A if k % 2 == 0 else B
            self.push_grp(op, grp)
            time.sleep(1.0 / self.rate)

        # 愈合：全量规范投递
        self.mark(4, "heal")
        for k in range(self.heal):
            self.push_all(all_ops[self.steady + self.conv + self.partition + k])
            time.sleep(1.0 / self.rate)
        self.stop.set()

    # ---- monitor ----
    def mark(self, phase_idx, name):
        self.samples.append({"sample_ts": time.time(), "phase": name,
                             "phase_idx": phase_idx, "marker": True})

    def compute_snapshot(self):
        windows = []
        for r in range(self.N):
            rows = self.session.execute(self.sel, (self.trial, r)).all()
            windows.append([row[0] for row in rows])
        op_set = set()
        for w in windows:
            op_set.update(w)
        op_set = list(op_set)
        if len(op_set) < 2:
            return None
        sigma = ranked_pairs(windows, op_set)
        d = [tau(sigma, w) for w in windows]
        total = sum(d)
        M = len(op_set)
        th = tauhat(total, self.N, M)
        g = gini(d)
        lens = [len(w) for w in windows]
        maxlag = max(lens) - min(lens)
        jac = self._jaccard(windows)
        return {"tauhat": th, "gini": g, "maxlag": maxlag, "jaccard": jac, "M": M,
                "tau_total": total}

    @staticmethod
    def _jaccard(windows):
        sets = [set(w) for w in windows]
        tot = 0.0
        n = 0
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                u = sets[i] | sets[j]
                if u:
                    tot += len(sets[i] & sets[j]) / len(u)
                    n += 1
        return tot / n if n else 1.0

    def run_monitor(self, interval=1.0):
        while not self.stop.is_set():
            snap = self.compute_snapshot()
            now = time.time()
            if snap:
                snap["sample_ts"] = now
                snap["alert"] = 1 if snap["tauhat"] > self.threshold else 0
                cur = "running"
                for s in self.samples:
                    if s.get("marker"):
                        cur = s["phase"]
                snap["phase"] = cur
                snap["trial"] = self.trial
                self.samples.append(snap)
                try:
                    self.session.execute(
                        self.ins_mon,
                        (self.trial, snap["sample_ts"], snap["tauhat"], snap["gini"],
                         snap["maxlag"], snap["M"], snap["alert"], cur))
                except Exception:
                    pass
                log.info("monitor trial=%d phase=%s τ̂=%.4f maxlag=%d jac=%.3f",
                         self.trial, cur, snap["tauhat"], snap["maxlag"], snap["jaccard"])
            time.sleep(interval)
        return self.samples


def analyze_live(samples, trial_id, drift_max, threshold):
    """从采样序列计算检测延迟/误报/峰值。"""
    markers = [s for s in samples if s.get("marker")]
    phase_times = {}
    for s in markers:
        phase_times[s["phase"]] = s["sample_ts"]
    snapshots = [s for s in samples if not s.get("marker")]
    if not snapshots:
        return None
    drift_start = phase_times.get("drift")
    detect = None
    detect_maxlag = None
    for s in snapshots:
        if s.get("alert") and (drift_start is None or s["sample_ts"] >= drift_start):
            detect = s["sample_ts"] - drift_start if drift_start else 0.0
            detect_maxlag = s["maxlag"]
            break
    steady_snaps = [s for s in snapshots
                    if phase_times.get("steady") is not None
                    and s["sample_ts"] < phase_times.get("drift", s["sample_ts"])]
    false_alarms = sum(1 for s in steady_snaps if s.get("alert"))
    peak = max((s["tauhat"] for s in snapshots), default=0.0)

    def _by_phase(name):
        return [s for s in snapshots
                if phase_times.get(name) is not None and s["sample_ts"] >= phase_times[name]]

    peak_part = max((s["tauhat"] for s in _by_phase("partition")), default=0.0)
    part_jac = [s["jaccard"] for s in _by_phase("partition")]
    heal_jac = [s["jaccard"] for s in _by_phase("heal")]
    return {
        "trial": trial_id, "drift_max": drift_max, "threshold": threshold,
        "detect_delay_s": round(detect, 3) if detect is not None else None,
        "maxlag_at_detect": detect_maxlag,
        "false_alarms_steady": false_alarms,
        "steady_samples": len(steady_snaps),
        "peak_tauhat": round(peak, 4),
        "peak_partition_tauhat": round(peak_part, 4),
        "jac_partition_min": round(min(part_jac), 4) if part_jac else None,
        "jac_heal_max": round(max(heal_jac), 4) if heal_jac else None,
        "n_samples": len(snapshots),
    }


def run_e4(cfg, tm, session):
    log.info("=== E4: τ 实时监控 ===")
    results = []
    series = []
    for i, drift_max in enumerate((0.1, 0.2, 0.4, 0.6)):
        trial_id = 20000 + i
        lm = LiveMonitor(cfg, tm, trial_id, session, drift_max=drift_max,
                         threshold=cfg["monitor"]["threshold"])
        w = threading.Thread(target=lm.run_writer, daemon=True)
        w.start()
        samples = lm.run_monitor(interval=cfg["monitor"]["interval_s"])
        w.join(timeout=30)
        r = analyze_live(samples, trial_id, drift_max, cfg["monitor"]["threshold"])
        if r:
            results.append(r)
            log.info("E4[drift_max=%s] 检测延迟=%s maxlag@检测=%s 稳态误报=%d/%d "
                     "峰值τ̂=%s 分区峰值τ̂=%s jac分区min=%s jac愈合max=%s",
                     drift_max, r["detect_delay_s"], r["maxlag_at_detect"],
                     r["false_alarms_steady"], r["steady_samples"],
                     r["peak_tauhat"], r["peak_partition_tauhat"],
                     r["jac_partition_min"], r["jac_heal_max"])
        for s in samples:
            if not s.get("marker"):
                series.append({"trial": trial_id, "drift_max": drift_max,
                               "phase": s["phase"], "sample_ts": s["sample_ts"],
                               "tauhat": s["tauhat"], "gini": s["gini"],
                               "maxlag": s["maxlag"], "jaccard": s["jaccard"],
                               "M": s["M"], "alert": s["alert"]})
    df = pd.DataFrame(results)
    df.to_csv(common.ensure_results() + "/e4_monitor.csv", index=False)
    pd.DataFrame(series).to_csv(
        common.ensure_results() + "/e4_monitor_series.csv", index=False)
    return df


def main():
    cfg = common.load_config()
    ds = cfg["data"]
    ops_by_node = parse_bgl_file(ds["raw_file"], max_ops=ds["max_ops"])
    tm = TraceModel(ops_by_node, cfg["model"]["N"])
    ks = cfg["cluster"]["keyspace"]
    cluster, session = common.get_session(cfg)
    try:
        # 清理旧监控 trial（避免残留）
        del_rl = session.prepare(f"DELETE FROM {ks}.replica_logs WHERE trial=? AND replica=?")
        del_mon = session.prepare(f"DELETE FROM {ks}.monitor_series WHERE trial=?")
        for i in range(4):
            for r in range(cfg["model"]["N"]):
                session.execute(del_rl, (20000 + i, r))
            session.execute(del_mon, (20000 + i,))
        run_e4(cfg, tm, session)
    finally:
        cluster.shutdown()


if __name__ == "__main__":
    main()
