#!/usr/bin/env python3
import click
import subprocess
import os
import shutil
import tarfile
from pathlib import Path
from jinja2 import Template


def load_env():
    env_file = Path(".env.npm")
    env_vars = {}
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
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


def generate_package_json_from_pt(pt_file, template_file, output_file):
    with open(template_file, "r", encoding="utf-8") as f:
        template_content = f.read()
    
    template = Template(template_content)
    
    packages = []
    with open(pt_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                packages.append(line)
    
    rendered = template.render(packages=packages)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(rendered)
    
    return output_file


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--registry",
    "-r",
    help="npm镜像源",
)
@click.option(
    "--destination",
    "-d",
    help="下载目录",
)
@click.option(
    "--package-json",
    "-p",
    help="package.json文件路径",
)
@click.option(
    "--packages-txt",
    "--pt",
    help="packages.txt文件路径（一行一个包名）",
)
@click.option(
    "--need-pack/--no-need-pack",
    help="是否在下载完成后打包",
    default=None,
)
@click.argument("packages", nargs=-1)
def main(registry, destination, package_json, packages_txt, need_pack, packages):
    env_vars = load_env()

    default_registry = get_param_value(env_vars, "REGISTRY", "https://registry.npmjs.org")
    default_destination = get_param_value(env_vars, "D", "./packages")
    default_package_json = get_param_value(env_vars, "P", None)
    default_packages_txt = get_param_value(env_vars, "PT", None)
    need_pack_str = get_param_value(env_vars, "NEED_PACK", "false")

    # 命令行参数优先级最高
    if need_pack is None:
        need_pack = need_pack_str.lower() in ["true", "1", "yes"]

    target_registry = registry if registry else default_registry
    target_d = destination if destination else default_destination
    target_p = package_json if package_json else default_package_json
    target_pt = packages_txt if packages_txt else default_packages_txt

    d_path = Path(target_d)
    d_path.mkdir(exist_ok=True)

    generated_p = None
    if target_pt and Path(target_pt).exists():
        template_file = Path("package.json.j2")
        if template_file.exists():
            output_p = d_path / "package.json"
            generated_p = generate_package_json_from_pt(target_pt, template_file, output_p)
            click.echo(f"已基于 {target_pt} 生成 {generated_p}")
        else:
            click.echo(f"Error: 模板文件 {template_file} 不存在", err=True)
            return
    elif target_p and Path(target_p).exists():
        pass
    else:
        if not packages:
            click.echo("Error: 请指定 package.json、packages.txt 或包名", err=True)
            return

    # 检查 npo 是否可用
    npo_available = False
    try:
        # 尝试直接运行 npo
        result = subprocess.run(
            ["npo", "--version"], 
            capture_output=True, 
            text=True,
            shell=os.name == 'nt'  # Windows 上使用 shell
        )
        if result.returncode == 0:
            npo_available = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # 如果直接运行失败，尝试使用 npx
    if not npo_available:
        try:
            result = subprocess.run(
                ["npx", "npo", "--version"], 
                capture_output=True, 
                text=True,
                shell=os.name == 'nt'
            )
            if result.returncode == 0:
                npo_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    
    if not npo_available:
        click.echo("Error: npo 命令不可用，请先安装 npm-offline-packager", err=True)
        click.echo("运行: npm install -g npm-offline-packager", err=True)
        return
    
    cmd = ["npo", "fetch", "-d", target_d]
    
    if generated_p:
        cmd.extend(["-p", str(generated_p)])
    elif target_p and Path(target_p).exists():
        cmd.extend(["-p", target_p])
    
    if target_registry:
        cmd.extend(["--registry", target_registry])
    
    if packages:
        cmd.extend(packages)
    
    click.echo(f"执行命令: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, shell=os.name == 'nt')
        click.echo("下载完成")
    except subprocess.CalledProcessError as e:
        click.echo(f"下载失败: {e}", err=True)
        return

    if need_pack:
        click.echo("\n开始打包...")
        
        if not d_path.exists():
            click.echo(f"Error: 目录 {target_d} 不存在，无法打包", err=True)
            return

        if generated_p:
            pass
        elif target_p and Path(target_p).exists() and not (d_path / Path(target_p).name).exists():
            p_src = Path(target_p)
            p_dest = d_path / p_src.name
            shutil.copy2(p_src, p_dest)
            click.echo(f"已复制 {target_p} 到 {target_d}")

        tarballs_dir = Path("./tarballs")
        tarballs_dir.mkdir(exist_ok=True)
        
        tar_path = tarballs_dir / "packages.tar.gz"
        
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(target_d, arcname=os.path.basename(target_d))
        
        click.echo(f"打包完成: {tar_path}")


if __name__ == "__main__":
    main()
