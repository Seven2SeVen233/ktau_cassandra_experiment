# -*- coding: utf-8 -*-
"""E7: Cassandra cluster fault-injection monitoring experiment -- validation of τ
distance monitoring capability and multi-metric comparison.

Scenarios (4 physical nodes / 8 logical replicas, faulty replica F = replica 3):
  S1 partition_drift : group split (set divergence) + F-internal reshuffling
                       (ordering drift) -- combined fault
  S2 byz_reorder     : only F's window reshuffled repeatedly (set unchanged)
                       -- pure ordering corruption (Byzantine)
  S3 byz_phantom     : only F receives phantom operations (set fault)
  S4 steady_missing  : F misses operations during steady state (set fault, laggard)

Metrics (per sample, from the live window of Cassandra replica_logs):
  τ̂ aggregate (RP merged order + Z_eff effective normalization)
  τ̂_i per-replica normalized distance (faulty-node localization)
  maxlag / jaccard / set_mismatch_i (missing ops = repair-volume proxy) /
  order_viol_i

Analysis: per-metric detection latency / steady-state false alarms / faulty-node
localization accuracy (τ̂_i ranking, lag ranking, set_mismatch ranking) → compares
τ against other metrics on three monitoring tasks.

Output: results/fault_eval_summary.csv, results/fault_eval_series.csv
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
from tau import tau, tauhat_effective

WINDOW = 20
RATE = 100
STEADY = 100
FAULT = 200
HEAL = 100
INTERVAL = 0.5
THRESHOLD = 0.05

SCENARIOS = {
    "S1_partition_drift": "partition_drift",
    "S2_byz_reorder": "byz_reorder",
    "S3_byz_phantom": "byz_phantom",
    "S4_steady_missing": "steady_missing",
}
FAULTY = 3  # logical replica 3


class FaultTrial:
    def __init__(self, cfg, tm, trial_id, session, scenario, threshold=THRESHOLD):
        self.cfg = cfg
        self.tm = tm
        self.trial = trial_id
        self.session = session
        self.scenario = scenario
        self.N = cfg["model"]["N"]
        self.threshold = threshold
        ks = cfg["cluster"]["keyspace"]
        self.prep = session.prepare(
            f"INSERT INTO {ks}.replica_logs (trial, replica, seq, op_id) VALUES (?,?,?,?)")
        self.sel = session.prepare(
            f"SELECT op_id FROM {ks}.replica_logs WHERE trial=? AND replica=? "
            f"ORDER BY seq DESC LIMIT {WINDOW}")
        self.stop = threading.Event()
        self.samples = []
        self.mem = [[] for _ in range(self.N)]
        self.seq = [0] * self.N
        self.rng = random.Random(trial_id)

    # ---------- writer ----------
    def _push(self, r, op):
        self.seq[r] += 1
        self.mem[r].insert(0, (self.seq[r], op))
        if len(self.mem[r]) > WINDOW:
            self.mem[r].pop()
        self.session.execute(self.prep, (self.trial, r, self.seq[r], op))

    def push_all(self, op):
        for r in range(self.N):
            self._push(r, op)

    def push_grp(self, op, grp):
        for r in grp:
            self._push(r, op)

    def reshuffle(self, r, blk_frac=0.66):
        """Shuffle a random contiguous block in replica r's window and write it back
        (set unchanged, order only)."""
        from cassandra.query import BatchStatement, BatchType

        n = len(self.mem[r])
        if n < 4:
            return
        blk = max(2, int(n * blk_frac))
        p = self.rng.randrange(0, n - blk + 1)
        sub = self.mem[r][p:p + blk]
        seqs = [s for s, _ in sub]
        ops = [o for _, o in sub]
        self.rng.shuffle(ops)
        sub = list(zip(seqs, ops))
        self.mem[r][p:p + blk] = sub
        batch = BatchStatement(batch_type=BatchType.UNLOGGED)
        for s, o in sub:
            batch.add(self.prep, (self.trial, r, s, o))
        self.session.execute(batch)

    def run_writer(self):
        all_ops = sorted(self.tm.all_op_ids, key=lambda o: self.tm.ops[o]["ts"])
        A = [r for r in range(self.N) if r != FAULTY][:3]
        B = [r for r in range(self.N) if r != FAULTY][3:6]
        F = FAULTY

        self.mark("steady")
        for k in range(STEADY):
            self.push_all(all_ops[k])
            time.sleep(1.0 / RATE)

        self.mark("fault")
        for k in range(FAULT):
            op = all_ops[STEADY + k]
            if self.scenario == "partition_drift":
                grp = A if k % 2 == 0 else B
                self.push_grp(op, grp)          # group split: set divergence
                if self.rng.random() < 0.5:
                    self.reshuffle(F)            # F-internal reshuffle: ordering drift
            elif self.scenario == "byz_reorder":
                if self.rng.random() < 0.7:
                    self.reshuffle(F)            # only F's ordering corrupted
            elif self.scenario == "byz_phantom":
                self._push(F, op)                # only F receives it (phantom)
            elif self.scenario == "steady_missing":
                for r in range(self.N):
                    if r != F:
                        self._push(r, op)        # F misses the operation
            time.sleep(1.0 / RATE)

        self.mark("heal")
        for k in range(HEAL):
            self.push_all(all_ops[STEADY + FAULT + k])
            time.sleep(1.0 / RATE)
        self.stop.set()

    def mark(self, name):
        self.samples.append({"sample_ts": time.time(), "phase": name, "marker": True})

    # ---------- monitor ----------
    def snapshot(self):
        windows = []
        for r in range(self.N):
            rows = self.session.execute(self.sel, (self.trial, r)).all()
            windows.append([row[0] for row in rows])
        op_set = list({o for w in windows for o in w})
        if len(op_set) < 2:
            return None
        sigma = ranked_pairs(windows, op_set)
        lens = [len(w) for w in windows]
        zs = [max(1, l * (l - 1) // 2) for l in lens]
        tau_i = [tau(sigma, w) for w in windows]
        tauhat_i = [t / z if z else 0.0 for t, z in zip(tau_i, zs)]
        merged_set = set(op_set)
        miss_i = [len(merged_set - set(w)) for w in windows]
        total = sum(tau_i)
        return {
            "tauhat": tauhat_effective(total, windows),
            "tauhat_i": tauhat_i,
            "tau_i": tau_i,
            "miss_i": miss_i,
            "lens": lens,
            "maxlag": max(lens) - min(lens),
            "jaccard": self._jaccard(windows),
            "M": len(op_set),
        }

    @staticmethod
    def _jaccard(windows):
        sets = [set(w) for w in windows]
        tot, n = 0.0, 0
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                u = sets[i] | sets[j]
                if u:
                    tot += len(sets[i] & sets[j]) / len(u)
                    n += 1
        return tot / n if n else 1.0

    def run_monitor(self):
        while not self.stop.is_set():
            snap = self.snapshot()
            now = time.time()
            if snap:
                cur = "running"
                for s in self.samples:
                    if s.get("marker"):
                        cur = s["phase"]
                snap["sample_ts"] = now
                snap["phase"] = cur
                snap["trial"] = self.trial
                snap["scenario"] = self.scenario
                snap["alert"] = 1 if snap["tauhat"] > self.threshold else 0
                snap["alert_f"] = 1 if snap["tauhat_i"][FAULTY] > self.threshold else 0
                snap["lag_alert"] = 1 if snap["maxlag"] > 0 else 0
                snap["jac_alert"] = 1 if snap["jaccard"] < 1.0 else 0
                self.samples.append(snap)
                log.info("E7[%s] τ̂=%.4f τ̂_F=%.4f lag=%d jac=%.3f miss_F=%d",
                         self.scenario, snap["tauhat"], snap["tauhat_i"][FAULTY],
                         snap["maxlag"], snap["jaccard"], snap["miss_i"][FAULTY])
            time.sleep(INTERVAL)
        return self.samples


def analyze(samples, trial_id, scenario):
    markers = [s for s in samples if s.get("marker")]
    times = {s["phase"]: s["sample_ts"] for s in markers}
    snaps = [s for s in samples if not s.get("marker")]
    if not snaps:
        return None
    f_start = times.get("fault")
    heal_start = times.get("heal")

    def fault_window():
        return [s for s in snaps
                if f_start is not None and s["sample_ts"] >= f_start
                and (heal_start is None or s["sample_ts"] < heal_start)]

    def steady_window():
        return [s for s in snaps
                if f_start is not None and s["sample_ts"] < f_start]

    fw = fault_window()
    sw = steady_window()

    # 1) aggregate τ̂ detection latency (first alert after fault starts)
    d_tau = None
    for s in fw:
        if s["alert"]:
            d_tau = round(s["sample_ts"] - f_start, 2)
            break
    # 2) lag detection latency
    d_lag = None
    for s in fw:
        if s["lag_alert"]:
            d_lag = round(s["sample_ts"] - f_start, 2)
            break
    # 3) jaccard detection latency
    d_jac = None
    for s in fw:
        if s["jac_alert"]:
            d_jac = round(s["sample_ts"] - f_start, 2)
            break
    # 4) steady-state false alarms (τ̂ alerts during steady)
    false_alarms = sum(1 for s in sw if s["alert"])
    # 5) localization accuracy: fraction of fault-window samples where F ranks
    #    first in τ̂_i / miss_i / (lag implied = min-len)
    loc_tau = 0
    loc_miss = 0
    loc_lag = 0
    for s in fw:
        if s["tauhat_i"][FAULTY] >= max(s["tauhat_i"]):
            loc_tau += 1
        if s["miss_i"][FAULTY] >= max(s["miss_i"]):
            loc_miss += 1
        if s["lens"][FAULTY] <= min(s["lens"]):
            loc_lag += 1
    n = max(1, len(fw))
    # 6) fault-window peaks
    peak_tau_F = max((s["tauhat_i"][FAULTY] for s in fw), default=0.0)
    peak_tau = max((s["tauhat"] for s in fw), default=0.0)
    peak_jac_drop = min((s["jaccard"] for s in fw), default=1.0)
    return {
        "trial": trial_id, "scenario": scenario, "n_fault_samples": len(fw),
        "detect_tau_s": d_tau, "detect_lag_s": d_lag, "detect_jac_s": d_jac,
        "false_alarms_steady": false_alarms, "steady_samples": len(sw),
        "loc_tau_F_rank1": round(loc_tau / n, 3),
        "loc_miss_F_rank1": round(loc_miss / n, 3),
        "loc_lag_F_rank1": round(loc_lag / n, 3),
        "peak_tauhat_F": round(peak_tau_F, 4),
        "peak_tauhat": round(peak_tau, 4),
        "jac_min": round(peak_jac_drop, 4),
    }


def main():
    cfg = common.load_config()
    ds = cfg["data"]
    ops_by_node = parse_bgl_file(ds["raw_file"], max_ops=ds["max_ops"])
    tm = TraceModel(ops_by_node, cfg["model"]["N"])
    ks = cfg["cluster"]["keyspace"]
    cluster, session = common.get_session(cfg)
    try:
        # Clean up stale trials
        del_rl = session.prepare(f"DELETE FROM {ks}.replica_logs WHERE trial=? AND replica=?")
        trials = [i + 30000 for i in range(len(SCENARIOS) * 3)]
        for t in trials:
            for r in range(cfg["model"]["N"]):
                session.execute(del_rl, (t, r))

        results, series = [], []
        for rep in range(3):
            for si, (sname, scen) in enumerate(SCENARIOS.items()):
                trial_id = 30000 + rep * len(SCENARIOS) + si
                ft = FaultTrial(cfg, tm, trial_id, session, scen)
                w = threading.Thread(target=ft.run_writer, daemon=True)
                w.start()
                samples = ft.run_monitor()
                w.join(timeout=60)
                r = analyze(samples, trial_id, sname)
                if r:
                    results.append(r)
                    log.info("E7[%s#%d] detect(τ/lag/jac)=%s/%s/%s false_alarms=%d "
                             "localize(F:τ/miss/lag)=%s/%s/%s",
                             sname, rep, r["detect_tau_s"], r["detect_lag_s"],
                             r["detect_jac_s"], r["false_alarms_steady"],
                             r["loc_tau_F_rank1"], r["loc_miss_F_rank1"], r["loc_lag_F_rank1"])
                for s in samples:
                    if s.get("marker"):
                        continue
                    series.append({
                        "trial": trial_id, "scenario": sname, "phase": s["phase"],
                        "sample_ts": s["sample_ts"], "tauhat": s["tauhat"],
                        "tauhat_F": s["tauhat_i"][FAULTY],
                        "maxlag": s["maxlag"], "jaccard": s["jaccard"],
                        "miss_F": s["miss_i"][FAULTY], "M": s["M"],
                        "alert": s["alert"],
                    })
        pd.DataFrame(results).to_csv(
            common.ensure_results() + "/fault_eval_summary.csv", index=False)
        pd.DataFrame(series).to_csv(
            common.ensure_results() + "/fault_eval_series.csv", index=False)
        print("\n===== E7 summary =====")
        print(pd.DataFrame(results).to_string(index=False))
    finally:
        cluster.shutdown()


if __name__ == "__main__":
    main()
