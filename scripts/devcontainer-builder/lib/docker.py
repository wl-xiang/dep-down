"""docker buildx 构建、外挂服务镜像拉取与 docker save（gzip 直出）。"""

import gzip
import shutil
import subprocess
from pathlib import Path

from .params import Params

# GitHub Actions 上由 docker/setup-buildx-action 提供 gha 缓存支持
BUILDX_CACHE_ARGS = ["--cache-from", "type=gha", "--cache-to", "type=gha,mode=max"]


def _run(cmd):
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def build_image(p, staging, target, image):
    """在 staging 目录上构建指定 target（prod/dev）的镜像并 --load 进 daemon。"""
    cmd = [
        "docker", "buildx", "build",
        "--platform", p.docker_platform,
        "--target", target,
        "-t", image,
        "--load",
        *BUILDX_CACHE_ARGS,
        str(staging),
    ]
    _run(cmd)


def pull_service_images(p):
    """按需拉取外挂服务镜像（与目标平台一致）。"""
    if p.enable_nginx:
        _run(["docker", "pull", "--platform", p.docker_platform, "nginx:stable"])
    if p.enable_postgres:
        _run(["docker", "pull", "--platform", p.docker_platform, "postgres:16"])


def image_list(p):
    """本次需要 docker save 的镜像清单。"""
    images = [p.prod_image]
    if p.build_dev_image:
        images.append(p.dev_image)
    if p.enable_nginx:
        images.append("nginx:stable")
    if p.enable_postgres:
        images.append("postgres:16")
    return images


def save_images(images, out_file):
    """docker save 输出直接流式经 gzip 写入 out_file。

    产物本身即 gzip 压缩的镜像归档（不再套一层包含 images.tar 的 tar），
    因此 `docker load -i <out_file>` 可直接导入。
    """
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["docker", "save", *images]
    print("+ " + " ".join(cmd) + f" | gzip > {out_file}")
    with gzip.open(out_file, "wb") as gz:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        try:
            shutil.copyfileobj(proc.stdout, gz, length=1 << 20)
        finally:
            proc.stdout.close()
            returncode = proc.wait()
    if returncode != 0:
        out_file.unlink(missing_ok=True)
        raise RuntimeError(f"docker save 失败（退出码 {returncode}）")
