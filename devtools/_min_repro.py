"""最小复现：为什么 8 副本重排后窗口完全一致？"""
import random
import sys

sys.path.insert(0, "scripts")


def main():
    N = 8
    WINDOW = 20
    STEADY = 120
    DRIFT = 120
    rng = random.Random(99999)
    mem = [[] for _ in range(N)]
    seq = [0] * N
    triggers = []

    # 稳态
    for k in range(STEADY):
        for r in range(N):
            seq[r] += 1
            mem[r].insert(0, (seq[r], f"op{k}"))
            if len(mem[r]) > WINDOW:
                mem[r].pop()

    # 漂移
    for k in range(DRIFT):
        jit = 0.6 * (k + 1) / DRIFT
        for r in range(N):
            if rng.random() < jit:
                triggers.append((k, r))
                n = len(mem[r])
                blk = max(2, int(n * 0.66))
                p = rng.randrange(0, n - blk + 1)
                sub = mem[r][p:p + blk]
                rng.shuffle(sub)
                mem[r][p:p + blk] = sub

    print(f"触发事件数={len(triggers)}")
    from collections import Counter
    per_rep = Counter(r for _, r in triggers)
    print(f"每副本触发次数={dict(sorted(per_rep.items()))}")
    for r in range(N):
        w = [o for _, o in mem[r]]
        print(f"副本{r}: {w[:8]}...")

    # 分歧检查
    orders = [[o for _, o in mem[r]] for r in range(N)]
    diff = sum(1 for i in range(N) for j in range(i + 1, N) if orders[i] != orders[j])
    print(f"分歧对数={diff}/{N*(N-1)//2}")


if __name__ == "__main__":
    main()
