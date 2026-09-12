#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kendall-Tau 日志协调实验统一入口。

用法:
    python run.py <phase> [args]

Phases:
    env      生成 .env（把 config.yaml 的 docker 段同步给 docker compose）
    up       启动 Cassandra 集群并等待全部节点健康
    down     停止并清理集群
    fetch    下载 Loghub trace（默认 BGL，可按 config.yaml data.dataset）
    init     初始化 keyspace 与数据表（需集群已启动）
    ingest   解析并导入 trace 到 Cassandra（需集群已启动）
    core     E1–E6a 核心实验（离线，仅需 data/ 下的 trace 文件）
    monitor  E4 τ 实时监控（需集群已启动）
    perf     性能/资源采集，默认 90s，可传时长: python run.py perf 30
    analyze  汇总 results/*.csv 生成 experiment_report.md
    test     核心模块冒烟测试（离线，快速自检）
    all      完整流水线: env → up → fetch → init → ingest → core → monitor → perf → analyze

示例:
    python run.py all                  # 一键完整复现
    python run.py analyze              # 仅重新生成汇总报告
    python run.py monitor              # 单独跑 E4 实时监控
"""
import os
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(ROOT, "scripts")
COMPOSE = os.path.join(ROOT, "docker-compose.yml")
PY = sys.executable


def load_cfg():
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_py(name, *args):
    cmd = [PY, os.path.join(SCRIPTS, name)] + list(args)
    print(">>>", " ".join(cmd))
    return subprocess.call(cmd) == 0


def compose(args):
    cmd = ["docker", "compose", "-f", COMPOSE] + list(args)
    print(">>>", " ".join(cmd))
    return subprocess.call(cmd) == 0


# ---------- phases ----------

def phase_env():
    return run_py("prepare_env.py")


def phase_up():
    if not phase_env():
        return False
    if compose(["up", "-d", "--wait"]):
        return True
    # 旧版 compose 不支持 --wait：退化为后台启动
    if not compose(["up", "-d"]):
        return False
    print("! 当前 compose 不支持 --wait，请稍后用 `python run.py ps` 观察健康状态")
    return True


def phase_down():
    return compose(["down"])


def phase_fetch():
    return run_py("fetch_trace.py", load_cfg()["data"]["dataset"])


def phase_init():
    return run_py("init_cluster.py")


def phase_ingest():
    return run_py("ingest_trace.py")


def phase_core():
    return run_py("run_experiments.py")


def phase_monitor():
    return run_py("monitor.py")


def phase_perf(duration=None):
    return run_py("perf_collect.py", str(duration)) if duration else run_py("perf_collect.py")


def phase_analyze():
    return run_py("analyze_results.py")


def phase_test():
    return run_py("smoke_test.py")


# ---------- main ----------

HELP = __doc__

PHASES = {
    "env": phase_env,
    "up": phase_up,
    "down": phase_down,
    "fetch": phase_fetch,
    "init": phase_init,
    "ingest": phase_ingest,
    "core": phase_core,
    "monitor": phase_monitor,
    "perf": lambda *a: phase_perf(int(a[0]) if a and str(a[0]).isdigit() else None),
    "analyze": phase_analyze,
    "test": phase_test,
}

ALL = ["env", "up", "fetch", "init", "ingest", "core", "monitor", "perf", "analyze"]


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(HELP)
        return
    phase = args[0]
    extra = args[1:]
    if phase == "all":
        ok = all(PHASES[p]() for p in ALL)
        print("流水线完成" if ok else "流水线失败，请检查上方输出")
        sys.exit(0 if ok else 1)
    if phase not in PHASES:
        print(f"未知 phase: {phase}\n\n{HELP}")
        sys.exit(2)
    ok = PHASES[phase](*extra)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
