# devcontainer-builder

离线 Python 开发环境镜像构建工具：解析参数 → 渲染模板 → pip download →
docker 构建 → 打包 → Summary。由 `.github/workflows/build-devcontainer.yml`
调用，也可本地运行。内网使用手册见 `docs/offline-devcontainer.md`。

## 目录结构

```
scripts/devcontainer-builder/
├── main.py                  # 总入口：编排以下各模块
├── lib/
│   ├── params.py            # 输入解析、规范化、校验、glibc→manylinux 映射
│   ├── render.py            # 模板渲染与子模板拼接（compose 服务/dev 阶段等）
│   ├── pip.py               # pip download → wheels/（多平台标签展开）
│   ├── docker.py            # buildx 构建、外挂镜像 pull、docker save 直出 gzip
│   ├── package.py           # src tgz 打包
│   └── summary.py           # GITHUB_STEP_SUMMARY / GITHUB_OUTPUT
└── templates/
    ├── Dockerfile.prod.tmpl       # prod 阶段（基础镜像 + APT/自定义命令 + 离线 pip install）
    ├── Dockerfile.dev.tmpl        # dev 阶段（FROM prod + 开发工具）
    ├── Dockerfile.devonly.tmpl    # 仅 dev 镜像模式的单阶段 Dockerfile
    ├── compose.base.tmpl          # compose 模板骨架（app 服务 + 占位块；输出为 .tpl）
    ├── compose.service.nginx.tmpl # nginx 服务子模板
    ├── compose.service.postgres.tmpl # postgres 服务子模板（含健康检查）
    ├── nginx.conf.tmpl            # nginx 反代配置（启用 nginx 且指定 app_port 时）
    ├── Makefile.tmpl              # make 目标（check/up/shell/lint/compile/test 等）
    ├── requirements.txt.tmpl      # pip 包清单
    ├── main.py.tmpl               # 占位入口（install.sh 在应用根目录无 main.py 时复制）
    ├── install.sh.tmpl            # 安装脚本（与 src tgz 同打成一个 src artifact，不进 tgz）
    ├── Dockerfile.addon.tmpl      # 离线补装：基于现有镜像生成 addon 阶段（wheels 进 /tmp 同层删）
    ├── build.sh.tmpl              # 离线补装入口（docker build Dockerfile.addon，默认 addon-<TAG>）
    └── README.src.tmpl            # src 产物内的快速上手说明
```

## 环境变量（与 workflow inputs 一一对应）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PLATFORM` | `linux-arm64` | `linux-amd64` / `linux-arm64` |
| `PYTHON_VERSION` | `3.13` | `3.12` / `3.13` |
| `GLIBC_VERSION` | `2.28` | `2.17` / `2.28` / `2.34`，控制 manylinux 标签 |
| `PIP_MIRROR` | `thu` | `pypi.org` / `aliyun` / `thu` |
| `PIP_PACKAGES` | 空 | `$` 分隔的 pip 包列表 |
| `APT_PACKAGES` | 空 | 空格分隔的 APT 包 |
| `CUSTOM_INSTALL_CMD` | 空 | 镜像内的个性化安装命令 |
| `ENABLE_NGINX` | `false` | 启用 nginx 服务 |
| `ENABLE_POSTGRES` | `false` | 启用 postgres 服务 |
| `APP_DEPENDS_ON_NGINX` | `false` | app depends_on nginx |
| `APP_DEPENDS_ON_POSTGRES` | `false` | app depends_on postgres |
| `PROD_COMMAND` | `python main.py` | prod 服务命令 |
| `BUILD_DEV_IMAGE` | `true` | 是否构建 dev 镜像 |
| `DEV_IMAGE_ONLY` | `false` | 仅构建 dev 镜像：不再区分 prod/dev，部署也用 dev 镜像，Bundle 只含该镜像（优先于 `BUILD_DEV_IMAGE`） |
| `IMAGE_PREFIX` | `devcontainer` | 镜像名前缀 |
| `APP_SOURCE_DIR` | `.` | 挂载为 /app 的源码目录（不支持 `~`） |
| `APP_PORT` | 空 | 应用容器内监听端口；启用 nginx 时自动生成反代配置 |
| `ENV_FILE` | 空 | 注入 app 服务的 env 文件，逗号/空格分隔 |
| `SELINUX_RELABEL` | `false` | 挂载追加 `:z`（SELinux Enforcing 主机） |
| `DEVCONTAINER_SKIP_DOCKER` | 空 | 置 `1` 跳过 docker 步骤（本地联调） |

## 本地运行

```bash
# 需要本机有 docker（或设置 DEVCONTAINER_SKIP_DOCKER=1 跳过 docker 步骤）
PLATFORM=linux-amd64 PIP_PACKAGES='numpy$requests' \
DEVCONTAINER_SKIP_DOCKER=1 \
python scripts/devcontainer-builder/main.py
```

产物输出到仓库 `dist/` 目录（已被 .gitignore 忽略）。本地运行时可设置
`GITHUB_STEP_SUMMARY` / `GITHUB_OUTPUT` 环境变量指定输出文件，未设置时
Summary 直接打印到终端。

## 与 scripts/pip/pip_download.py 的关系

`lib/pip.py` 复用了 pip_download.py 的下载逻辑（`--only-binary=:all:` +
manylinux 平台标签 + `--python-version` 交叉下载 + 镜像源），但**直接调用
`python -m pip download`** 而非经 pip_download.py 转发，原因：

1. **平台标签展开**：pip（>= 25）对显式 `--platform` 不再向低版本 glibc 标签
   展开，只传 `manylinux_2_28_<arch>` 会漏掉仅带
   `manylinux_2_17_<arch>.manylinux2014_<arch>` 复合标签的 wheel（如 ruff）。
   本模块按目标 glibc 向下展开为多个 `--platform` 一起传入。
2. **失败判定**：pip_download.py 会吞掉 pip 的失败退出码（最终 exit 0），
   只能靠日志扫描判断；直接调用可严格依赖返回码。

## 主要设计点

- **install.sh + compose 模板（.tpl）**：src 包内的 compose 文件名为
  `docker-compose.yml.tpl`（不会被 docker compose 自动发现 / 被 `-f` 误用，
  与用户自己的 compose 配置隔离——compose 对 ports 等列表合并只做并集）。
  `install.sh <应用根目录>` 解压 src 到 `<根>/docs/devcontainer/`，把
  `{{SRC_ROOT}}` 渲染为根目录绝对路径（挂载为 /app）、生成 compose 项目名，
  并在缺少 main.py 时放置占位入口（保证 `make up` 开箱即用）。
- **离线补装（build.sh + Dockerfile.addon）**：src 包附带 addon 机制——把
  wheel 放到 `<应用根目录>/wheels/`，`bash build.sh` 基于现有镜像逐个
  `docker build --target` 生成 `<镜像名>:addon-<原TAG>` 新镜像。wheel 复制到
  镜像 `/tmp/addon-wheels` 后在同一 RUN 层内安装并删除（不增大镜像）；构建
  上下文为临时目录（只含 wheels），构建后自动清理。回滚 = 重新 docker load
  原 bundle。
- **多阶段 Dockerfile**：`prod`（运行时）与 `dev`（`FROM prod` + ruff/pytest
  等工具）在同文件内分阶段构建，compose 通过 `target` 区分；dev 服务挂
  `profiles: [dev]`，仅 `make shell/lint/test` 激活，不影响 `make up`。
- **容器默认当前用户**：Makefile 自动导出 `HOST_UID=$(id -u)` /
  `HOST_GID=$(id -g)`（可 `make shell HOST_UID=0 HOST_GID=0` 覆盖），避免
  ruff/pytest/compileall 缓存（`.ruff_cache`/`.pytest_cache`/`__pycache__`）
  以 root 属主污染挂载目录。
- **仅 dev 镜像模式**（`dev_image_only=true`）：Dockerfile 渲染为单阶段 dev
  镜像，compose 的 app 服务直接使用该 dev 镜像并显式指定 `command`，Bundle
  只包含这一个镜像（不再生成 prod 镜像文件）。app/dev 两个服务保留：prod+dev
  模式两服务镜像本就不同，统一模板可避免生成器分支；dev 服务无
  restart/ports/depends_on，工具型 `compose run` 不会误拉起外挂服务。
- **CMD 而非 ENTRYPOINT**：prod/dev 镜像默认命令均通过 `CMD` 承载，
  `docker compose up` 时由 compose `command` 覆盖执行 `python main.py`，
  `docker compose run` 时落到 dev 镜像的 `CMD ["bash"]`，互不冲突。
- **compose run 与 profile**：命令行显式指定的服务会自动激活其 profiles
  （compose v2 行为），因此 `DEV_RUN` 无需 `--profile dev`；但
  `make build`（`compose build`）需要 `--profile dev` 才会构建 dev 服务。
- **镜像 TAG**：`<yyyymmdd-HHMMSS>`（UTC），与产物文件名的时间戳一致，
  保证 compose 引用与 `docker save` 的镜像名一一对应。
- **glibc 语义**：基础镜像固定 slim-bookworm（glibc 2.36），glibc 参数仅决定
  pip download 请求的 manylinux 标签集合（目标 glibc 及以下全部标签）。
- **YAML 安全**：compose 中的 `command` 与 `volumes` 挂载路径使用
  JSON 转义后的双引号标量注入，避免命令含 `:` / 空格时破坏 YAML 结构。
