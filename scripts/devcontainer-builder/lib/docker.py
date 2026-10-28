"""docker buildx 构建、外挂服务镜像拉取与 docker save。"""

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


def save_images(images, out_tar):
    out_tar = Path(out_tar)
    out_tar.parent.mkdir(parents=True, exist_ok=True)
    _run(["docker", "save", "-o", str(out_tar), *images])
