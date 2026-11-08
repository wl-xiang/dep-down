"""生成 GITHUB_STEP_SUMMARY（构建摘要）与 GITHUB_OUTPUT（产物路径等输出）。"""

import hashlib
import os
from pathlib import Path

from .package import human_size
from .params import Params


def _yes_no(flag):
    return "是" if flag else "否"


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_markdown(p, results):
    """按计划书 4.7 生成 Summary markdown。"""
    wheels_count = results.get("wheels_count", 0)
    images = results.get("images") or [p.app_image]
    src_tgz = results.get("src_tgz")
    images_tgz = results.get("images_tgz")
    install_sh = results.get("install_sh")
    skipped_docker = results.get("skipped_docker", False)
    bundle_name = f"devcontainer-bundle_{p.ts}"

    out = []
    out.append("## 离线开发环境构建摘要")
    out.append("")
    out.append("| 项目 | 值 |")
    out.append("| --- | --- |")
    out.append(f"| 时间戳 (UTC+8) | `{p.ts}` |")
    out.append(f"| 镜像 TAG 后缀 | `{p.tag}` ({p.image_tag}) |")
    out.append(f"| 目标平台 | `{p.docker_platform}` |")
    out.append(f"| Python 版本 | `{p.python_version}` |")
    out.append(f"| glibc (wheel 标签) | `{p.glibc_version}` → `{p.pip_platform_tag}` |")
    out.append(f"| pip 镜像源 | `{p.pip_mirror}` ({p.mirror_url}) |")
    out.append(f"| wheels 数量 | {wheels_count} |")
    if p.dev_image_only:
        image_mode = "仅 dev 镜像（部署与开发共用，镜像归档只含该镜像）"
    elif p.build_dev_image:
        image_mode = "prod + dev 两个镜像"
    else:
        image_mode = "仅 prod 镜像"
    out.append(f"| 镜像模式 | {image_mode} |")
    out.append(f"| 应用监听端口 | {('`' + p.app_port + '`') if p.has_app_port else '(未指定)'} |")
    out.append(f"| env_file | {', '.join(p.env_file_list) if p.env_file_list else '(无)'} |")
    out.append(f"| SELinux 重打标签 (:z) | {_yes_no(p.selinux_relabel)} |")
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
                    " 构建/保存，因此没有镜像归档产物。")
    out.append("")

    out.append("### 产物清单")
    out.append("")
    out.append(f"唯一 Artifact：**{bundle_name}**（zip 封装、仅存储不压缩，"
               "解压即得以下三个文件）")
    out.append("")
    out.append("| 文件 | 大小 | SHA256 |")
    out.append("| --- | --- | --- |")
    if images_tgz:
        out.append(
            f"| {images_tgz.name}（镜像归档，docker load 用） "
            f"| {human_size(images_tgz.stat().st_size)} "
            f"| `{sha256_of(images_tgz)}` |"
        )
    if src_tgz:
        out.append(
            f"| {src_tgz.name} | {human_size(src_tgz.stat().st_size)} "
            f"| `{sha256_of(src_tgz)}` |"
        )
    if install_sh:
        out.append(
            f"| {install_sh.name}（安装脚本） | {human_size(install_sh.stat().st_size)} "
            f"| `{sha256_of(install_sh)}` |"
        )
    out.append("")

    out.append("### 内网使用步骤")
    out.append("")
    out.append("1. 从本次运行页面底部 **Artifacts** 下载唯一产物"
               f" **{bundle_name}**（zip 仅为封装、不压缩，解压得到"
               " 镜像归档 tgz、src tgz 与 install.sh 三个文件），"
               "传输到与目标平台一致的内网机器，并用上表 SHA256 校验完整性。")
    out.append("2. 导入镜像（tgz 是 gzip 压缩的镜像归档，可直接 load）:")
    out.append("")
    out.append("```bash")
    out.append(f"docker load -i devcontainer-docker-images_{p.ts}.tgz")
    out.append("```")
    out.append("")
    out.append("3. 安装到应用根目录（在 install.sh 与 src tgz 所在目录执行，"
               "参数为你的项目根目录；会把 src 解压到 `<项目根>/docs/devcontainer`、"
               "把 `docker-compose.yml.tpl` 复制到项目根目录为 `docker-compose.yml`，"
               "并在缺少 `main.py` 时放置占位入口）:")
    out.append("")
    out.append("```bash")
    out.append("bash install.sh ~/apps/myapp1")
    out.append("```")
    out.append("")
    out.append(f"4. 离线自检（确认镜像已导入、架构匹配；prod 命令为 `{p.prod_command}`):")
    out.append("")
    out.append("```bash")
    out.append("cd ~/apps/myapp1/docs/devcontainer")
    out.append("make check")
    out.append("```")
    out.append("")
    if p.dev_tools_enabled:
        out.append("5. 开发调试（均在 `docs/devcontainer` 目录执行）:")
        out.append("")
        out.append("```bash")
        out.append("make shell      # 交互式 bash")
        out.append("make lint       # ruff check .")
        out.append("make compile    # python -m compileall -q .")
        out.append("make test       # pytest -q")
        out.append("```")
        out.append("")
        out.append("6. 运行服务（`--no-build`，不会触发任何联网）:")
    else:
        out.append("5. 运行服务（本次未构建 dev 镜像，无 make shell/lint/test 目标）:")
    out.append("")
    out.append("```bash")
    out.append("make up")
    out.append("make logs")
    out.append("make down")
    out.append("```")
    out.append("")
    if p.has_app_port:
        out.append(f"应用端口 `{p.app_port}`: 已在 compose 中配置"
                   + ("（由 nginx 反代，仅容器网络暴露）。"
                      if p.enable_nginx else "（宿主机同端口映射）。"))
        out.append("")
    if p.enable_postgres:
        out.append("postgres 已启用: 连接串 "
                   "`postgres://postgres:postgres@postgres:5432/postgres`，"
                   "数据持久化在 `pgdata` 卷。")
        out.append("")
    if p.enable_nginx:
        out.append("nginx 已启用: 宿主机 `http://<host>:8080` → 容器 80 端口。")
        if p.has_app_port:
            out.append(f"已生成 `nginx/conf.d/default.conf`，反代到 `app:{p.app_port}`。")
        else:
            out.append("未指定 app_port，nginx 未生成反代配置，需自行挂载 "
                       "`nginx/conf.d/default.conf`。")
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
            ("ts", p.ts),
            ("image_tag", p.tag),
            # 唯一 Artifact 名（GitHub Actions 上传后为 devcontainer-bundle_<ts>.zip）
            ("bundle_name", f"devcontainer-bundle_{p.ts}"),
        ]
        src_tgz = results.get("src_tgz")
        images_tgz = results.get("images_tgz")
        install_sh = results.get("install_sh")
        if images_tgz:
            entries.append(("images_tgz", str(images_tgz)))
            entries.append(("images_name", images_tgz.name))
            entries.append(("images_sha256", sha256_of(images_tgz)))
        if src_tgz:
            entries.append(("src_tgz", str(src_tgz)))
            entries.append(("src_name", src_tgz.name))
            entries.append(("src_sha256", sha256_of(src_tgz)))
        if install_sh:
            entries.append(("install_sh", str(install_sh)))
            entries.append(("install_sha256", sha256_of(install_sh)))
        entries.append(("images", ",".join(results.get("images") or [])))
        with open(output_path, "a", encoding="utf-8") as f:
            for key, value in entries:
                f.write(f"{key}={value}\n")
        print(f"== Outputs 已写入 {output_path} ==")
