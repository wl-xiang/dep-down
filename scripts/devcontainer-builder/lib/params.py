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

PYTHON_VERSIONS = ("3.10", "3.11", "3.12", "3.13")

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

# 预装 lucide（SVG 图标库，Django/Jinja 模板渲染 lucide.dev 图标）的 pip 包名
LUCIDE_PIP_PACKAGE = "lucide"

# 预装 Oracle Instant Client 19 时随装的 python-oracledb 版本。
# 锁定 2.5.1：与 Instant Client 19 + Oracle 11.2 Thick 模式的组合经过生产
# 环境验证（参考 https://github.com/wl-xiang/oracle2excel 的 Dockerfile）。
ORACLEDB_PIP_PACKAGE = "oracledb==2.5.1"

# Oracle Instant Client 19 的安装模式：
#   none              = 不安装
#   runtime_deps_only = 只安装运行时依赖并配置环境变量，客户端由 compose 从宿主机挂载
#   full              = 完整安装（构建期下载官方 Basic 包解压进镜像 + 运行时依赖）
ORACLE_MODES = ("none", "runtime_deps_only", "full")

# Oracle Instant Client 的容器内固定挂载点与环境变量地址。
# runtime_deps_only 模式下客户端本体不打进镜像（减小镜像体积），由 compose
# 从宿主机只读挂载；full 模式把客户端解压到同一路径，保持环境变量一致。
ORACLE_CLIENT_DIR = "/opt/oracle/instantclient19"

# npm download Action 产物（packages/）在容器内的只读挂载点
NPM_PACKAGES_CONTAINER_DIR = "/opt/npm-packages"

# 预设环境变量的分隔符（workflow 输入框无法换行）
ENV_PRESET_SEPARATOR = "》"

NODE_VERSIONS = ("24",)

# 与 .github/workflows/npm_download.yml 的 registry 选项保持一致
NPM_REGISTRIES = {
    "npmmirror (taobao)": "https://registry.npmmirror.com",
    "Tencent": "https://mirrors.cloud.tencent.com/npm/",
    "Huawei": "https://repo.huaweicloud.com/repository/npm/",
    "THU (tuna)": "https://mirrors.tuna.tsinghua.edu.cn/npm/",
    "USTC": "https://mirrors.ustc.edu.cn/npm/",
    "Official (npmjs.org)": "https://registry.npmjs.org",
}

NPM_OTHER_REGISTRY = "Other (custom URL)"

# 自定义 npm 源会拼进 Dockerfile 的 RUN 命令，限制为安全的 URL 字符
NPM_REGISTRY_URL_RE = re.compile(r"^https?://[A-Za-z0-9._~:/\[\]@%+=,-]+$")

# npm 离线包目录会拼进 compose / Makefile / install.sh，限制为安全路径字符
NPM_PACKAGES_DIR_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# npm 包名（可带 @scope/ 前缀与 @version 后缀）；刻意排除空格与 shell 元字符，
# 因为包名会直接拼进 Dockerfile 的 RUN 命令
NPM_PACKAGE_RE = re.compile(
    r"^(@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*(@[a-z0-9][a-z0-9._-]*)?$",
    re.IGNORECASE,
)

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
    enable_lucide: bool
    oracle_instantclient_mode: str
    app_depends_on_nginx: bool
    app_depends_on_postgres: bool
    prod_command: str
    build_dev_image: bool
    dev_image_only: bool
    image_prefix: str
    app_source_dir: str
    app_port: str
    env_file: str
    preset_envs: str
    enable_node: bool
    node_version: str
    npm_packages: str
    npm_registry: str
    npm_custom_registry_url: str
    npm_packages_dir: str
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
    def preinstall_pip_packages(self):
        """用户 pip 包 + 预装组件（lucide / oracledb）的合并清单。

        用于 requirements.txt 渲染与 pip download；用户已显式写出同名包时
        不重复追加（版本以其声明为准）。
        """
        pkgs = list(self.pip_package_list)
        existing = {x.lower().split("=")[0].split("<")[0].split(">")[0].split("!")[0].strip()
                    for x in pkgs}
        if self.enable_lucide and "lucide" not in existing:
            pkgs.append(LUCIDE_PIP_PACKAGE)
        if (self.oracle_enabled
                and "oracledb" not in existing):
            pkgs.append(ORACLEDB_PIP_PACKAGE)
        return pkgs

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
    def oracle_enabled(self):
        return self.oracle_instantclient_mode != "none"

    @property
    def oracle_full(self):
        """full 模式：客户端随镜像分发，不需要宿主机挂载。"""
        return self.oracle_instantclient_mode == "full"

    @property
    def app_port_parts(self):
        """(宿主机端口, 容器端口)；app_port 支持 3000 或 3000:3000 两种写法。"""
        if not self.app_port:
            return None
        if ":" in self.app_port:
            host, container = self.app_port.split(":", 1)
        else:
            host = container = self.app_port
        return host, container

    @property
    def has_app_port(self):
        return bool(self.app_port)

    @property
    def app_container_port(self):
        """应用在容器内监听的端口（nginx 反代/expose 使用）。"""
        parts = self.app_port_parts
        return parts[1] if parts else ""

    @property
    def env_file_list(self):
        """env_file 支持逗号或空格分隔。"""
        return [x for x in self.env_file.replace(",", " ").split() if x]

    @property
    def preset_env_pairs(self):
        """预设环境变量：KEY=VALUE，多个用 》 分隔。"""
        pairs = []
        for item in self.preset_envs.split(ENV_PRESET_SEPARATOR):
            item = item.strip()
            if not item:
                continue
            key, _, value = item.partition("=")
            pairs.append((key.strip(), value.strip()))
        return pairs

    @property
    def npm_package_list(self):
        return [x.strip() for x in self.npm_packages.split("$") if x.strip()]

    @property
    def npm_registry_url(self):
        if self.npm_registry == NPM_OTHER_REGISTRY:
            return self.npm_custom_registry_url
        return NPM_REGISTRIES[self.npm_registry]

    @property
    def oracle_client_dir(self):
        """Oracle 客户端在容器内的固定路径（也是 ORACLE_HOME/LD_LIBRARY_PATH）。"""
        return ORACLE_CLIENT_DIR

    @property
    def npm_packages_mount(self):
        """npm 离线包目录：空字符串表示不挂载。"""
        if not self.enable_node or not self.npm_packages_dir:
            return ""
        return f"{self.npm_packages_mount_source}:{NPM_PACKAGES_CONTAINER_DIR}:ro"

    @property
    def npm_packages_mount_source(self):
        """宿主机目录（相对项目根或绝对路径），compose 中可用 NPM_PACKAGES_DIR 覆盖。"""
        path = self.npm_packages_dir.removeprefix("./")
        if self.npm_packages_dir.startswith("/"):
            return "${NPM_PACKAGES_DIR:-" + self.npm_packages_dir + "}"
        return "${NPM_PACKAGES_DIR:-./" + path + "}"

    @property
    def oracle_client_mount(self):
        """Oracle 客户端只读挂载：仅 runtime_deps_only 模式需要。"""
        if self.oracle_instantclient_mode != "runtime_deps_only":
            return ""
        return f"{self.oracle_client_mount_source}:{ORACLE_CLIENT_DIR}:ro"

    @property
    def oracle_client_mount_source(self):
        return "${ORACLE_CLIENT_DIR:-" + ORACLE_CLIENT_DIR + "}"

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
        pip_mirror=_env("PIP_MIRROR", "pypi.org"),
        pip_packages=_env("PIP_PACKAGES", ""),
        apt_packages=_env("APT_PACKAGES", ""),
        custom_install_cmd=_env("CUSTOM_INSTALL_CMD", ""),
        enable_nginx=_env_bool("ENABLE_NGINX", False),
        enable_postgres=_env_bool("ENABLE_POSTGRES", False),
        enable_lucide=_env_bool("ENABLE_LUCIDE", False),
        oracle_instantclient_mode=_env(
            "ENABLE_ORACLE_INSTANTCLIENT", "none"
        ).lower(),
        app_depends_on_nginx=_env_bool("APP_DEPENDS_ON_NGINX", False),
        app_depends_on_postgres=_env_bool("APP_DEPENDS_ON_POSTGRES", False),
        prod_command=_env("PROD_COMMAND", "python main.py"),
        build_dev_image=_env_bool("BUILD_DEV_IMAGE", True),
        dev_image_only=_env_bool("DEV_IMAGE_ONLY", False),
        image_prefix=_env("IMAGE_PREFIX", "mydevc1"),
        app_source_dir=_env("APP_SOURCE_DIR", "."),
        # app_port 显式置空 = 不映射端口（workflow 总会设置该变量）
        app_port=(os.environ["APP_PORT"].strip()
                  if "APP_PORT" in os.environ else "3000:3000"),
        env_file=_env("ENV_FILE", ""),
        preset_envs=_env("PRESET_ENVS", ""),
        enable_node=_env_bool("ENABLE_NODE", False),
        node_version=_env("NODE_VERSION", "24"),
        npm_packages=_env("NPM_PACKAGES", ""),
        npm_registry=_env("NPM_REGISTRY", "Official (npmjs.org)"),
        npm_custom_registry_url=_env("NPM_CUSTOM_REGISTRY_URL", ""),
        npm_packages_dir=_env("NPM_PACKAGES_DIR", "packages"),
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
    if p.oracle_instantclient_mode not in ORACLE_MODES:
        raise ParamError(
            f"不支持的 enable_oracle_instantclient: {p.oracle_instantclient_mode!r}，"
            f"可选: {', '.join(ORACLE_MODES)}"
        )
    if p.app_depends_on_nginx and not p.enable_nginx:
        raise ParamError("app_depends_on_nginx=true 需要同时设置 enable_nginx=true")
    if p.app_depends_on_postgres and not p.enable_postgres:
        raise ParamError(
            "app_depends_on_postgres=true 需要同时设置 enable_postgres=true"
        )
    if p.npm_registry not in NPM_REGISTRIES and p.npm_registry != NPM_OTHER_REGISTRY:
        raise ParamError(
            f"不支持的 npm_registry: {p.npm_registry!r}，可选: "
            f"{', '.join(NPM_REGISTRIES)}, {NPM_OTHER_REGISTRY}"
        )
    if p.node_version not in NODE_VERSIONS:
        raise ParamError(
            f"不支持的 node_version: {p.node_version!r}，可选: {', '.join(NODE_VERSIONS)}"
        )
    if p.npm_registry == NPM_OTHER_REGISTRY and not p.npm_custom_registry_url:
        raise ParamError(
            "npm_registry 为 'Other (custom URL)' 时必须填写 npm_custom_registry_url"
        )
    if p.npm_registry == NPM_OTHER_REGISTRY and not NPM_REGISTRY_URL_RE.match(
        p.npm_custom_registry_url
    ):
        raise ParamError(
            "npm_custom_registry_url 非法（需 http(s):// 开头，且不含空白/引号/$ 等字符）: "
            f"{p.npm_custom_registry_url!r}"
        )
    if p.npm_packages and not p.enable_node:
        raise ParamError("npm_packages 需要同时设置 enable_node=true")
    for pkg in p.npm_package_list:
        if not NPM_PACKAGE_RE.match(pkg):
            raise ParamError(
                f"npm 包名非法（仅允许 name / @scope/name，可带 @版本；"
                f"多个包请用 $ 分隔）: {pkg!r}"
            )
    if not NPM_PACKAGES_DIR_RE.match(p.npm_packages_dir):
        raise ParamError(
            f"npm_packages_dir 非法（仅允许字母/数字/./_/-，相对项目根或绝对路径，"
            f"不支持 ~ 展开）: {p.npm_packages_dir!r}"
        )

    # 预设环境变量：KEY=VALUE，多个用 》 分隔；校验名称并拒绝重复键
    seen_env = set()
    for item in p.preset_envs.split(ENV_PRESET_SEPARATOR):
        item = item.strip()
        if not item:
            continue
        key, sep, _value = item.partition("=")
        key = key.strip()
        if not sep:
            raise ParamError(
                f"预设环境变量必须为 KEY=VALUE 形式: {item!r}"
                "（多个变量用 》 分隔）"
            )
        if not ENV_NAME_RE.match(key):
            raise ParamError(f"预设环境变量名非法: {key!r}")
        if key in seen_env:
            raise ParamError(f"预设环境变量重复: {key!r}")
        seen_env.add(key)

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
        parts = p.app_port.split(":")
        if len(parts) > 2 or not all(
            x.isdigit() and 1 <= int(x) <= 65535 for x in parts
        ):
            raise ParamError(
                "app_port 必须是 1-65535 的端口号，或 host:container 端口映射"
                f"（如 3000:3000）: {p.app_port!r}"
            )
        if len(parts) == 1:
            p.app_port = f"{int(parts[0])}:{int(parts[0])}"
        else:
            p.app_port = f"{int(parts[0])}:{int(parts[1])}"
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
