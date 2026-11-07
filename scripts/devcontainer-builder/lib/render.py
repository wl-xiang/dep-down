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
_DEV_SERVICE_TMPL = """\
  dev:
    image: {{IMAGE_PREFIX}}-dev:{{TAG}}
    build:
      context: .
      dockerfile: Dockerfile
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

# Makefile 中依赖 dev 镜像的目标（build_dev_image=true 时生成）
_DEV_MAKE_TARGETS = """\
check-dev: ## 检查 dev 镜像是否已导入（离线环境不会自行构建）
\t@docker image inspect {{DEV_IMAGE}} >/dev/null 2>&1 || { \\
\t\techo "dev 镜像 {{DEV_IMAGE}} 未导入：请先 docker load 对应 bundle（或本次未构建 dev 镜像）"; \\
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


def _load(name):
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _sub(text, mapping):
    for key, value in mapping.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _base_mapping(p):
    return {
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
        "APP_SOURCE_DIR": p.app_source_dir,
        "APP_VOLUME": json.dumps(p.mount_path),
        "IMAGE_LIST": " ".join(p.image_refs),
        "DEV_IMAGE": p.dev_image,
        "PROD_COMMAND": p.prod_command,
        # YAML 双引号标量（json.dumps 的转义规则与 YAML 兼容）
        "PROD_COMMAND_YAML": json.dumps(p.prod_command),
        "PROD_COMMAND_JSON": p.prod_command_json,
        "PIP_PACKAGES_LINES": "\n".join(p.pip_package_list),
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


def _install_block(local_wheels):
    if local_wheels:
        return (
            "# wheels 同时保留在镜像内，离线环境可在容器内继续安装:\n"
            "#   pip install --no-index --find-links=/wheels <pkg>\n"
            "COPY wheels/ /wheels/\n"
            "COPY requirements.txt /app/requirements.txt\n"
            "\n"
            "RUN pip install --no-index --find-links=/wheels -r /app/requirements.txt\n"
        )
    return (
        "# 发布包不含 wheels/（已装进镜像），重建时从 pip 源在线安装\n"
        "COPY requirements.txt /app/requirements.txt\n"
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
    dev_stage = ""
    if p.build_dev_image:
        dev_stage = "\n" + _sub(
            _load("Dockerfile.dev.tmpl"),
            {**_base_mapping(p), "DEV_PIP_BLOCK": _dev_pip_block(p, local_wheels)},
        )
    return _sub(
        _load("Dockerfile.prod.tmpl"),
        {
            **_base_mapping(p),
            "APT_BLOCK": _apt_block(p.apt_package_list),
            "CUSTOM_INSTALL_BLOCK": _custom_install_block(p.custom_install_cmd),
            "INSTALL_BLOCK": _install_block(local_wheels),
            "DEV_STAGE": dev_stage,
        },
    )


def render_src_dockerfile(p, staging):
    """把 src 产物内的 Dockerfile 改写为不含 wheels/ 的联网重建版本。"""
    (Path(staging) / "Dockerfile").write_text(
        render_dockerfile(p, local_wheels=False), encoding="utf-8"
    )


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
        lines.extend(f"      - {json.dumps(x)}\n" for x in p.env_file_list)
    return "".join(lines)


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
        mount = "    volumes:\n      - ./nginx/conf.d:/etc/nginx/conf.d:ro\n"
    return _sub(
        _load("compose.service.nginx.tmpl"),
        {**_base_mapping(p), "NGINX_CONF_MOUNT": mount},
    ).rstrip("\n")


def render_compose(p):
    dev_service = ""
    if p.build_dev_image:
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
    if p.build_dev_image:
        dev_targets = _sub(_DEV_MAKE_TARGETS, _base_mapping(p))
    return _sub(
        _load("Makefile.tmpl"),
        {
            **_base_mapping(p),
            "DEV_TARGETS": dev_targets,
            "PHONY_DEV": _DEV_PHONY if p.build_dev_image else "",
        },
    )


def render_requirements(p):
    text = _sub(_load("requirements.txt.tmpl"), _base_mapping(p))
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def render_src_readme(p):
    services = []
    if p.enable_nginx:
        services.append("nginx:stable (宿主机 8080 → 容器 80)")
    if p.enable_postgres:
        services.append("postgres:16 (数据卷 pgdata)")
    services_summary = "、".join(services) if services else "无"

    if p.build_dev_image:
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
        "docker-compose.yaml": render_compose(p),
        "Makefile": render_makefile(p),
        "requirements.txt": render_requirements(p),
        "README.md": render_src_readme(p),
    }
    for name, content in files.items():
        (staging / name).write_text(content, encoding="utf-8")
    if p.enable_nginx and p.has_app_port:
        conf_dir = staging / "nginx" / "conf.d"
        conf_dir.mkdir(parents=True, exist_ok=True)
        (conf_dir / "default.conf").write_text(
            render_nginx_conf(p), encoding="utf-8"
        )
    return files
