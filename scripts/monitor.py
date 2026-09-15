"""Phase 3-E4: Real-time τ monitoring (Cassandra-backed live storage).

Design (aligned with paper §8.4 future directions, validated on offline trace simulation):
- Steady state: all replicas receive every operation in ts order → τ̂≈0, binary lag=0
- Ordering drift: replicas independently reshuffle windows over the same operation set
  (set-convergent → maxlag=0), with probability rising linearly in k
  → τ̂ rises monotonically while binary lag stays 0
  → validates τ's sub-threshold / early detection capability (paper §5.1, §8.4)
- Convergence: full canonical delivery flushes window divergence → τ̂ falls back
- Set divergence: operations delivered only to replica groups A/B → Jaccard drops,
  τ̂ stays ≈0 → validates complementarity of τ and Jaccard (paper §5.5, §8.4)
- Healing: full delivery resumes → τ̂≈0, Jaccard recovers

Metrics: τ̂ trajectory, detection latency, steady-state false alarms, peak τ̂,
Jaccard, maxlag.
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
from tau import gini, tau, tauhat_effective

# Defaults for per-phase steps / window / write rate (overridable via the monitor section of config.yaml)
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
        # Per-replica in-memory window: (seq, op) list, newest first -- used for drift reshuffling
        self.mem = [[] for _ in range(self.N)]
        self.seq = [0] * self.N

    # ---- writer ----
    def _wait(self, futs):
        for f in futs:
            f.result()

    def push(self, r, op):
        """Write op to the top (new seq) of replica r and update the in-memory window."""
        self.seq[r] += 1
        self.mem[r].insert(0, (self.seq[r], op))
        if len(self.mem[r]) > self.window:
            self.mem[r].pop()
        self.session.execute(self.prep, (self.trial, r, self.seq[r], op))

    def push_all(self, op):
        """Write op to all replicas (in parallel)."""
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
        """Write op only to the replicas in grp (in parallel)."""
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
        """Randomly permute one contiguous block (≈blk_frac length) in replica r's
        window and write it back.

        Only the seq positions of existing rows are reordered → operation set is
        unchanged (maxlag=0); only the ordering diverges.
        Uses an atomic unlogged batch write-back so readers never observe a
        "partially reshuffled" duplicate op.
        """
        from cassandra.query import BatchStatement, BatchType

        n = len(self.mem[r])
        if n < 4:
            return
        blk = max(2, int(n * blk_frac))
        p = rng.randrange(0, n - blk + 1)
        sub = self.mem[r][p:p + blk]
        # Key step: unbind ops from seqs, shuffle the ops, then re-pair and write back,
        # so the DB's seq→op mapping truly diverges (window order read by seq changes).
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

        # mark() stamps at phase starts: the monitor labels the "current phase" from
        # these, ensuring drift-period samples are tagged as drift (for detection
        # latency / steady-state false-alarm statistics).
        self.mark(0, "steady")
        # Steady state: full canonical delivery
        for k in range(self.steady):
            self.push_all(all_ops[k])
            time.sleep(1.0 / self.rate)

        # Ordering drift: no new ops; replicas independently reshuffle windows
        # (set-convergent → maxlag=0)
        self.mark(1, "drift")
        for k in range(self.drift):
            jit = self.drift_max * (k + 1) / self.drift
            for r in range(self.N):
                if rng.random() < jit:
                    self.reshuffle(r, rng)
            time.sleep(1.0 / self.rate)

        # Convergence: full canonical delivery flushes window divergence
        self.mark(2, "converge")
        for k in range(self.conv):
            self.push_all(all_ops[self.steady + k])
            time.sleep(1.0 / self.rate)

        # Set divergence: ops delivered only to A or B (Jaccard drops, τ̂ stays ≈0)
        self.mark(3, "partition")
        for k in range(self.partition):
            op = all_ops[self.steady + self.conv + k]
            grp = A if k % 2 == 0 else B
            self.push_grp(op, grp)
            time.sleep(1.0 / self.rate)

        # Healing: full canonical delivery
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
        # Effective normalization (§5.1): Z_eff = Σ_i |Li|(|Li|−1)/2, handles
        # incomplete windows during the partition phase
        th = tauhat_effective(total, windows)
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
                log.info("monitor trial=%d phase=%s tauhat=%.4f maxlag=%d jac=%.3f",
                         self.trial, cur, snap["tauhat"], snap["maxlag"], snap["jaccard"])
            time.sleep(interval)
        return self.samples


def analyze_live(samples, trial_id, drift_max, threshold):
    """Compute detection latency / false alarms / peak from the sample series."""
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
    log.info("=== E4: real-time tau monitoring ===")
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
            log.info("E4[drift_max=%s] detect_delay=%s maxlag@detect=%s steady_false_alarms=%d/%d "
                     "peak_tauhat=%s partition_peak_tauhat=%s jac_partition_min=%s jac_heal_max=%s",
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
        # Clean up stale monitor trials (avoid residue)
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
