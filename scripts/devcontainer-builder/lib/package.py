"""src tgz 产物的打包（bundle 由 lib/docker.py 直出 gzip）。"""

import tarfile
from pathlib import Path


def human_size(num_bytes):
    num_bytes = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


def make_src_tgz(staging, out_file):
    """打包运行时源码产物，顶层目录为 devcontainer-src/。"""
    with tarfile.open(out_file, "w:gz") as tar:
        tar.add(staging, arcname="devcontainer-src")
    return out_file
