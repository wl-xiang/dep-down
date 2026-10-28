"""pip download 执行模块：按目标平台/python/glibc 下载 wheels。

与 scripts/pip/pip_download.py 的关系：复用其下载逻辑
（--only-binary=:all: + manylinux 平台标签 + --python-version 交叉下载），
但这里直接调用 `python -m pip download`，原因有二：

1. pip（>= 25）对显式传入的 --platform 不再向低版本 glibc 标签展开，
   例如请求 manylinux_2_28_aarch64 时，只带
   manylinux_2_17_aarch64.manylinux2014_aarch64 复合标签的 wheel（如 ruff）
   会匹配失败。本模块按目标 glibc 向下展开为多个 --platform 一并传入，
   保证 "wheel 兼容目标 glibc" 的语义（低版本标签的 wheel 可在高版本
   glibc 上运行）。
2. pip_download.py 会吞掉 pip 的失败退出码（最终 exit 0），只能靠日志
   扫描判断成败；直接调用可以严格依赖返回码。
"""

import subprocess
import sys
from pathlib import Path

from .params import Params  # noqa: F401  (类型标注用)

# manylinux 标签可能出现的 glibc 次版本范围（2.17 起为 PEP 600 常用下限）
_GLIBC_MINORS = [f"2.{i}" for i in range(17, 35)]


def platform_tags(p):
    """按目标 glibc 向下展开的 manylinux 平台标签列表（含 2.17 的传统别名 manylinux2014）。"""
    arch = p.pip_arch
    tags = [
        f"manylinux_{minor.replace('.', '_')}_{arch}"
        for minor in _GLIBC_MINORS
        if minor <= p.glibc_version
    ]
    # manylinux2014 ≡ manylinux_2_17，部分 wheel 只带其中一种形式
    tags.append(f"manylinux2014_{arch}")
    return tags


def download_wheels(p, staging):
    """下载 wheels 到 staging/wheels/，返回 wheel 数量。

    无任何依赖可下载时（未指定 pip 包且不构建 dev 镜像）直接返回 0。
    """
    wheels_dir = Path(staging) / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)

    user_pkgs = p.pip_package_list
    dev_tools = p.dev_pip_tools
    if not user_pkgs and not dev_tools:
        print("== 未指定 pip 包且不构建 dev 镜像，跳过 pip download ==")
        return 0

    cmd = [
        sys.executable, "-m", "pip", "download",
        "--only-binary=:all:",
        "--python-version", p.python_version,
        "-d", str(wheels_dir),
    ]
    for tag in platform_tags(p):
        cmd += ["--platform", tag]
    if p.mirror_url:
        cmd += ["--index-url", p.mirror_url]
    if user_pkgs:
        cmd += ["-r", str(Path(staging) / "requirements.txt")]
    if dev_tools:
        cmd += dev_tools

    print("== 执行 pip download ==")
    print(" ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"pip download 失败（退出码 {e.returncode}），请检查上方日志中的 ERROR 信息"
        ) from e

    whls = sorted(wheels_dir.glob("*.whl"))
    if not whls:
        raise RuntimeError("wheels/ 下没有任何 .whl 文件，pip download 可能失败")
    print(f"== pip download 完成，共 {len(whls)} 个 wheel ==")
    return len(whls)
