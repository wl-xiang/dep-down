"""产物整理：src 交付目录（供 upload-artifact 直接封装为 zip）与大小工具。

src 产物不再打 tgz：交付目录 dist/out/<name>/ 由 workflow 的
upload-artifact 上传（其父目录为 zip 根），下载解压即得 <name>/ 文件夹。
bundle 产物为 dist/build/images.tar（docker save 输出），同样直接上传。
"""

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def human_size(num_bytes):
    num_bytes = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


def tree_size(path):
    """目录内所有文件的字节总大小。"""
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def copy_repo_scripts(staging):
    """把仓库 scripts/ 一并放进 src 产物（内网可复用的下载工具）。"""
    src = REPO_ROOT / "scripts"
    dst = Path(staging) / "scripts"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
