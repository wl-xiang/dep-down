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
    volumes:
      - {{APP_VOLUME}}
    networks:
      - app-net
    profiles:
      - dev
"""

# Makefile 中依赖 dev 镜像的目标（build_dev_image=true 时生成）
_DEV_MAKE_TARGETS = """\
shell: ## 进入 dev 容器交互式 bash
\t$(DEV_RUN)

dev: ## 等价于 shell
\t$(DEV_RUN)

lint: ## ruff 静态检查
\t$(DEV_RUN) ruff check .

compile: ## 字节码编译校验
\t$(DEV_RUN) python -m compileall -q .

test: ## 运行 pytest
\t$(DEV_RUN) pytest -q

"""

_DEV_PHONY = "shell dev lint compile test "


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
        "APP_VOLUME": json.dumps(f"{p.app_source_dir}:/app"),
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


def render_compose(p):
    depends = []
    if p.app_depends_on_nginx:
        depends.append("nginx")
    if p.app_depends_on_postgres:
        depends.append("postgres")
    depends_block = ""
    if depends:
        depends_block = "    depends_on:\n" + "".join(
            f"      - {d}\n" for d in depends
        )

    dev_service = ""
    if p.build_dev_image:
        dev_service = _sub(_DEV_SERVICE_TMPL, _base_mapping(p))

    services = []
    if p.enable_nginx:
        services.append(_load("compose.service.nginx.tmpl").rstrip("\n"))
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
            "DEPENDS_ON_BLOCK": depends_block,
            "DEV_SERVICE_BLOCK": dev_service,
            "SERVICE_BLOCKS": service_blocks,
            "VOLUMES_BLOCK": volumes_block,
        },
    )


def render_makefile(p):
    return _sub(
        _load("Makefile.tmpl"),
        {
            **_base_mapping(p),
            "DEV_TARGETS": _DEV_MAKE_TARGETS if p.build_dev_image else "",
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
    return files
