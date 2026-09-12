"""将 config.yaml 的 docker 段同步为 docker compose 插值用的 .env。

docker compose 启动时会自动读取项目根目录的 .env 文件。
单一配置源是 config.yaml：修改 docker 段后重新运行本脚本即可，
无需手工维护两份配置。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

# config.yaml 的 docker 段键 -> compose 环境变量名
# 注：network 由 docker-compose.yml 固定声明，不支持插值，故不导出。
MAP = {
    "image": "CASSANDRA_IMAGE",
    "cluster_name": "CASSANDRA_CLUSTER_NAME",
    "dc": "CASSANDRA_DC",
    "rack": "CASSANDRA_RACK",
    "container_prefix": "CASSANDRA_CONTAINER_PREFIX",
    "client_port": "CASSANDRA_CLIENT_PORT",
    "heap_size": "CASSANDRA_MAX_HEAP",
    "heap_newsize": "CASSANDRA_HEAP_NEWSIZE",
    "cpu_limit": "CASSANDRA_CPU_LIMIT",
    "mem_limit": "CASSANDRA_MEM_LIMIT",
}


def main():
    cfg = common.load_config()
    docker_cfg = cfg["docker"]
    lines = ["# 由 scripts/prepare_env.py 自动生成；请修改 config.yaml 后重新运行。"]
    for key, env in MAP.items():
        lines.append(f"{env}={docker_cfg[key]}")
    out = os.path.join(common.BASE, ".env")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {out}")
    for l in lines:
        print("  " + l)


if __name__ == "__main__":
    main()
