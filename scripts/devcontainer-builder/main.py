#!/usr/bin/env python3
"""离线 Python 开发环境镜像构建入口。

执行序列（对应计划书 4.6）:
    1. 读取环境变量 → lib/params.py 解析与校验
    2. lib/render.py 渲染 Dockerfile / docker-compose.yml.tpl / Makefile /
       requirements.txt / main.py 占位 / install.sh / readme.html /
       .dockerignore / .gitignore
    3. lib/pip.py 复用 pip_download 逻辑下载 wheels/
    4. lib/docker.py buildx 构建 prod(/dev)、拉取外挂镜像、docker save 直出 gzip
    5. lib/package.py 打包 devcontainer-src_<ts>.tgz；镜像归档
       devcontainer-docker-images_<ts>.tgz 已在上一步直出；
       install.sh 与 readme.html 写入 dist/
    6. lib/summary.py 写 GITHUB_STEP_SUMMARY / GITHUB_OUTPUT，
       上传唯一 Artifact：devcontainer-bundle_<ts>（zip，内含镜像归档 tgz、
       src tgz、install.sh 与 readme.html 四个文件）

本地联调可设置 DEVCONTAINER_SKIP_DOCKER=1 跳过 docker 步骤。
"""

import os
import shutil
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import docker as docker_mod  # noqa: E402
from lib import package as package_mod  # noqa: E402
from lib import params as params_mod  # noqa: E402
from lib import pip as pip_mod  # noqa: E402
from lib import render as render_mod  # noqa: E402
from lib import summary as summary_mod  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

SKIP_DOCKER_VALUES = {"1", "true", "yes"}


def _annotation(message):
    one_line = " ".join(str(message).split())
    print(f"::error::{one_line}", file=sys.stderr)


def main():
    try:
        p = params_mod.load()
    except params_mod.ParamError as e:
        _annotation(f"参数校验失败: {e}")
        return 2

    print("== 参数 ==")
    print(f"  platform={p.docker_platform} python={p.python_version} "
          f"glibc={p.glibc_version} ({p.pip_platform_tag}) "
          f"mirror={p.pip_mirror} ts={p.ts} (UTC+8) image_tag={p.tag}")
    print(f"  pip_packages={p.pip_package_list} apt_packages={p.apt_package_list} "
          f"build_dev_image={p.build_dev_image} dev_image_only={p.dev_image_only}")
    print(f"  nginx={p.enable_nginx}(depends={p.app_depends_on_nginx}) "
          f"postgres={p.enable_postgres}(depends={p.app_depends_on_postgres})")
    print(f"  lucide={p.enable_lucide} oracle_instantclient={p.enable_oracle_instantclient}")
    print(f"  preset_envs={[k for k, _v in p.preset_env_pairs]}")
    print(f"  node={p.enable_node}(v{p.node_version}) npm_packages={p.npm_package_list} "
          f"npm_packages_dir={p.npm_packages_dir}")

    work_dir = REPO_ROOT / "dist" / "devcontainer"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    staging = work_dir / "src"
    staging.mkdir(parents=True)

    # 1. 模板渲染（requirements.txt 供下一步 pip download 使用）
    render_mod.render_all(p, staging)

    # 2. pip download → wheels/
    wheels_count = pip_mod.download_wheels(p, staging)

    # 3. docker 构建 / 拉取 / 导出
    skip_docker = os.environ.get("DEVCONTAINER_SKIP_DOCKER", "").strip().lower() in SKIP_DOCKER_VALUES
    images = []
    images_tgz = None
    if skip_docker:
        print("== DEVCONTAINER_SKIP_DOCKER=1，跳过 docker 构建/保存（本地联调用）==")
    else:
        if p.dev_image_only:
            # 只构建 dev 镜像：部署与开发共用，镜像归档也仅包含这一个镜像
            print("== docker build (dev only) ==")
            docker_mod.build_image(p, staging, "dev", p.dev_image)
        else:
            print("== docker build (prod) ==")
            docker_mod.build_image(p, staging, "prod", p.prod_image)
            if p.build_dev_image:
                print("== docker build (dev) ==")
                docker_mod.build_image(p, staging, "dev", p.dev_image)
        docker_mod.pull_service_images(p)
        images = docker_mod.image_list(p)
        images_tgz = REPO_ROOT / "dist" / f"devcontainer-docker-images_{p.ts}.tgz"
        print("== docker save (gzip) ==")
        docker_mod.save_images(images, images_tgz)

    # 4. 打包产物
    # wheels/ 已在镜像构建阶段安装（BuildKit bind mount，不落入任何镜像层），
    # 不再随 src 产物分发；同时把 Dockerfile 改写为不含 wheels/ 的联网重建版本，
    # 避免引用不存在的目录
    shutil.rmtree(staging / "wheels", ignore_errors=True)
    render_mod.render_src_dockerfile(p, staging)
    # .dockerignore 供 src 产物分发（install.sh 安装/合并到用户项目根目录）。
    # 必须在 docker 构建之后才写入：staging 即构建上下文，若在构建前写入，
    # 其 wheels/ 排除规则会导致构建期引用 wheels 失败（Copy ignored file）
    (staging / ".dockerignore").write_text(
        render_mod.render_dockerignore(p), encoding="utf-8"
    )
    src_tgz = REPO_ROOT / "dist" / f"devcontainer-src_{p.ts}.tgz"
    package_mod.make_src_tgz(staging, src_tgz)
    print(f"== src 产物: {src_tgz} "
          f"({package_mod.human_size(src_tgz.stat().st_size)}) ==")

    # install.sh 与安装说明：独立文件（与两个 tgz 一同放进唯一的 bundle Artifact zip）
    install_sh = render_mod.render_install_sh(
        p, REPO_ROOT / "dist" / "install.sh"
    )
    print(f"== install 脚本: {install_sh} ==")
    readme_html = render_mod.render_readme_html(
        p, REPO_ROOT / "dist" / "readme.html"
    )
    print(f"== 安装说明: {readme_html} ==")

    if images_tgz is not None:
        print(f"== 镜像归档产物: {images_tgz} "
              f"({package_mod.human_size(images_tgz.stat().st_size)}) ==")

    # 5. Summary / Outputs
    results = {
        "src_tgz": src_tgz,
        "images_tgz": images_tgz,
        "install_sh": install_sh,
        "readme_html": readme_html,
        "images": images,
        "wheels_count": wheels_count,
        "skipped_docker": skip_docker,
    }
    summary_mod.emit(p, results)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _annotation(f"构建失败: {e}")
        sys.exit(1)
