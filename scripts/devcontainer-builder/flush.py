#!/usr/bin/env python3
"""部署服务器端脚本：读取 sync.json，把代码压缩包解压替换到 ./src 目录。

用法（在接收 src 压缩包与 sync.json 的目录中执行）:
    python flush.py          # 校验 + 展示计划 + 输入 y 确认后替换 ./src
    python flush.py -y       # 跳过交互确认直接执行

协议说明:
    部署目录固定为 ./src —— 与 install.sh 的默认安装路径 ../src/ 一致
    （compose 模板中 ${SRC_ROOT:-./src/} 把该目录挂载为容器内 /app）。

流程:
    1. 读取 sync.json，取打包文件名与打包方法，并校验压缩包 SHA256
    2. 展示将要发生什么，等待手动输入 y 确认（-y 跳过）
    3. 清空 ./src 目录下的所有内容
    4. 按打包方法解压压缩包内容到 ./src（不会自动运行任何代码）
"""

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from zipfile import ZipFile

SYNC_JSON = "sync.json"
SRC_DIR = "src"


def die(msg):
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(1)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(archive, fmt, dest_tmp):
    """解压到临时目录，返回内容根（压缩包只有单个顶层目录时进入该目录）。"""
    if fmt == "tgz":
        with tarfile.open(archive, "r:gz") as tar:
            try:
                tar.extractall(dest_tmp, filter="data")
            except TypeError:  # 兼容未实现 extraction filter 的旧版 Python
                tar.extractall(dest_tmp)
    else:
        with ZipFile(archive) as zf:
            zf.extractall(dest_tmp)
    entries = list(Path(dest_tmp).iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return Path(dest_tmp)


def main():
    parser = argparse.ArgumentParser(
        description="读取 sync.json 并把代码压缩包解压替换到 ./src 目录"
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="跳过交互确认直接执行"
    )
    args = parser.parse_args()

    # 1. 读取 sync.json
    here = Path.cwd()
    meta_path = here / SYNC_JSON
    if not meta_path.is_file():
        die(
            f"未找到 {meta_path}（请在与 src 压缩包、sync.json 同级的目录中运行 flush.py）"
        )
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"sync.json 解析失败: {e}")

    fmt = str(meta.get("format", "")).strip().lower()
    filename = str(meta.get("filename", "")).strip()
    digest = str(meta.get("sha256", "")).strip().lower()
    if fmt not in ("tgz", "zip"):
        die(f"sync.json 的打包方法无法识别: {meta.get('format')!r}（仅支持 tgz / zip）")
    if not filename:
        die("sync.json 缺少 filename 字段")
    archive = here / filename
    if not archive.is_file():
        die(f"压缩包不存在: {archive}")

    # SHA256 校验（与 sync.json 中记录的 checksum 对比，损坏即中止）
    actual = sha256_of(archive)
    if digest and actual != digest:
        die(
            "SHA256 校验失败，文件可能损坏或不完整，已中止:\n"
            f"  sync.json: {digest}\n"
            f"  实际:      {actual}"
        )
    checksum_note = "已通过校验" if digest else "sync.json 未提供 sha256，跳过校验"

    # 2. 展示将要发生什么，等待手动确认
    src = here / SRC_DIR
    print("== 执行 flush 将发生 ==")
    print(f"  压缩包: {archive.name}（{fmt}，打包时间 {meta.get('time', '未知')}）")
    print(f"  SHA256: {checksum_note}")
    print(f"  目标目录: {src.resolve()}")
    print(f"  将清空 {SRC_DIR}/ 下的所有内容，再解压新代码（不会自动运行任何代码）")
    if not args.yes:
        try:
            answer = input("确认执行 flush? 输入 y 继续: ")
        except (EOFError, KeyboardInterrupt):
            print()
            die("已取消")
        if answer.strip().lower() != "y":
            die("已取消")

    # 3. 清空 ./src 下的所有内容（目录不存在则创建）
    src.mkdir(exist_ok=True)
    for entry in src.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    # 4. 解压到临时目录后把内容移入 ./src
    with tempfile.TemporaryDirectory(prefix="flush-") as tmp:
        top = extract(archive, fmt, tmp)
        for item in sorted(top.iterdir()):
            shutil.move(str(item), src / item.name)

    print(f"== flush 完成: 新代码已就位 {src.resolve()} ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
