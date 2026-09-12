"""公共工具：配置加载、Cassandra 会话、日志。"""
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
    # raw_file 相对路径统一相对项目根目录解析，保证任意 cwd 下可运行
    raw = cfg.get("data", {}).get("raw_file")
    if raw and not os.path.isabs(raw):
        cfg["data"]["raw_file"] = os.path.join(BASE, raw)
    return cfg


def ensure_results():
    os.makedirs(RESULTS, exist_ok=True)
    return RESULTS


def get_session(cfg):
    """建立 Cassandra 会话（尽量复用已存在的）。"""
    # Python 3.12+ 移除了 asyncore，驱动默认 reactor 链（gevent/eventlet/libev/asyncore）
    # 全部不可用，故先注入 asyncore shim，使 DefaultConnection 解析到 asyncio 实现。
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
