"""src tgz 产物的打包（bundle 由 lib/docker.py 直出 gzip）。"""

import shutil
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def human_size(num_bytes):
    num_bytes = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


def copy_repo_scripts(staging):
    """把仓库 scripts/ 一并放进 src 产物（内网可复用的下载工具）。"""
    src = REPO_ROOT / "scripts"
    dst = Path(staging) / "scripts"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def make_src_tgz(staging, out_file):
    """打包运行时源码产物，顶层目录为 devcontainer-src/。"""
    with tarfile.open(out_file, "w:gz") as tar:
        tar.add(staging, arcname="devcontainer-src")
    return out_file
