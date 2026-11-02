"""生成 GITHUB_STEP_SUMMARY（构建摘要）与 GITHUB_OUTPUT（产物路径等输出）。"""

import os
from pathlib import Path

from .package import human_size, tree_size
from .params import Params


def _yes_no(flag):
    return "是" if flag else "否"


def build_markdown(p, results):
    """按计划书 4.7 生成 Summary markdown。"""
    wheels_count = results.get("wheels_count", 0)
    images = results.get("images") or [p.prod_image]
    src_dir = results.get("src_dir")
    bundle_tar = results.get("bundle_tar")
    skipped_docker = results.get("skipped_docker", False)

    out = []
    out.append("## 离线开发环境构建摘要")
    out.append("")
    out.append("| 项目 | 值 |")
    out.append("| --- | --- |")
    out.append(f"| 名称 (NAME) | `{p.name}` |")
    out.append(f"| TAG | `{p.tag}` |")
    out.append(f"| 目标平台 | `{p.docker_platform}` |")
    out.append(f"| Python 版本 | `{p.python_version}` |")
    out.append(f"| glibc (wheel 标签) | `{p.glibc_version}` → `{p.pip_platform_tag}` |")
    out.append(f"| pip 镜像源 | `{p.pip_mirror}` ({p.mirror_url}) |")
    out.append(f"| wheels 数量 | {wheels_count} |")
    out.append("")

    out.append("### pip 包清单")
    out.append("")
    if p.pip_package_list:
        out.extend(f"- `{x}`" for x in p.pip_package_list)
    else:
        out.append("- (无)")
    out.append("")

    out.append("### APT 工具")
    out.append("")
    if p.apt_package_list:
        out.extend(f"- `{x}`" for x in p.apt_package_list)
    else:
        out.append("- (无)")
    out.append("")

    out.append("### 个性化安装命令")
    out.append("")
    if p.custom_install_cmd:
        out.append("```bash")
        out.append(p.custom_install_cmd)
        out.append("```")
    else:
        out.append("- (无)")
    out.append("")

    out.append("### 外挂服务")
    out.append("")
    out.append("| 服务 | 启用 | app 依赖 (depends_on) |")
    out.append("| --- | --- | --- |")
    out.append(f"| nginx | {_yes_no(p.enable_nginx)} | {_yes_no(p.app_depends_on_nginx)} |")
    out.append(f"| postgres | {_yes_no(p.enable_postgres)} | {_yes_no(p.app_depends_on_postgres)} |")
    out.append("")

    out.append("### 生成的镜像")
    out.append("")
    out.extend(f"- `{img}`" for img in images)
    if skipped_docker:
        out.append("")
        out.append("> 注意: 本次设置了 DEVCONTAINER_SKIP_DOCKER=1，未执行 docker"
                    " 构建/保存，因此没有 bundle 产物。")
    out.append("")

    out.append("### 产物清单")
    out.append("")
    out.append("| Artifact（下载后为 zip） | 内容 | 大小 |")
    out.append("| --- | --- | --- |")
    if src_dir:
        out.append(f"| `{p.src_artifact_name}` | 解压得 `{p.name}/` 源码目录 | "
                   f"{human_size(tree_size(src_dir))} |")
    if bundle_tar:
        out.append(f"| `{p.bundle_artifact_name}` | 解压得 `images.tar`（docker save） | "
                   f"{human_size(Path(bundle_tar).stat().st_size)} |")
    out.append("")

    out.append("### 内网使用步骤")
    out.append("")
    out.append("1. 从本次运行页面底部 **Artifacts** 下载两个产物"
               "（GitHub artifact 本身就是 zip），传输到与目标平台一致的内网机器。")
    out.append("2. 解压 `bundle` zip 得到 `images.tar`，导入镜像:")
    out.append("")
    out.append("```bash")
    out.append("docker load -i images.tar")
    out.append("```")
    out.append("")
    out.append("3. 解压 `src` zip 得到文件夹并进入目录:")
    out.append("")
    out.append("```bash")
    out.append(f"cd {p.name}")
    out.append("```")
    out.append("")
    out.append(f"4. 将应用代码放入该目录，并编辑 `docker-compose.yaml` 重写 app 服务的 "
               f"`command`（默认 `['bash']`，exec 数组形式），"
               f"例如 `command: [\"python\", \"main.py\"]`。")
    out.append("")
    if p.build_dev_image:
        out.append("5. 开发调试:")
        out.append("")
        out.append("```bash")
        out.append("make shell      # 交互式 bash")
        out.append("make lint       # ruff check .")
        out.append("make compile    # python -m compileall -q .")
        out.append("make test       # pytest -q")
        out.append("```")
        out.append("")
        out.append("6. 运行服务:")
    else:
        out.append("5. 运行服务（本次未构建 dev 镜像，无 make shell/lint/test 目标）:")
    out.append("")
    out.append("```bash")
    out.append("make up")
    out.append("make logs")
    out.append("make down")
    out.append("```")
    out.append("")
    if p.enable_postgres:
        out.append("postgres 已启用: 连接串 "
                   "`postgres://postgres:postgres@postgres:5432/postgres`，"
                   "数据持久化在 `pgdata` 卷。")
        out.append("")
    if p.enable_nginx:
        out.append("nginx 已启用: 宿主机 `http://<host>:8080` → 容器 80 端口。")
        out.append("")
    out.append("> 完整手册见仓库 `docs/offline-devcontainer.md`。")
    out.append("")
    return "\n".join(out)


def emit(p, results):
    """写入 GITHUB_STEP_SUMMARY 与 GITHUB_OUTPUT（不在 Actions 环境时打印到终端）。"""
    md = build_markdown(p, results)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(md)
        print(f"== Summary 已写入 {summary_path} ==")
    else:
        print(md)

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        entries = [
            ("name", p.name),
            ("tag", p.tag),
            ("src_name", p.src_artifact_name),
            ("src_dir", str(results["src_dir"])),
        ]
        bundle_tar = results.get("bundle_tar")
        if bundle_tar:
            entries.append(("bundle_name", p.bundle_artifact_name))
            entries.append(("bundle_tar", str(bundle_tar)))
        entries.append(("images", ",".join(results.get("images") or [])))
        with open(output_path, "a", encoding="utf-8") as f:
            for key, value in entries:
                f.write(f"{key}={value}\n")
        print(f"== Outputs 已写入 {output_path} ==")
