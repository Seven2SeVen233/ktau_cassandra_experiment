"""模拟完整 E4 轨迹：稳态→漂移(重排窗口,不新增op)→分区(集合发散)→愈合。"""
import random
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0])

from ranked_pairs import ranked_pairs
from tau import tau, tauhat


def jaccard(windows):
    sets = [set(w) for w in windows]
    tot, n = 0.0, 0
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            u = sets[i] | sets[j]
            if u:
                tot += len(sets[i] & sets[j]) / len(u)
                n += 1
    return tot / n if n else 1.0


def snapshot(windows):
    op_set = list(set(o for w in windows for o in w))
    if len(op_set) < 2:
        return 0.0, 1.0
    sigma = ranked_pairs(windows, op_set)
    d = [tau(sigma, w) for w in windows]
    th = tauhat(sum(d), len(windows), len(op_set))
    return th, jaccard(windows)


def sim_full(N, WINDOW, STEADY, DRIFT, CONV, PART, HEAL, drift_max, mode="full", seed=42,
             new_ops_drift=True, jit_floor=0.0):
    rng = random.Random(seed)
    A = list(range(N // 2))
    B = list(range(N // 2, N))
    # 每副本窗口（最新在前），固定大小
    mem = [[] for _ in range(N)]
    traj_tau, traj_jac, traj_phase = [], [], []

    def emit(phase):
        th, jc = snapshot(mem)
        traj_tau.append(th)
        traj_jac.append(jc)
        traj_phase.append(phase)

    # 稳态
    for k in range(STEADY):
        for r in range(N):
            mem[r].insert(0, k)
            if len(mem[r]) > WINDOW:
                mem[r].pop()
    emit("steady")

    # 漂移：新 op 全量投递（若 new_ops_drift），并对窗口重排
    for k in range(DRIFT):
        jit = jit_floor + (drift_max - jit_floor) * (k + 1) / DRIFT
        op = STEADY + k
        for r in range(N):
            if new_ops_drift:
                mem[r].insert(0, op)
                if len(mem[r]) > WINDOW:
                    mem[r].pop()
            if rng.random() < jit and len(mem[r]) >= 4:
                if mode == "full":
                    rng.shuffle(mem[r])
                elif mode == "suffix":
                    n = len(mem[r])
                    blk = max(2, n * 2 // 3)
                    p = rng.randrange(0, n - blk + 1)
                    sub = mem[r][p:p + blk]
                    rng.shuffle(sub)
                    mem[r][p:p + blk] = sub
        if k % 5 == 4:
            emit("drift")

    # 收敛：全量规范投递，冲刷窗口分歧
    for k in range(CONV):
        op = STEADY + DRIFT + k
        for r in range(N):
            mem[r].insert(0, op)
            if len(mem[r]) > WINDOW:
                mem[r].pop()
    emit("converge")

    # 分区：新 op 只投递 A 或 B（集合发散）
    for k in range(PART):
        op = STEADY + DRIFT + CONV + k
        grp = A if k % 2 == 0 else B
        for r in grp:
            mem[r].insert(0, op)
            if len(mem[r]) > WINDOW:
                mem[r].pop()
        if k % 5 == 4:
            emit("partition")

    # 愈合：新 op 全量投递（集合收敛，顺序规范）
    for k in range(HEAL):
        op = STEADY + DRIFT + CONV + PART + k
        for r in range(N):
            mem[r].insert(0, op)
            if len(mem[r]) > WINDOW:
                mem[r].pop()
        if k % 5 == 4:
            emit("heal")
    return traj_tau, traj_jac, traj_phase


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-new-drift", action="store_true")
    ap.add_argument("--floor", type=float, default=0.0)
    ap.add_argument("--detail", type=int, default=-1, help="打印某个 dm*100 配置的详细轨迹")
    args = ap.parse_args()
    new_ops = not args.no_new_drift
    for WINDOW in (20, 30):
        for dm in (0.2, 0.4, 0.6, 0.8):
            for mode in ("full", "suffix"):
                tt, tj, tp = sim_full(8, WINDOW, 120, 120, 40, 120, 60, dm, mode, 42,
                                      new_ops_drift=new_ops, jit_floor=args.floor)
                if args.detail == int(dm * 100):
                    dr = [(v, j) for v, j, p in zip(tt, tj, tp) if p == "drift"]
                    print(f"\n== 轨迹 W={WINDOW} dm={dm} {mode} (new_ops={new_ops}, floor={args.floor}) ==")
                    print("漂移轨迹 τ̂:", " ".join(f"{v:.2f}" for v, _ in dr))
                # 各阶段均值
                def avg(tag):
                    xs = [v for v, p in zip(tt, tp) if p == tag]
                    return sum(xs) / len(xs) if xs else 0.0
                drift_vals = [v for v, p in zip(tt, tp) if p == "drift"]
                drift_max_v = max(drift_vals) if drift_vals else 0.0
                part_vals = [v for v, p in zip(tt, tp) if p == "partition"]
                peak_part = max(part_vals) if part_vals else 0.0
                part_jac = [v for v, p in zip(tj, tp) if p == "partition"]
                print(f"W={WINDOW:3d} dm={dm:.1f} {mode:6s} | τ̂ 稳态={avg('steady'):.3f} "
                      f"漂移max={drift_max_v:.3f} 收敛={avg('converge'):.3f} 分区max={peak_part:.3f} 愈合={avg('heal'):.3f} | "
                      f"jac 分区min={min(part_jac) if part_jac else 1:.2f} | "
                      f"轨迹长度={len(tt)}")
            print()
