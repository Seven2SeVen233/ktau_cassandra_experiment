#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified entry point for the Kendall-Tau log reconciliation experiments.

Usage:
    python run.py <phase> [args]

Phases:
    env      generate .env (sync the docker section of config.yaml to docker compose)
    up       start the Cassandra cluster and wait for all nodes to be healthy
    down     stop and clean up the cluster
    fetch    download the Loghub trace (default BGL, per config.yaml data.dataset)
    init     initialize the keyspace and data tables (requires a running cluster)
    ingest   parse and import the trace into Cassandra (requires a running cluster)
    core     E1–E6a core experiments (offline; only needs the trace file under data/)
    monitor  E4 real-time τ monitoring (requires a running cluster)
    perf     performance/resource collection, default 90s; pass a duration:
             python run.py perf 30
    analyze  summarize results/*.csv into experiment_report.md
    test     smoke tests for the core modules (offline, quick self-check)
    all      full pipeline: env → up → fetch → init → ingest → core → monitor → perf → analyze

Examples:
    python run.py all                  # one-click full reproduction
    python run.py analyze              # regenerate only the summary report
    python run.py monitor              # run E4 real-time monitoring alone
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
    # Older compose versions do not support --wait: fall back to background start
    if not compose(["up", "-d"]):
        return False
    print("! this compose does not support --wait; observe health later with `python run.py ps`")
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
        print("pipeline completed" if ok else "pipeline failed; check the output above")
        sys.exit(0 if ok else 1)
    if phase not in PHASES:
        print(f"unknown phase: {phase}\n\n{HELP}")
        sys.exit(2)
    ok = PHASES[phase](*extra)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
