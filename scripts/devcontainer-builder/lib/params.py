"""输入参数解析、规范化与校验。

环境变量与 .github/workflows/build-devcontainer.yml 的 inputs 一一对应
（大写 + 下划线）。优先级：环境变量 > 默认值。
"""

import json
import os
import re
import shlex
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# workflow platform 选项 → Docker --platform
PLATFORM_MAP = {
    "linux-amd64": "linux/amd64",
    "linux-arm64": "linux/arm64",
}

# workflow platform 选项 → (docker arch, pip arch)
ARCH_MAP = {
    "linux-amd64": ("amd64", "x86_64"),
    "linux-arm64": ("arm64", "aarch64"),
}

PYTHON_VERSIONS = ("3.12", "3.13")

# glibc → manylinux 标签（pip 实际使用 manylinux_<glibc>_<arch> 形式，
# 其中 manylinux2014 与 manylinux_2_17 等价）
GLIBC_MANYLINUX = {
    "2.17": "manylinux2014",
    "2.28": "manylinux_2_28",
    "2.34": "manylinux_2_34",
}

PIP_MIRRORS = {
    "pypi.org": "https://pypi.org/simple",
    "aliyun": "https://mirrors.aliyun.com/pypi/simple",
    "thu": "https://pypi.tuna.tsinghua.edu.cn/simple",
}

# dev 镜像额外安装的工具（wheel 会随 wheels/ 一起下载）
DEV_PIP_TOOLS = ("ruff", "pytest", "pytest-cov")

# 产物/镜像时间戳统一使用东八区（UTC+8）
TZ_CN = timezone(timedelta(hours=8), name="UTC+8")

# image_tag 选项：latest（默认）或本次构建时间戳
IMAGE_TAG_CHOICES = ("latest", "timestamp")

IMAGE_PREFIX_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

BOOL_TRUE = {"1", "true", "yes", "on"}


class ParamError(ValueError):
    """参数校验失败。"""


def _env(name, default=""):
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in BOOL_TRUE


@dataclass
class Params:
    platform: str
    python_version: str
    glibc_version: str
    pip_mirror: str
    pip_packages: str
    apt_packages: str
    custom_install_cmd: str
    enable_nginx: bool
    enable_postgres: bool
    app_depends_on_nginx: bool
    app_depends_on_postgres: bool
    prod_command: str
    build_dev_image: bool
    dev_image_only: bool
    image_prefix: str
    app_source_dir: str
    app_port: str
    env_file: str
    selinux_relabel: bool
    image_tag: str
    ts: str

    # ---------- 派生值 ----------

    @property
    def docker_platform(self):
        return PLATFORM_MAP[self.platform]

    @property
    def arch(self):
        return ARCH_MAP[self.platform][0]

    @property
    def pip_arch(self):
        return ARCH_MAP[self.platform][1]

    @property
    def pip_platform_tag(self):
        glibc = self.glibc_version.replace(".", "_")
        return f"manylinux_{glibc}_{self.pip_arch}"

    @property
    def manylinux_label(self):
        return GLIBC_MANYLINUX[self.glibc_version]

    @property
    def mirror_url(self):
        return PIP_MIRRORS[self.pip_mirror]

    @property
    def pip_package_list(self):
        return [x.strip() for x in self.pip_packages.split("$") if x.strip()]

    @property
    def apt_package_list(self):
        return self.apt_packages.split()

    @property
    def dev_tools_enabled(self):
        """是否需要 dev 阶段（仅 dev 镜像模式下唯一镜像即 dev 镜像）。"""
        return self.dev_image_only or self.build_dev_image

    @property
    def dev_pip_tools(self):
        return list(DEV_PIP_TOOLS) if self.dev_tools_enabled else []

    @property
    def tag(self):
        """镜像 TAG 后缀：latest（默认）或本次构建时间戳（UTC+8）。"""
        return self.ts if self.image_tag == "timestamp" else "latest"

    @property
    def prod_image(self):
        """prod 镜像：<前缀>:prod-<TAG 后缀>。"""
        return f"{self.image_prefix}:prod-{self.tag}"

    @property
    def dev_image(self):
        """dev 镜像：<前缀>:dev-<TAG 后缀>。"""
        return f"{self.image_prefix}:dev-{self.tag}"

    @property
    def app_image(self):
        """部署（app 服务）使用的镜像：仅 dev 镜像模式下直接用 dev 镜像。"""
        return self.dev_image if self.dev_image_only else self.prod_image

    @property
    def app_build_target(self):
        return "dev" if self.dev_image_only else "prod"

    @property
    def image_refs(self):
        """本次导入/自检需要的镜像清单（与 docker.image_list 保持一致）。"""
        if self.dev_image_only:
            images = [self.dev_image]
        else:
            images = [self.prod_image]
            if self.build_dev_image:
                images.append(self.dev_image)
        if self.enable_nginx:
            images.append("nginx:stable")
        if self.enable_postgres:
            images.append("postgres:16")
        return images

    @property
    def has_app_port(self):
        return bool(self.app_port)

    @property
    def env_file_list(self):
        """env_file 支持逗号或空格分隔。"""
        return [x for x in self.env_file.replace(",", " ").split() if x]

    @property
    def mount_path(self):
        """容器 /app 的挂载源。${SRC_ROOT:-./} 由 docker compose 在运行时解析
        （默认 ./ = docker-compose.yml 所在的项目根目录）；app_source_dir 为
        根目录下的相对子目录（或绝对路径）。
        SELinux Enforcing 主机可追加 :z 重打标签。"""
        if self.app_source_dir == ".":
            src = "${SRC_ROOT:-./}"
        elif self.app_source_dir.startswith("/"):
            src = self.app_source_dir.rstrip("/") or "/"
        else:
            src = "${SRC_ROOT:-./}/" + self.app_source_dir.strip("/")
        return f"{src}:/app{':z' if self.selinux_relabel else ''}"

    @property
    def prod_command_args(self):
        return shlex.split(self.prod_command)

    @property
    def prod_command_json(self):
        return json.dumps(self.prod_command_args)


def load():
    """从环境变量读取参数并校验；失败抛出 ParamError。"""
    params = Params(
        platform=_env("PLATFORM", "linux-arm64"),
        python_version=_env("PYTHON_VERSION", "3.13"),
        glibc_version=_env("GLIBC_VERSION", "2.28"),
        pip_mirror=_env("PIP_MIRROR", "thu"),
        pip_packages=_env("PIP_PACKAGES", ""),
        apt_packages=_env("APT_PACKAGES", ""),
        custom_install_cmd=_env("CUSTOM_INSTALL_CMD", ""),
        enable_nginx=_env_bool("ENABLE_NGINX", False),
        enable_postgres=_env_bool("ENABLE_POSTGRES", False),
        app_depends_on_nginx=_env_bool("APP_DEPENDS_ON_NGINX", False),
        app_depends_on_postgres=_env_bool("APP_DEPENDS_ON_POSTGRES", False),
        prod_command=_env("PROD_COMMAND", "python main.py"),
        build_dev_image=_env_bool("BUILD_DEV_IMAGE", True),
        dev_image_only=_env_bool("DEV_IMAGE_ONLY", False),
        image_prefix=_env("IMAGE_PREFIX", "devcontainer"),
        app_source_dir=_env("APP_SOURCE_DIR", "."),
        app_port=_env("APP_PORT", ""),
        env_file=_env("ENV_FILE", ""),
        selinux_relabel=_env_bool("SELINUX_RELABEL", False),
        image_tag=_env("IMAGE_TAG", "latest"),
        ts=datetime.now(TZ_CN).strftime("%Y%m%d-%H%M%S"),
    )
    return validate(params)


def validate(p):
    if p.platform not in PLATFORM_MAP:
        raise ParamError(
            f"不支持的 platform: {p.platform!r}，可选: {', '.join(PLATFORM_MAP)}"
        )
    if p.python_version not in PYTHON_VERSIONS:
        raise ParamError(
            f"不支持的 python_version: {p.python_version!r}，"
            f"可选: {', '.join(PYTHON_VERSIONS)}"
        )
    if p.glibc_version not in GLIBC_MANYLINUX:
        raise ParamError(
            f"不支持的 glibc_version: {p.glibc_version!r}，"
            f"可选: {', '.join(GLIBC_MANYLINUX)}"
        )
    if p.pip_mirror not in PIP_MIRRORS:
        raise ParamError(
            f"不支持的 pip_mirror: {p.pip_mirror!r}，可选: {', '.join(PIP_MIRRORS)}"
        )
    if p.image_tag not in IMAGE_TAG_CHOICES:
        raise ParamError(
            f"不支持的 image_tag: {p.image_tag!r}，可选: {', '.join(IMAGE_TAG_CHOICES)}"
        )
    if p.app_depends_on_nginx and not p.enable_nginx:
        raise ParamError("app_depends_on_nginx=true 需要同时设置 enable_nginx=true")
    if p.app_depends_on_postgres and not p.enable_postgres:
        raise ParamError(
            "app_depends_on_postgres=true 需要同时设置 enable_postgres=true"
        )
    if not IMAGE_PREFIX_RE.match(p.image_prefix):
        raise ParamError(
            f"image_prefix 非法（仅允许小写字母/数字/./_/-，且以字母或数字开头）: "
            f"{p.image_prefix!r}"
        )
    if not p.prod_command_args:
        raise ParamError(f"prod_command 无法解析为命令: {p.prod_command!r}")
    if not p.app_source_dir.strip():
        raise ParamError("app_source_dir 不能为空")
    if p.app_source_dir.startswith("~"):
        raise ParamError(
            "app_source_dir 不支持 ~ 展开，请写绝对路径或在应用根目录使用 '.'"
        )
    if p.app_port:
        if not p.app_port.isdigit() or not 1 <= int(p.app_port) <= 65535:
            raise ParamError(f"app_port 必须是 1-65535 的整数: {p.app_port!r}")
        p.app_port = str(int(p.app_port))
    for path in p.env_file_list:
        if path.startswith("~"):
            raise ParamError(f"env_file 不支持 ~ 展开: {path!r}")

    for pkg in p.pip_package_list:
        if any(ch.isspace() for ch in pkg):
            raise ParamError(f"pip 包名含空白字符（多个包请用 $ 分隔）: {pkg!r}")

    # 规范化挂载路径：去掉多余的尾部斜杠
    if len(p.app_source_dir) > 1 and p.app_source_dir != "/":
        p.app_source_dir = p.app_source_dir.rstrip("/") or "."
    return p
