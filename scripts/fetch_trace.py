"""Phase 1: Loghub trace 自动化拉取（多源回退 + 格式校验）。

已验证源（本机网络可达）：
  1. gitcode 镜像（raw.gitcode.com，真实下载地址）
  2. gitcode /raw/ 端点（部分资源）
  3. 官方 GitHub raw / Zenodo（视网络可达性）
文件已存在且格式合法则跳过。
"""
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
from common import log

SOURCES = {
    "BGL": [
        "https://raw.gitcode.com/gh_mirrors/lo/loghub/raw/master/BGL/BGL_2k.log",
        "https://gitcode.com/gh_mirrors/lo/loghub/raw/master/BGL/BGL_2k.log",
    ],
    "HDFS": [
        "https://raw.gitcode.com/gh_mirrors/lo/loghub/raw/master/HDFS/HDFS_2k.log",
        "https://gitcode.com/gh_mirrors/lo/loghub/raw/master/HDFS/HDFS_2k.log",
    ],
}


def validate_format(path, min_lines=100, min_fields=9):
    n = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("<!DOCTYPE") or line.startswith("<html"):
                return False
            if len(line.split(" ")) >= min_fields:
                n += 1
            if n >= min_lines:
                return True
    return n >= min_lines


def fetch(dataset="BGL", dest_dir="data", force=False):
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{dataset}_2k.log")
    if os.path.exists(dest) and validate_format(dest) and not force:
        log.info("%s 已存在且格式合法，跳过下载", dest)
        return dest
    for url in SOURCES[dataset]:
        try:
            log.info("尝试下载 %s -> %s", url, dest)
            urllib.request.urlretrieve(url, dest)
            if validate_format(dest):
                log.info("下载成功并校验通过: %s", dest)
                return dest
            log.warning("下载内容格式非法: %s", url)
        except Exception as e:
            log.warning("下载失败 %s: %s", url, e)
    raise RuntimeError(f"全部数据源不可达: {dataset}")


if __name__ == "__main__":
    ds = sys.argv[1] if len(sys.argv) > 1 else "BGL"
    base = common.BASE
    fetch(ds, os.path.join(base, "data"))
