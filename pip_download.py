#!/usr/bin/env python3
import click
import subprocess
import os
import shutil
import tarfile
from pathlib import Path


def load_env():
    env_file = Path(".env.pip")
    env_vars = {}
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars


def get_param_value(env_vars, key, default):
    if key in os.environ:
        return os.environ[key]
    if key in env_vars:
        return env_vars[key]
    return default


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--platform",
    "-p",
    multiple=True,
    help="目标平台 [linux, win], 可传入多个",
)
@click.option(
    "--arch",
    "-a",
    help="目标架构 [x86_64, amd64, arm64, aarch64]",
)
@click.option(
    "--python-version",
    "-v",
    help="Python版本 [36, 38, 39, 310, 311, 312, 313, ...]",
)
@click.option(
    "-d",
    help="下载目录, 默认值为 ./wheels",
)
@click.option(
    "-r",
    help="依赖文件 [auto, requirements.txt, 自定义文件路径]",
)
@click.option(
    "--index-url",
    "--index",
    "-i",
    help="pip镜像源",
)
@click.option(
    "--need-pack/--no-need-pack",
    help="是否在下载完成后打包",
    default=None,
)
@click.argument("packages", nargs=-1)
def main(platform, arch, python_version, d, r, index_url, need_pack, packages):
    env_vars = load_env()

    default_platform = get_param_value(env_vars, "PLATFORM", "linux")
    default_arch = get_param_value(env_vars, "ARCH", "x86_64")
    default_python_version = get_param_value(env_vars, "PYTHON_VERSION", "312")
    default_d = get_param_value(env_vars, "D", "./wheels")
    default_r = get_param_value(env_vars, "R", "requirements.txt")
    default_index_url = get_param_value(env_vars, "INDEX_URL", None)
    
    # 命令行参数优先级最高
    if need_pack is None:
        need_pack_str = get_param_value(env_vars, "NEED_PACK", "false")
        need_pack = need_pack_str.lower() in ["true", "1", "yes"]

    target_platforms = list(platform) if platform else [default_platform]
    target_arch = arch if arch else default_arch
    target_python_version = python_version if python_version else default_python_version
    target_d = d if d else default_d
    target_r = r if r else default_r
    target_index_url = index_url if index_url else default_index_url

    target_r = "requirements.txt" if target_r.lower() == "auto" else target_r

    for plat in target_platforms:
        if plat == "linux":
            if target_arch in ["x86_64", "amd64"]:
                pip_platform = "manylinux_2_17_x86_64"
            elif target_arch in ["arm64", "aarch64"]:
                pip_platform = "manylinux_2_17_aarch64"
            else:
                click.echo(f"Error: 不支持的架构 {target_arch} 用于平台 {plat}", err=True)
                return
        elif plat == "win":
            if target_arch in ["x86_64", "amd64"]:
                pip_platform = "win_amd64"
            elif target_arch in ["arm64", "aarch64"]:
                pip_platform = "win_arm64"
            else:
                click.echo(f"Error: 不支持的架构 {target_arch} 用于平台 {plat}", err=True)
                return
        else:
            click.echo(f"Error: 不支持的平台: {plat}", err=True)
            return

        py_version_str = target_python_version
        cp_version = f"cp{py_version_str}"
        abi_version = f"{cp_version}"
        py_tag = f"py{py_version_str}"

        cmd = [
            "pip", "download",
            "--only-binary=:all:",
            "--platform", pip_platform,
            "--python-version", py_version_str,
            # "--implementation", "cp",
            # "--abi", abi_version,
            "-d", target_d
        ]

        if target_index_url:
            cmd.extend(["--index-url", target_index_url])

        if target_r and target_r.strip() and os.path.exists(target_r):
            cmd.extend(["-r", target_r])

        if packages:
            cmd.extend(packages)

        click.echo(f"执行命令: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True)
            click.echo(f"平台 {plat} 下载完成")
        except subprocess.CalledProcessError as e:
            click.echo(f"平台 {plat} 下载失败: {e}", err=True)

    if need_pack:
        click.echo("\n开始打包...")
        
        d_path = Path(target_d)
        if not d_path.exists():
            click.echo(f"Error: 目录 {target_d} 不存在，无法打包", err=True)
            return

        if target_r and target_r.strip() and os.path.exists(target_r):
            r_src = Path(target_r)
            r_dest = d_path / r_src.name
            shutil.copy2(r_src, r_dest)
            click.echo(f"已复制 {target_r} 到 {target_d}")
            
            # 在文件开头添加 pip install 参数
            with open(r_dest, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(r_dest, 'w', encoding='utf-8') as f:
                f.write("--no-index --find-links=./\n")
                f.write(content)
            click.echo(f"已在 requirements.txt 开头添加 pip install 参数")

        tarballs_dir = Path("./tarballs")
        tarballs_dir.mkdir(exist_ok=True)
        
        # 标准化架构名称用于文件名
        if target_arch in ["x86_64", "amd64"]:
            file_arch = "x86_64"
        elif target_arch in ["arm64", "aarch64"]:
            file_arch = "arm64"
        else:
            file_arch = target_arch
        
        # 使用第一个平台（支持多平台，但打包文件只使用第一个）
        pack_platform = target_platforms[0] if target_platforms else "linux"
        
        tar_filename = f"wheels_{pack_platform}_{file_arch}_py{target_python_version}.tar.gz"
        tar_path = tarballs_dir / tar_filename
        
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(target_d, arcname=os.path.basename(target_d))
        
        click.echo(f"打包完成: {tar_path}")


if __name__ == "__main__":
    main()
