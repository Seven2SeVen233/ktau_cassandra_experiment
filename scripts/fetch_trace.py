"""Phase 1: automated Loghub trace download (multi-source fallback + format
validation).

Verified sources (reachable from this host):
  1. gitcode mirror (raw.gitcode.com, real download URLs)
  2. gitcode /raw/ endpoint (some resources)
  3. official GitHub raw / Zenodo (depending on network reachability)
If the file already exists and is well-formed, downloading is skipped.
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
        log.info("%s exists and is well-formed; skipping download", dest)
        return dest
    for url in SOURCES[dataset]:
        try:
            log.info("attempting download %s -> %s", url, dest)
            urllib.request.urlretrieve(url, dest)
            if validate_format(dest):
                log.info("download succeeded and validated: %s", dest)
                return dest
            log.warning("downloaded content has invalid format: %s", url)
        except Exception as e:
            log.warning("download failed %s: %s", url, e)
    raise RuntimeError(f"all data sources unreachable: {dataset}")


if __name__ == "__main__":
    ds = sys.argv[1] if len(sys.argv) > 1 else "BGL"
    base = common.BASE
    fetch(ds, os.path.join(base, "data"))
