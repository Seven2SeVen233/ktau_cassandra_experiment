"""Common utilities: config loading, Cassandra session, logging."""
import json
import logging
import os
import time
import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config.yaml")
RESULTS = os.path.join(BASE, "results")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ktau")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Relative raw_file paths are resolved against the project root so the scripts
    # run correctly from any working directory
    raw = cfg.get("data", {}).get("raw_file")
    if raw and not os.path.isabs(raw):
        cfg["data"]["raw_file"] = os.path.join(BASE, raw)
    return cfg


def ensure_results():
    os.makedirs(RESULTS, exist_ok=True)
    return RESULTS


def get_session(cfg):
    """Establish a Cassandra session (reusing an existing one when possible)."""
    # Python 3.12+ removed asyncore, so the driver's default reactor chain
    # (gevent/eventlet/libev/asyncore) is unavailable; inject an asyncore shim so
    # DefaultConnection resolves to the asyncio implementation.
    import sys
    import types as _types
    from cassandra.io.asyncioreactor import AsyncioConnection

    if "cassandra.io.asyncorereactor" not in sys.modules:
        _shim = _types.ModuleType("cassandra.io.asyncorereactor")
        _shim.AsyncoreConnection = AsyncioConnection
        sys.modules["cassandra.io.asyncorereactor"] = _shim

    from cassandra.cluster import Cluster, NoHostAvailable
    from cassandra.policies import WhiteListRoundRobinPolicy
    from cassandra.query import ConsistencyLevel

    cluster = Cluster(
        cfg["cluster"]["contact_points"], port=cfg["cluster"]["port"],
        connection_class=AsyncioConnection,
        protocol_version=5,
        load_balancing_policy=WhiteListRoundRobinPolicy(cfg["cluster"]["contact_points"]),
    )
    session = cluster.connect()
    session.default_fetch_size = 10000
    return cluster, session


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def now_ms():
    return time.perf_counter() * 1000.0
