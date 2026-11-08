"""模板渲染：读取 templates/ 下的模板文件，拼装生成最终文件。

使用简单的 {{PLACEHOLDER}} 字符串替换（不依赖 jinja2）。块级内容
（APT 安装、个性化命令、dev 阶段、compose 服务、Makefile dev 目标）
由本模块计算后填入对应占位符。
"""

import json
from pathlib import Path

from .params import Params

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# compose 中的 dev 服务（profile=dev，仅 make shell/lint/compile/test 时激活）
# build.dockerfile 指向 docs/devcontainer/Dockerfile（联网重建版 Dockerfile 位于
# 该目录，context 为项目根目录）
_DEV_SERVICE_TMPL = """\
  dev:
    image: {{DEV_IMAGE}}
    build:
      context: .
      dockerfile: docs/devcontainer/Dockerfile
      target: dev
    working_dir: /app
    pull_policy: never
    user: "${HOST_UID:-0}:${HOST_GID:-0}"
    volumes:
      - {{APP_VOLUME}}
    networks:
      - app-net
    profiles:
      - dev
"""

# Makefile 中依赖 dev 镜像的目标（需要 dev 工具时生成）
_DEV_MAKE_TARGETS = """\
check-dev: ## 检查 dev 镜像是否已导入（离线环境不会自行构建）
\t@docker image inspect {{DEV_IMAGE}} >/dev/null 2>&1 || { \\
\t\techo "dev 镜像 {{DEV_IMAGE}} 未导入：请先 docker load 镜像归档（或本次未构建 dev 镜像）"; \\
\t\texit 1; \\
\t}

shell: check-dev ## 进入 dev 容器交互式 bash
\t$(DEV_RUN)

dev: check-dev ## 等价于 shell
\t$(DEV_RUN)

lint: check-dev ## ruff 静态检查
\t$(DEV_RUN) ruff check .

compile: check-dev ## 字节码编译校验
\t$(DEV_RUN) python -m compileall -q .

test: check-dev ## 运行 pytest
\t$(DEV_RUN) pytest -q

"""

_DEV_PHONY = "check-dev shell dev lint compile test "

# Dockerfile.addon 中基于现有镜像的阶段（离线补装 Python 包，配合 build.sh）。
# requirements.txt 只在含有真实包名（非选项/注释/空行）时才按清单安装，
# 否则安装目录下全部 .whl——保证只有离线安装头（--no-index --find-links=./）
# 的空 requirements 不会静默装个寂寞。
_ADDON_STAGE_TMPL = """\
FROM {{BASE_IMAGE}} AS {{STAGE_NAME}}

# wheels 只在本层临时存在：install 与 rm 同层执行，不增大最终镜像
COPY wheels/ /tmp/addon-wheels/
RUN set -eux; \\
    if [ -f /tmp/addon-wheels/requirements.txt ] \\
        && grep -Ev '^[[:space:]]*(#|--|$)' /tmp/addon-wheels/requirements.txt \\
        | grep -q .; \\
    then \\
        pip install --no-index --find-links=/tmp/addon-wheels \\
            -r /tmp/addon-wheels/requirements.txt; \\
    else \\
        pip install --no-index --find-links=/tmp/addon-wheels \\
            /tmp/addon-wheels/*.whl; \\
    fi; \\
    rm -rf /tmp/addon-wheels
"""


def _addon_targets(p):
    """(Dockerfile target, 基础镜像, stage 名) 列表，与本次构建出的应用镜像一一对应。"""
    targets = []
    if p.dev_image_only:
        targets.append(("addon-dev", p.dev_image, "dev"))
    else:
        targets.append(("addon-prod", p.prod_image, "prod"))
        if p.build_dev_image:
            targets.append(("addon-dev", p.dev_image, "dev"))
    return targets


def render_dockerfile_addon(p):
    stages = "\n\n".join(
        _sub(_ADDON_STAGE_TMPL, {"BASE_IMAGE": image, "STAGE_NAME": target})
        for target, image, _stage in _addon_targets(p)
    )
    return _sub(_load("Dockerfile.addon.tmpl"), {**_base_mapping(p),
                                                 "ADDON_STAGES": stages})


def render_build_sh(p):
    """build.sh：docker build Dockerfile.addon，默认新 TAG 后缀为 addon-<时间戳>，
    新镜像命名沿用 <前缀>:<stage>-<TAG 后缀>（如 <前缀>:dev-addon-<ts>）。"""
    calls = "\n".join(
        f'build {target} "{image}" "{stage}-$NEW_SUFFIX"'
        for target, image, stage in _addon_targets(p)
    )
    return _sub(_load("build.sh.tmpl"), {**_base_mapping(p), "BUILD_CALLS": calls})


def _load(name):
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _sub(text, mapping):
    for key, value in mapping.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _base_mapping(p):
    return {
        # TS = 构建时间戳（UTC+8，用于产物文件名）；TAG = 镜像 TAG 后缀（latest 或时间戳）
        "TS": p.ts,
        "TAG": p.tag,
        "PLATFORM": p.platform,
        "DOCKER_PLATFORM": p.docker_platform,
        "PYTHON_VERSION": p.python_version,
        "GLIBC_VERSION": p.glibc_version,
        "MANYLINUX_LABEL": p.manylinux_label,
        "PIP_PLATFORM_TAG": p.pip_platform_tag,
        "PIP_MIRROR": p.pip_mirror,
        "MIRROR_URL": p.mirror_url,
        "IMAGE_PREFIX": p.image_prefix,
        "PROD_IMAGE": p.prod_image,
        "APP_IMAGE": p.app_image,
        "APP_BUILD_TARGET": p.app_build_target,
        "APP_SOURCE_DIR": p.app_source_dir,
        "APP_VOLUME": json.dumps(p.mount_path),
        "NEEDS_MAIN_PY": "1" if p.prod_command == "python main.py" else "0",
        "IMAGE_LIST": " ".join(p.image_refs),
        "DEV_IMAGE": p.dev_image,
        "PROD_COMMAND": p.prod_command,
        # YAML 双引号标量（json.dumps 的转义规则与 YAML 兼容）
        "PROD_COMMAND_YAML": json.dumps(p.prod_command),
        "PROD_COMMAND_JSON": p.prod_command_json,
        # 用户包 + 预装组件（lucide / oracledb）的合并清单
        "PIP_PACKAGES_LINES": "\n".join(p.preinstall_pip_packages),
        "DEV_PIP_TOOLS": " ".join(p.dev_pip_tools),
    }


def _apt_block(packages):
    if not packages:
        return ""
    return (
        "RUN apt-get update \\\n"
        "    && apt-get install -y --no-install-recommends \\\n"
        f"        {' '.join(packages)} \\\n"
        "    && rm -rf /var/lib/apt/lists/*\n"
    )


def _custom_install_block(cmd):
    if not cmd:
        return ""
    return f"RUN {cmd}\n"


def _oracle_block(p):
    """Oracle Instant Client 19 安装块（勾选 enable_oracle_instantclient 时）。"""
    if not p.enable_oracle_instantclient:
        return ""
    return _load("Dockerfile.oracle.tmpl")


def _install_block(local_wheels, req_path="requirements.txt"):
    if local_wheels:
        return (
            "# wheels 同时保留在镜像内，离线环境可在容器内继续安装:\n"
            "#   pip install --no-index --find-links=/wheels <pkg>\n"
            "COPY wheels/ /wheels/\n"
            f"COPY {req_path} /app/requirements.txt\n"
            "\n"
            "RUN pip install --no-index --find-links=/wheels -r /app/requirements.txt\n"
        )
    return (
        "# 发布包不含 wheels/（已装进镜像），重建时从 pip 源在线安装\n"
        f"COPY {req_path} /app/requirements.txt\n"
        "\n"
        "RUN pip install -r /app/requirements.txt\n"
    )


def _dev_pip_block(p, local_wheels):
    tools = " ".join(p.dev_pip_tools)
    if local_wheels:
        return (
            "# dev 工具的 wheel 已随 wheels/ 一起下载，离线仍可安装\n"
            f"RUN pip install --no-index --find-links=/wheels {tools}\n"
        )
    return (
        "# 发布包不含 wheels/，重建时从 pip 源在线安装\n"
        f"RUN pip install {tools}\n"
    )


def render_dockerfile(p, local_wheels=True):
    # 发布包内的重建版 Dockerfile 由 compose 在项目根目录构建（context=项目根），
    # requirements.txt 位于 docs/devcontainer/，COPY 路径相应调整
    req_path = ("requirements.txt" if local_wheels
                else "docs/devcontainer/requirements.txt")
    base = {
        **_base_mapping(p),
        "APT_BLOCK": _apt_block(p.apt_package_list),
        "CUSTOM_INSTALL_BLOCK": _custom_install_block(p.custom_install_cmd),
        "INSTALL_BLOCK": _install_block(local_wheels, req_path),
        "DEV_PIP_BLOCK": _dev_pip_block(p, local_wheels),
        "ORACLE_BLOCK": _oracle_block(p),
    }
    if p.dev_image_only:
        # 仅 dev 镜像模式：单阶段 Dockerfile，产物只有一个 dev 镜像
        return _sub(_load("Dockerfile.devonly.tmpl"), base)

    dev_stage = ""
    if p.build_dev_image:
        dev_stage = "\n" + _sub(_load("Dockerfile.dev.tmpl"), base)
    return _sub(
        _load("Dockerfile.prod.tmpl"),
        {**base, "DEV_STAGE": dev_stage},
    )


def render_src_dockerfile(p, staging):
    """把 src 产物内的 Dockerfile 改写为不含 wheels/ 的联网重建版本。"""
    (Path(staging) / "Dockerfile").write_text(
        render_dockerfile(p, local_wheels=False), encoding="utf-8"
    )


def _app_command_block(p):
    """仅 dev 镜像模式下镜像 CMD 为 bash，app 服务需显式指定启动命令。"""
    if not p.dev_image_only:
        return ""
    return f"    command: {p.prod_command_json}\n"


def _app_options_block(p):
    """app 服务的端口发布与 env_file 注入。"""
    lines = []
    if p.has_app_port:
        if p.enable_nginx:
            # 已由 nginx 反代，app 只对容器网络暴露，避免与宿主机端口冲突
            lines.append("    expose:\n")
            lines.append(f"      - \"{p.app_port}\"\n")
        else:
            lines.append("    ports:\n")
            lines.append(f"      - \"{p.app_port}:{p.app_port}\"\n")
    if p.env_file_list:
        lines.append("    env_file:\n")
        # env 文件相对应用根目录（docker-compose.yml 由 install.sh 复制到项目根，
        # ${SRC_ROOT:-./} 默认即项目根）；绝对路径原样保留
        lines.extend(
            f"      - {json.dumps(_env_file_path(x))}\n" for x in p.env_file_list
        )
    return "".join(lines)


def _env_file_path(path):
    if path.startswith("/"):
        return path
    return "${SRC_ROOT:-./}/" + path


def _depends_on_block(p):
    """app 的启动依赖；postgres 等待健康检查通过，避免首次连接被拒。"""
    if not p.app_depends_on_nginx and not p.app_depends_on_postgres:
        return ""
    lines = ["    depends_on:\n"]
    if p.app_depends_on_nginx:
        lines.append("      nginx:\n        condition: service_started\n")
    if p.app_depends_on_postgres:
        lines.append("      postgres:\n        condition: service_healthy\n")
    return "".join(lines)


def _nginx_service(p):
    mount = ""
    if p.has_app_port:
        # docker-compose.yml 位于项目根目录（install.sh 复制），反代配置相对其
        # 所在的 docs/devcontainer 目录
        mount = ("    volumes:\n"
                 "      - ./docs/devcontainer/nginx/conf.d:/etc/nginx/conf.d:ro\n")
    return _sub(
        _load("compose.service.nginx.tmpl"),
        {**_base_mapping(p), "NGINX_CONF_MOUNT": mount},
    ).rstrip("\n")


def render_compose(p):
    dev_service = ""
    if p.dev_tools_enabled:
        dev_service = _sub(_DEV_SERVICE_TMPL, _base_mapping(p))

    services = []
    if p.enable_nginx:
        services.append(_nginx_service(p))
    if p.enable_postgres:
        services.append(_load("compose.service.postgres.tmpl").rstrip("\n"))
    service_blocks = "\n".join(services)
    if service_blocks:
        service_blocks += "\n"

    volumes_block = "volumes:\n  pgdata: {}\n" if p.enable_postgres else ""

    return _sub(
        _load("compose.base.tmpl"),
        {
            **_base_mapping(p),
            "APP_COMMAND_BLOCK": _app_command_block(p),
            "APP_OPTIONS_BLOCK": _app_options_block(p),
            "DEPENDS_ON_BLOCK": _depends_on_block(p),
            "DEV_SERVICE_BLOCK": dev_service,
            "SERVICE_BLOCKS": service_blocks,
            "VOLUMES_BLOCK": volumes_block,
        },
    )


def render_nginx_conf(p):
    """nginx 反代到 app:<app_port>；仅在启用 nginx 且指定 app_port 时生成。"""
    return _sub(_load("nginx.conf.tmpl"), {"APP_PORT": p.app_port})


def render_makefile(p):
    # dev 目标块内部也用占位符（{{DEV_IMAGE}}），需先替换再插入主模板
    dev_targets = ""
    if p.dev_tools_enabled:
        dev_targets = _sub(_DEV_MAKE_TARGETS, _base_mapping(p))
    return _sub(
        _load("Makefile.tmpl"),
        {
            **_base_mapping(p),
            "DEV_TARGETS": dev_targets,
            "PHONY_DEV": _DEV_PHONY if p.dev_tools_enabled else "",
        },
    )


def render_requirements(p):
    text = _sub(_load("requirements.txt.tmpl"), _base_mapping(p))
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def render_dockerignore(p):
    """项目根目录 .dockerignore（install.sh 安装/合并），防止 wheels/dist 进入构建上下文。"""
    return _sub(_load("dockerignore.tmpl"), _base_mapping(p))


def render_gitignore(p):
    """项目根目录 .gitignore（install.sh 安装/合并），忽略离线产物与本地补装缓存。"""
    return _sub(_load("gitignore.tmpl"), _base_mapping(p))


def render_main_py():
    """占位入口：install.sh 在应用根目录无 main.py 且启动命令为默认值时复制。"""
    return _load("main.py.tmpl")


def render_install_sh(p, out_file):
    """渲染安装脚本到 dist/（独立 artifact，不进 src tgz）。"""
    content = _sub(_load("install.sh.tmpl"), _base_mapping(p))
    path = Path(out_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


def render_readme_txt(p, out_file):
    """渲染 bundle 安装说明 readme.txt 到 dist/（随 install.sh 等一起进 Artifact zip）。"""
    content = _sub(_load("readme.txt.tmpl"), _base_mapping(p))
    path = Path(out_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def render_src_readme(p):
    services = []
    if p.enable_nginx:
        services.append("nginx:stable (宿主机 8080 → 容器 80)")
    if p.enable_postgres:
        services.append("postgres:16 (数据卷 pgdata)")
    services_summary = "、".join(services) if services else "无"

    if p.dev_image_only:
        image_summary = f"`{p.dev_image}`（仅 dev 镜像，部署与开发共用）"
    elif p.build_dev_image:
        image_summary = f"`{p.prod_image}` / `{p.dev_image}`"
    else:
        image_summary = f"`{p.prod_image}`"

    if p.dev_image_only:
        dev_note = (
            f"- 本次仅构建 dev 镜像 `{p.dev_image}`，部署（`make up`）与开发"
            "（`make shell / lint / compile / test`）共用该镜像。"
        )
    elif p.build_dev_image:
        dev_note = (
            f"- dev 镜像 `{p.dev_image}` 已包含 ruff/pytest 等工具，"
            "`make shell / lint / compile / test` 可直接使用。"
        )
    else:
        dev_note = "- 本次未构建 dev 镜像，`make shell / lint / compile / test` 目标不可用。"

    return _sub(
        _load("README.src.tmpl"),
        {
            **_base_mapping(p),
            "IMAGE_SUMMARY": image_summary,
            "SERVICES_SUMMARY": services_summary,
            "DEV_TOOLS_NOTE": dev_note,
        },
    )


def render_all(p, staging):
    """渲染全部文件到 staging 目录，返回 {文件名: 内容}。"""
    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "wheels").mkdir(exist_ok=True)

    files = {
        "Dockerfile": render_dockerfile(p),
        # .tpl 后缀：不会被 docker compose 自动发现/被 -f 误用，
        # 由 install.sh 原样复制到项目根目录为 docker-compose.yml
        # （模板内 ${SRC_ROOT:-./} / ${SRC_ROOT_NAME:-app} 由 compose 运行时解析）
        "docker-compose.yml.tpl": render_compose(p),
        "Makefile": render_makefile(p),
        "requirements.txt": render_requirements(p),
        "main.py": render_main_py(),
        "README.md": render_src_readme(p),
        # 离线补装：wheel 打进现有镜像生成 addon 镜像
        "Dockerfile.addon": render_dockerfile_addon(p),
        "build.sh": render_build_sh(p),
        # 随 install.sh 安装/合并到项目根目录（src root）
        ".dockerignore": render_dockerignore(p),
        ".gitignore": render_gitignore(p),
    }
    for name, content in files.items():
        (staging / name).write_text(content, encoding="utf-8")
    # 保留可执行位（tar 会随包保留；artifact zip 解压可能丢失，文档引导 bash 调用）
    (staging / "build.sh").chmod(0o755)
    if p.enable_nginx and p.has_app_port:
        conf_dir = staging / "nginx" / "conf.d"
        conf_dir.mkdir(parents=True, exist_ok=True)
        (conf_dir / "default.conf").write_text(
            render_nginx_conf(p), encoding="utf-8"
        )
    return files
