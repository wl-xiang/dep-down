"""输入参数解析、规范化与校验。

环境变量与 .github/workflows/build-devcontainer.yml 的 inputs 一一对应
（大写 + 下划线）。优先级：环境变量 > 默认值。
"""

import os
import re
from dataclasses import dataclass

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

# 名称（镜像名与产物名前缀）：仅允许小写字母/数字/./_/-，且以字母或数字开头
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# docker tag 规则：^[a-zA-Z0-9_][a-zA-Z0-9._-]{0,127}$
TAG_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9._-]{0,127}$")

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
    build_dev_image: bool
    name: str
    tag: str
    app_source_dir: str

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
    def dev_pip_tools(self):
        return list(DEV_PIP_TOOLS) if self.build_dev_image else []

    @property
    def prod_image(self):
        return f"{self.name}-prod:{self.tag}"

    @property
    def dev_image(self):
        return f"{self.name}-dev:{self.tag}"

    @property
    def src_artifact_name(self):
        return f"{self.name}-src_{self.tag}"

    @property
    def bundle_artifact_name(self):
        return f"{self.name}-bundle_{self.tag}"


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
        build_dev_image=_env_bool("BUILD_DEV_IMAGE", True),
        name=_env("NAME", "devcontainer"),
        tag=_env("TAG", "latest"),
        app_source_dir=_env("APP_SOURCE_DIR", "."),
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
    if p.app_depends_on_nginx and not p.enable_nginx:
        raise ParamError("app_depends_on_nginx=true 需要同时设置 enable_nginx=true")
    if p.app_depends_on_postgres and not p.enable_postgres:
        raise ParamError(
            "app_depends_on_postgres=true 需要同时设置 enable_postgres=true"
        )
    if not NAME_RE.match(p.name):
        raise ParamError(
            f"name 非法（仅允许小写字母/数字/./_/-，且以字母或数字开头）: {p.name!r}"
        )
    if not TAG_RE.match(p.tag):
        raise ParamError(
            f"tag 非法（仅允许字母/数字/./_/-，且以字母或数字开头）: {p.tag!r}"
        )
    if not p.app_source_dir.strip():
        raise ParamError("app_source_dir 不能为空")

    for pkg in p.pip_package_list:
        if any(ch.isspace() for ch in pkg):
            raise ParamError(f"pip 包名含空白字符（多个包请用 $ 分隔）: {pkg!r}")

    # 规范化挂载路径：去掉多余的尾部斜杠
    if len(p.app_source_dir) > 1 and p.app_source_dir != "/":
        p.app_source_dir = p.app_source_dir.rstrip("/") or "."
    return p
