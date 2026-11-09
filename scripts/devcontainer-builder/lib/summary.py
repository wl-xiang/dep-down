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
    readme_html = results.get("readme_html")
    skipped_docker = results.get("skipped_docker", False)
    bundle_name = p.bundle_name

    out = []
    out.append("## 离线开发环境构建摘要")
    out.append("")
    out.append("| 项目 | 值 |")
    out.append("| --- | --- |")
    out.append(f"| 时间戳 (UTC+8) | `{p.ts}` |")
    out.append(f"| 镜像 TAG | `{p.tag}` ({p.image_tag}) |")
    out.append(f"| 目标平台 | `{p.docker_platform}` |")
    out.append(f"| Python 版本 | `{p.python_version}` |")
    out.append(f"| glibc (wheel 标签) | `{p.glibc_version}` → `{p.pip_platform_tag}` |")
    out.append(f"| pip 镜像源 | `{p.pip_mirror}` ({p.mirror_url}) |")
    out.append(f"| wheels 数量 | {wheels_count} |")
    out.append(f"| 预装 lucide 图标库 (pip) | {_yes_no(p.enable_lucide)} |")
    if p.oracle_full:
        oracle_mode = (
            "完整安装（客户端已打进镜像，"
            f"`ORACLE_HOME={p.oracle_client_dir}`）"
        )
    elif p.oracle_enabled:
        oracle_mode = (
            "仅运行时依赖（客户端由 compose 从宿主机只读挂载到 "
            f"`{p.oracle_client_dir}`）"
        )
    else:
        oracle_mode = "未启用（none）"
    out.append(f"| Oracle Instant Client 19 | {oracle_mode} |")
    if p.enable_node:
        node_mode = f"Node.js {p.node_version} + npm"
    else:
        node_mode = "未启用"
    out.append(f"| Node.js / npm | {node_mode} |")
    if p.enable_node:
        npm_pkg_summary = ", ".join(f"`{x}`" for x in p.npm_package_list) or "(无)"
        out.append(f"| npm 全局预装包 | {npm_pkg_summary} |")
        out.append(
            f"| npm 离线包目录 | `${{NPM_PACKAGES_DIR:-{p.npm_packages_dir}}}`"
            " → `/opt/npm-packages`（只读挂载） |"
        )
    env_summary = ", ".join(f"`{k}`" for k, _v in p.preset_env_pairs) or "(无)"
    out.append(f"| 预设环境变量 (app/dev) | {env_summary} |")
    if p.dev_image_only:
        image_mode = "仅 dev 镜像（部署与开发共用，镜像归档只含该镜像）"
    elif p.build_dev_image:
        image_mode = "prod + dev 两个镜像"
    else:
        image_mode = "仅 prod 镜像"
    out.append(f"| 镜像模式 | {image_mode} |")
    out.append(f"| 应用端口 (host:container) | {('`' + p.app_port + '`') if p.has_app_port else '(未指定)'} |")
    out.append(f"| env_file | {', '.join(p.env_file_list) if p.env_file_list else '(无)'} |")
    out.append(f"| SELinux 重打标签 (:z) | {_yes_no(p.selinux_relabel)} |")
    out.append("")

    out.append("### pip 包清单（含预装组件）")
    out.append("")
    if p.preinstall_pip_packages:
        for x in p.preinstall_pip_packages:
            note = ""
            if x == "lucide" and p.enable_lucide:
                note = "（预装：SVG 图标库）"
            elif x.startswith("oracledb") and p.oracle_enabled:
                note = "（预装：配合 Instant Client 19 连 Oracle 11g）"
            out.append(f"- `{x}`{note}")
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
               "解压即得以下四个文件）")
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
    if readme_html:
        out.append(
            f"| {readme_html.name}（安装说明） | {human_size(readme_html.stat().st_size)} | (HTML) |"
        )
    out.append("")

    out.append("### 内网使用步骤")
    out.append("")
    out.append("1. 从本次运行页面底部 **Artifacts** 下载唯一产物"
               f" **{bundle_name}**（zip 仅为封装、不压缩，解压得到"
               " 镜像归档 tgz、src tgz、install.sh 与 readme.html 四个文件），"
               "传输到与目标平台一致的内网机器，并用上表 SHA256 校验完整性。")
    out.append("")
    out.append("2. **把 artifact zip 包放到你的项目根目录 `dist/` 文件夹下**"
               "（没有就新建一个），然后在 `dist/` 里解压、就地安装："
               "place artifact zipball in project root `./dist/` dir, then"
               " unzip and run `./install.sh ../`")
    out.append("")
    out.append("```bash")
    out.append("mkdir -p /path/to/your-project/dist   # 项目根目录下的 dist/")
    out.append(f"# 把 {bundle_name}.zip 移入 dist/ 后：")
    out.append(f"cd /path/to/your-project/dist && unzip {bundle_name}.zip")
    out.append("bash install.sh --load ../              # --load 安装开始前自动 docker load 镜像归档")
    out.append("bash install.sh ../                     # 参数 ../ 即项目根目录（或改用上一行的 --load 一步到位）")
    out.append("```")
    out.append("")
    out.append("   install.sh 会把 `Makefile` / `build.sh` / `Dockerfile`"
               "（由 Dockerfile.addon 改名）/ `README-devcontainer.md`（由"
               " README.md 改名）/ `.dockerignore` / `.gitignore` 安装到项目"
               "根目录（同名文件已存在时终止安装，不覆盖），把 src 解压到"
               " `<项目根>/docs/devcontainer`（原始副本，用于重置），把"
               " `docker-compose.yml` 复制到项目根目录，并在缺少 `main.py` 时"
               "放置占位入口。")
    out.append("")
    out.append(f"3. 离线自检（回到**项目根目录**执行，确认镜像已导入、架构匹配；"
               f"prod 命令为 `{p.prod_command}`):")
    out.append("")
    out.append("```bash")
    out.append("cd /path/to/your-project")
    out.append("make check")
    out.append("```")
    out.append("")
    if p.dev_tools_enabled:
        out.append("4. 开发调试（均在**项目根目录**执行）:")
    else:
        out.append("4. 运行服务（本次未构建 dev 镜像，无 make shell/lint/test 目标）:")
    out.append("")
    out.append("```bash")
    if p.dev_tools_enabled:
        out.append("make shell      # 交互式 bash")
        out.append("make lint       # ruff check .")
        out.append("make compile    # python -m compileall -q .")
        out.append("make test       # pytest -q")
    out.append("make up")
    out.append("make logs")
    out.append("make down")
    out.append("```")
    out.append("")
    out.append("> 后续 make / build.sh 命令都在项目根目录执行；`docs/devcontainer/`"
               " 下是原始副本，改坏根目录文件时从那里复制回去重置，不要在该目录"
               "下直接运行任何脚本。")
    out.append("")
    if p.has_app_port:
        host_port, container_port = p.app_port_parts
        out.append(f"应用端口 `{host_port}:{container_port}`（host:container）: 已在 compose 中配置"
                   + (f"（app 仅容器网络 expose {container_port}，由 nginx 反代）。"
                      if p.enable_nginx else "（宿主机端口映射）。"))
        out.append("")
    if p.enable_postgres:
        out.append("postgres 已启用: 连接串 "
                   "`postgres://postgres:postgres@postgres:5432/postgres`，"
                   "数据持久化在 `pgdata` 卷。")
        out.append("")
    if p.enable_nginx:
        out.append("nginx 已启用: 宿主机 `http://<host>:8080` → 容器 80 端口。")
        if p.has_app_port:
            out.append(f"已生成 `nginx/conf.d/default.conf`，反代到 `app:{p.app_container_port}`。")
        else:
            out.append("未指定 app_port，nginx 未生成反代配置，需自行挂载 "
                       "`nginx/conf.d/default.conf`。")
        out.append("")
    if p.oracle_full:
        out.append("### Oracle Instant Client（已完整安装进镜像）")
        out.append("")
        out.append("镜像内**包含** Instant Client 19 Basic（构建期从 Oracle 官方直链"
                   "下载）与运行依赖 `libaio1` / `libnsl2`，并配置"
                   f" `ORACLE_HOME={p.oracle_client_dir}` / `LD_LIBRARY_PATH` /"
                   " `TNS_ADMIN`。客户端随镜像分发，无需宿主机挂载：")
        out.append("")
        out.append("```bash")
        out.append("# 验证 Thick 模式加载成功（输出 OCI OK）")
        out.append('docker compose run --rm app python -c "import oracledb; '
                   "oracledb.init_oracle_client(); print('OCI OK')\"")
        out.append("```")
        out.append("")
    elif p.oracle_enabled:
        out.append("### Oracle Instant Client（客户端由宿主机挂载）")
        out.append("")
        out.append("镜像内**不包含**客户端，仅安装 `libaio1` / `libnsl2` 并配置"
                   " `ORACLE_HOME` / `LD_LIBRARY_PATH` / `TNS_ADMIN`；客户端由"
                   " compose 只读挂载，同一服务器的多个容器共用一份：")
        out.append("")
        out.append("```bash")
        out.append(f"# 1. 宿主机准备 Instant Client 19 Basic 包，解压到 {p.oracle_client_dir}")
        out.append(f"ls -l {p.oracle_client_dir}/libclntsh.so.19.1")
        out.append("# 2. 非默认目录时（无需重建镜像）")
        out.append("export ORACLE_CLIENT_DIR=/data/instantclient19   # make up 前设置")
        out.append("make up")
        out.append("# 3. 验证 Thick 模式加载成功（输出 OCI OK）")
        out.append('docker compose run --rm app python -c "import oracledb; '
                   "oracledb.init_oracle_client(); print('OCI OK')\"")
        out.append("```")
        out.append("")
    if p.enable_node:
        out.append("### 前端离线开发（Node.js / npm）")
        out.append("")
        out.append(f"镜像内置 Node.js {p.node_version} + npm；Npm Download Action 的"
                   " `npm_packages` 产物（顶层 `packages/`）由 compose 只读挂载到"
                   " `/opt/npm-packages`：")
        out.append("")
        out.append("```bash")
        out.append(f"# 1. 把 Npm Download 产物的 packages/ 放到项目根 {p.npm_packages_dir}/")
        out.append("ls packages/*.tgz")
        out.append("# 2. 离线安装依赖到 /app")
        out.append("make npm-install")
        out.append("# 3. 启动前端开发服务器：把 prod_command 设为 npm run dev -- --host 0.0.0.0、")
        out.append("#    app_port 设为 5173:5173（vite）/ 8080:8080（webpack）后 make up；临时调试可用：")
        out.append("#    docker compose run --rm -p 5173:5173 dev npm run dev -- --host 0.0.0.0")
        out.append("```")
        out.append("")
        out.append(f"离线包目录可用 `NPM_PACKAGES_DIR` 覆盖（默认 `{p.npm_packages_dir}`）。")
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
            # 唯一 Artifact 名（GitHub Actions 上传后为 <prefix>_devcontainer_<ts>.zip）
            ("bundle_name", p.bundle_name),
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
        readme_html = results.get("readme_html")
        if readme_html:
            entries.append(("readme_html", str(readme_html)))
        entries.append(("images", ",".join(results.get("images") or [])))
        with open(output_path, "a", encoding="utf-8") as f:
            for key, value in entries:
                f.write(f"{key}={value}\n")
        print(f"== Outputs 已写入 {output_path} ==")
