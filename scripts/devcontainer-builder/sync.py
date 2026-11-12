#!/usr/bin/env python3
"""把本地项目打包并推送到远端部署服务器（SSH/SFTP，用户名 + 密码认证）。

用法（在本地项目根目录内执行）:
    python sync.py            # 打包 + 展示计划 + 输入 y 确认后上传
    python sync.py -y         # 跳过交互确认直接上传

环境变量（见同目录 .env.example，可复制为 .env 填写）:
    SYNC_REMOTE_HOST        远端服务器 IP / 主机名（必填）
    SYNC_REMOTE_PORT        SSH 端口（留空默认 22）
    SYNC_REMOTE_USER        SSH 用户名（必填）
    SYNC_REMOTE_PASSWORD    SSH 密码（必填）
    SYNC_REMOTE_PATH        远端项目部署路径（必填）
    SYNC_ARCHIVE_FORMAT     代码打包方式 tgz | zip（留空默认 tgz）

流程:
    1. pwd 取当前项目根目录的名称，然后到上一层目录执行打包
    2. 把项目文件夹打包为 src-buddle.tgz / src-buddle.zip
    3. 生成 sync.json：打包方法、打包时间、打包文件名、打包文件 SHA256
    4. 展示将要发生什么，等待手动输入 y 确认（-y 跳过）
    5. 通过 SFTP 把压缩包与 sync.json 上传到远端指定目录
       （上传后请在部署服务器上运行 flush.py 完成解压部署）
"""

import argparse
import hashlib
import json
import os
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ARCHIVE_STEM = "src-buddle"

ENV_KEYS = (
    "SYNC_REMOTE_HOST",
    "SYNC_REMOTE_PORT",
    "SYNC_REMOTE_USER",
    "SYNC_REMOTE_PASSWORD",
    "SYNC_REMOTE_PATH",
    "SYNC_ARCHIVE_FORMAT",
)


def die(msg):
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(1)


def load_env():
    """加载 .env（先当前目录，再脚本所在目录）；已有的进程环境变量优先。"""
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent / ".env"):
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def load_config():
    env = {k: os.environ.get(k, "").strip() for k in ENV_KEYS}
    missing = [
        k
        for k in (
            "SYNC_REMOTE_HOST",
            "SYNC_REMOTE_USER",
            "SYNC_REMOTE_PASSWORD",
            "SYNC_REMOTE_PATH",
        )
        if not env[k]
    ]
    if missing:
        die(
            "缺少必填环境变量: " + ", ".join(missing)
            + "（参考 .env.example，复制为 .env 填写）"
        )
    try:
        port = int(env["SYNC_REMOTE_PORT"]) if env["SYNC_REMOTE_PORT"] else 22
    except ValueError:
        die(f"SYNC_REMOTE_PORT 必须是整数，当前: {env['SYNC_REMOTE_PORT']!r}")
    fmt = env["SYNC_ARCHIVE_FORMAT"].lower() or "tgz"
    if fmt not in ("tgz", "zip"):
        die(f"SYNC_ARCHIVE_FORMAT 仅支持 tgz / zip，当前: {fmt}")
    return {
        "host": env["SYNC_REMOTE_HOST"],
        "port": port,
        "user": env["SYNC_REMOTE_USER"],
        "password": env["SYNC_REMOTE_PASSWORD"],
        "path": env["SYNC_REMOTE_PATH"],
        "format": fmt,
    }


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pack(project_dir, out_file):
    """在上一层目录把项目文件夹打包（顶层目录名 = 项目根目录名）。"""
    if out_file.suffix == ".zip":
        with ZipFile(out_file, "w", ZIP_DEFLATED) as zf:
            for p in sorted(project_dir.rglob("*")):
                zf.write(p, p.relative_to(project_dir.parent))
    else:
        with tarfile.open(out_file, "w:gz") as tar:
            tar.add(project_dir, arcname=project_dir.name)


def ensure_remote_dir(sftp, remote_path):
    """远端目录不存在时逐级创建（等效 mkdir -p，仅支持 POSIX 路径）。"""
    cur = ""
    for part in [p for p in remote_path.rstrip("/").split("/") if p]:
        cur += "/" + part
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def upload(cfg, local_files):
    try:
        import paramiko
    except ImportError:
        die("需要 paramiko 库: pip install paramiko")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"== 连接 {cfg['user']}@{cfg['host']}:{cfg['port']} ==")
    client.connect(
        cfg["host"],
        port=cfg["port"],
        username=cfg["user"],
        password=cfg["password"],
        timeout=15,
    )
    try:
        sftp = client.open_sftp()
        ensure_remote_dir(sftp, cfg["path"])
        for local in local_files:
            remote = cfg["path"].rstrip("/") + "/" + local.name
            print(f"  上传 {local.name} -> {remote}")
            sftp.put(str(local), remote)
        sftp.close()
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(
        description="打包本地项目并通过 SFTP 推送到远端部署服务器"
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="跳过交互确认直接执行"
    )
    args = parser.parse_args()

    load_env()
    cfg = load_config()

    # 1. pwd 获取当前项目根目录名称
    project_dir = Path.cwd().resolve()
    if project_dir.parent == project_dir:
        die("请在项目目录内运行 sync.py（当前位于文件系统根目录）")
    parent = project_dir.parent

    # 2. cd 到上一层目录执行打包（压缩包放在项目目录旁，避免打进自身）
    archive = parent / f"{ARCHIVE_STEM}.{'tgz' if cfg['format'] == 'tgz' else 'zip'}"
    print(f"== 打包 {project_dir.name}/ ({cfg['format']}) ==")
    pack(project_dir, archive)
    digest = sha256_of(archive)

    # 3. 生成 sync.json（与压缩包同目录，随后一并上传）
    payload = {
        "format": cfg["format"],
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "filename": archive.name,
        "sha256": digest,
    }
    sync_json = parent / "sync.json"
    sync_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  {archive}  ({archive.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  SHA256: {digest}")
    print(f"  {sync_json}")

    # 4. 展示将要发生什么，等待手动确认
    print("== 执行 sync 将发生 ==")
    print(f"  打包方式: {cfg['format']}")
    print(f"  打包时间: {payload['time']}")
    print(f"  上传文件: {archive.name} 与 sync.json")
    print(f"  目标服务器: {cfg['user']}@{cfg['host']}:{cfg['port']}")
    print(f"  部署目录: {cfg['path']}")
    if not args.yes:
        try:
            answer = input("确认执行 sync? 输入 y 继续: ")
        except (EOFError, KeyboardInterrupt):
            print()
            die("已取消")
        if answer.strip().lower() != "y":
            die("已取消")

    # 5. SFTP 上传压缩包与 sync.json
    upload(cfg, [archive, sync_json])
    print("== 上传完成，请在部署服务器上运行 flush.py 完成解压部署 ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
