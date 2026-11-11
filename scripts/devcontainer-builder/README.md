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
    ├── Dockerfile.prod.tmpl       # prod 阶段（基础镜像 + APT/自定义命令/Oracle + 离线 pip install）
    ├── Dockerfile.dev.tmpl        # dev 阶段（FROM prod + 开发工具）
    ├── Dockerfile.devonly.tmpl    # 仅 dev 镜像模式的单阶段 Dockerfile
    ├── Dockerfile.oracle.tmpl     # Oracle runtime_deps_only 块：运行依赖/环境变量（客户端由 compose 挂载）
    ├── Dockerfile.oracle.full.tmpl # Oracle full 块：运行依赖 + 官方 Basic 包下载解压 + 环境变量
    ├── Dockerfile.node.tmpl       # Node.js/npm 块（从官方 node 镜像复制，enable_node 时插入）
    ├── compose.base.tmpl          # compose 模板骨架（app 服务 + 占位块；输出为 .tpl）
    ├── compose.service.nginx.tmpl # nginx 服务子模板
    ├── compose.service.postgres.tmpl # postgres 服务子模板（含健康检查）
    ├── nginx.conf.tmpl            # nginx 反代配置（启用 nginx 且指定 app_port 时）
    ├── Makefile.tmpl              # make 目标（安装到项目根，路径按 pwd 解析）
    ├── requirements.txt.tmpl      # pip 包清单（含预装组件）
    ├── main.py.tmpl               # 占位入口（install.sh 在应用根目录无 main.py 时复制）
    ├── install.sh.tmpl            # 安装脚本（复制/改名根目录操作文件、合并忽略文件、wheels 安装头）
    ├── Dockerfile.addon.tmpl      # 离线补装：基于现有镜像生成 addon 阶段（wheels 进 /tmp 同层删；
    │                              #  install.sh 复制到项目根时改名 Dockerfile）
    ├── build.sh.tmpl              # 离线补装入口（项目根执行，docker build 根目录 Dockerfile）
    ├── dockerignore.tmpl          # 项目根 .dockerignore（安装/合并；构建上下文排除 dist/ wheels/ 等）
    ├── gitignore.tmpl             # 项目根 .gitignore（安装/合并；忽略离线产物与补装缓存）
    ├── readme.html.tmpl           # bundle 安装说明（HTML，放进 Artifact zip，引导 dist/ 解压 + install.sh ../，含 --load 用法与 AI Agent 约定）
    └── README.src.tmpl            # src 产物内的快速上手说明（项目根为 README-devcontainer.md）
```

## 环境变量（workflow 会把 inputs 展开映射为这些变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PLATFORM` | `linux-arm64` | `linux-amd64` / `linux-arm64` |
| `PYTHON_VERSION` | `3.13` | `3.10` / `3.11` / `3.12` / `3.13` |
| `GLIBC_VERSION` | `2.28` | 固定值（workflow 不再暴露），控制 manylinux 标签 |
| `PIP_MIRROR` | `pypi.org` | 固定值（workflow 不再暴露），pip 源 |
| `PIP_PACKAGES` | 空 | `$` 分隔的 pip 包列表 |
| `APT_PACKAGES` | 空 | 空格分隔的 APT 包 |
| `CUSTOM_INSTALL_CMD` | 空 | 镜像内的个性化安装命令 |
| `ENABLE_LUCIDE` | `false` | 预装 lucide（SVG 图标库，Django/Jinja 模板用，pip 包） |
| `ENABLE_ORACLE_INSTANTCLIENT` | `none` | `none` / `runtime_deps_only`（运行依赖 + 环境变量 + `oracledb==2.5.1`，客户端由 compose 挂载）/ `full`（运行时依赖 + 官方 Basic 包完整安装进镜像） |
| `PRESET_ENVS` | 空 | 预设环境变量，单个 `》` 分隔的 `KEY=VALUE`（注入 app/dev 服务） |
| `ENABLE_NODE` | `false` | 镜像内置 Node.js + npm（前端离线开发） |
| `NODE_VERSION` | `24` | 固定值（workflow 不再暴露） |
| `NPM_PACKAGES` | 空 | `$` 分隔的全局 npm 包（需 `ENABLE_NODE=true`） |
| `NPM_REGISTRY` | `Official (npmjs.org)` | 固定为官方源（workflow 不再暴露） |
| `NPM_PACKAGES_DIR` | `packages` | Npm Download 产物目录，只读挂载到 `/opt/npm-packages` |
| `ENABLE_NGINX` | `false` | 启用 nginx 服务 |
| `ENABLE_POSTGRES` | `false` | 启用 postgres 服务 |
| `APP_DEPENDS_ON_NGINX` | `false` | app depends_on nginx |
| `APP_DEPENDS_ON_POSTGRES` | `false` | app depends_on postgres |
| `PROD_COMMAND` | `python main.py` | prod 服务命令 |
| `BUILD_DEV_IMAGE` | `true` | 是否构建 dev 镜像 |
| `DEV_IMAGE_ONLY` | `false` | 仅构建 dev 镜像：不再区分 prod/dev，部署也用 dev 镜像，镜像归档只含该镜像（优先于 `BUILD_DEV_IMAGE`） |
| `IMAGE_PREFIX` | `mydevc1` | 镜像名前缀（prod `<prefix>:<tag>` / dev `<prefix>-dev:<tag>`；Artifact 名为 `<prefix>_devcontainer_<ts>`） |
| `IMAGE_TAG` | `latest` | 镜像 TAG：`latest`（默认）或 `timestamp`（构建时间戳，UTC+8） |
| `APP_SOURCE_DIR` | `.` | 挂载为 /app 的源码目录（不支持 `~`） |
| `APP_PORT` | `3000:3000` | 端口映射 `host:container`（单端口等价同端口）；启用 nginx 时只暴露容器端口 |
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

- **install.sh + 根目录操作文件**：install.sh 先做全部前置检查再写盘（docs/
  devcontainer 不存在、compose 与根目录操作文件无同名冲突），可选 `--load`
  在安装开始前自动 docker load 同目录的镜像归档，然后：解压 src
  到 `<根>/docs/devcontainer/`（**原始副本**，仅用于把改坏的根目录文件复制回
  重置，不在该目录运行脚本）；把 compose 模板原样复制到项目根为
  `docker-compose.yml`（仅去掉 `.tpl` 后缀，不做渲染）；把 `Makefile` /
  `build.sh` / `Dockerfile.addon`（改名 `Dockerfile`）/ `README.md`（改名
  `README-devcontainer.md`）复制到项目根，安装/合并 `.dockerignore` 与
  `.gitignore`（已存在时仅追加缺失条目）；创建 `<根>/wheels/requirements.txt`
  离线安装头（`--no-index --find-links=./`，pip 按该文件所在目录解析相对
  find-links）；缺少 main.py 且 prod_command 为默认值时放置占位入口。
  Makefile/build.sh 的全部路径按**执行时 pwd** 解析，原始副本与根目录文件
  可互换。模板内 `${SRC_ROOT:-./}`（默认 `./` = 项目根目录，挂载为 /app）与
  `${SRC_ROOT_NAME:-app}`（compose 项目名后缀）由 docker compose 运行时解析。
- **离线补装（build.sh + Dockerfile.addon→根目录 Dockerfile）**：wheel 放
  项目根 `wheels/`，项目根执行 `bash build.sh` 基于现有镜像逐个
  `docker build --target` 生成 addon 新镜像（prod `<前缀>:<后缀>` / dev
  `<前缀>-dev:<后缀>`）。wheel
  复制到镜像 `/tmp/addon-wheels` 后在同一 RUN 层内安装并删除（不增大镜像）；
  构建上下文为临时目录 `.addon-build`（只含 wheels——docker 只按上下文根目录
  查找 .dockerignore，故不受根目录排除 wheels/ 影响；build.sh 还会显式清理
  上下文内任何 dockerignore 双保险），构建后自动清理。wheels/requirements.txt 含真实包名才
  按清单装，否则装目录下全部 `*.whl`（空清单不会静默 no-op）。回滚 = 重新
  docker load 原 `devcontainer-docker-images_<时间戳>.tgz`。workflow 的
  Verify 步骤含 mock docker 干跑回归测试，持续断言补装上下文不受
  .dockerignore 影响。
- **预装组件（勾选项）**：`enable_lucide` → 追加 pip 包 `lucide`（纯 Python
  wheel，Django/Jinja 模板渲染 lucide.dev SVG 图标）；`enable_oracle_instantclient`
  三选一：`none` 不安装；`runtime_deps_only` 只安装 `libaio1` / `libnsl2` 并配置
  `ORACLE_HOME` / `LD_LIBRARY_PATH` / `TNS_ADMIN`，客户端由 compose 把
  `${ORACLE_CLIENT_DIR:-/opt/oracle/instantclient19}` 只读挂载到容器
  `/opt/oracle/instantclient19`（多容器共用）；`full` 参考
  [oracle2excel](https://github.com/wl-xiang/oracle2excel/blob/main/Dockerfile)
  在构建期下载官方 Instant Client 19 Basic 包并解压进镜像（客户端随镜像分发，
  不生成挂载）。后两者都追加 `oracledb==2.5.1`；
  `enable_node` → 从官方 `node:24-slim-bookworm` 复制 node/npm，可选
  `npm_packages` 构建期从官方 npm 源全局安装；Npm Download 产物目录由 compose
  只读挂载到 `/opt/npm-packages`，配合 `make npm-install` 离线安装前端依赖。
  两者的 pip 包并入 requirements.txt 与 pip download（用户显式列出同名包时
  以用户声明为准），环境变量与 workflow inputs 一一对应。
- **预设环境变量**：`preset_envs`（单个 `》` 分隔的 `KEY=VALUE`）渲染为 compose
  app/dev 服务的 `environment`；与 Oracle 默认变量合并（同名覆盖），值中的
  `$` 转义为 `$$` 保证按字面量注入。
- **多阶段 Dockerfile**：`prod`（运行时）与 `dev`（`FROM prod` + ruff/pytest
  等工具）在同文件内分阶段构建，compose 通过 `target` 区分；dev 服务挂
  `profiles: [dev]`，仅 `make shell/lint/test` 激活，不影响 `make up`。
- **容器默认当前用户**：Makefile 自动导出 `HOST_UID=$(id -u)` /
  `HOST_GID=$(id -g)`（可 `make shell HOST_UID=0 HOST_GID=0` 覆盖），避免
  ruff/pytest/compileall 缓存（`.ruff_cache`/`.pytest_cache`/`__pycache__`）
  以 root 属主污染挂载目录。
- **仅 dev 镜像模式**（`dev_image_only=true`）：Dockerfile 渲染为单阶段 dev
  镜像，compose 的 app 服务直接使用该 dev 镜像，启动命令同样由 compose 的
  `command` 显式承载（镜像 CMD 为 bash），镜像归档只包含这一个镜像（不再生成
  prod 镜像文件）。app/dev 两个服务保留：
  prod+dev 模式两服务镜像本就不同，统一模板可避免生成器分支；dev 服务无
  restart/ports/depends_on，工具型 `compose run` 不会误拉起外挂服务。
- **启动方式显式写入 compose**：prod/dev 镜像默认命令通过 `CMD` 承载
  （直接 `docker run` 仍可用）；安装生成的 `docker-compose.yml` 在 app 服务
  上固定写入 `entrypoint: []`（清空镜像 ENTRYPOINT）与 `command`（默认
  `prod_command`），用户直接改这两行即可调整启动命令，或按模板注释换成自定义
  启动脚本（挂载 `./my-start.sh` → `entrypoint: ["/bin/bash",
  "/opt/my-start.sh"]` + `command: []`），均无需重建镜像；
  `docker compose run --rm app <命令>` 仍按传入命令执行，
  `make shell` 走 dev 镜像的 `CMD ["bash"]`，互不冲突。
- **compose run 与 profile**：命令行显式指定的服务会自动激活其 profiles
  （compose v2 行为），因此 `DEV_RUN` 无需 `--profile dev`；但
  `make build`（`compose build`）需要 `--profile dev` 才会构建 dev 服务。
- **镜像命名与 TAG**：prod 为 `<前缀>:<TAG>`、dev 为 `<前缀>-dev:<TAG>`（如
  `devcontainer:latest` / `devcontainer-dev:latest`；`IMAGE_TAG=timestamp` 时为
  `devcontainer:20260101-120000` / `devcontainer-dev:20260101-120000`）。TAG
  由 `IMAGE_TAG` 选择 `latest`（默认）或构建时间戳（UTC+8）。产物文件名
  （bundle zip / 镜像归档 tgz / src tgz）统一使用 UTC+8 时间戳。
- **唯一 Artifact**：`<镜像前缀>_devcontainer_<时间戳>` 一个 zip 内含
  `devcontainer-docker-images_<时间戳>.tgz`（docker save 直出 gzip，docker
  load 用）、`devcontainer-src_<时间戳>.tgz`、`install.sh` 与 `readme.html`
  四个文件；"Bundle" 专指该外部 zip，镜像归档文件名用 "Docker Images"。
  安装方式：zip 放项目根 `dist/` 解压后 `bash install.sh ../`（加 `--load`
  可在安装开始前自动 docker load 同目录的镜像归档 tgz）。
- **镜像瘦身**：基础镜像 slim-bookworm；apt 安装后同层 `apt-get clean` 并清理
  lists/archives；pip 统一 `--no-compile`（不生成 `.pyc`）；Node 仅复制
  node/npm 并删除 npm 自带 docs/man；Oracle `full` 模式的 wget/unzip 只用于
  构建期，安装/下载/`apt-get purge --auto-remove` 在同一 RUN 层完成，不残留
  在运行时镜像。dev 与 prod 共享基础层，`docker save` 归档中公共层只存一份。
- **AI Agent 约定**：src 产物 `README.md`（安装为 `README-devcontainer.md`）与
  `readme.html` 均包含「给 AI Agent 的使用约定」：Python/Node 命令一律通过
  `docker compose run --rm dev ...` / `make test` 等在容器内执行，不依赖宿主机
  Python；workflow 的 Verify 步骤会 grep 校验该段落存在。
- **glibc 语义**：基础镜像固定 slim-bookworm（glibc 2.36），glibc 参数仅决定
  pip download 请求的 manylinux 标签集合（目标 glibc 及以下全部标签）。
- **YAML 安全**：compose 中的 `command`、`/app` 挂载与 `environment` 值使用
  JSON 转义后的双引号标量注入，避免命令/环境变量含 `:`、空格、`$` 时破坏
  YAML 结构；Oracle/npm 的只读挂载使用 compose 运行时变量
  （`${ORACLE_CLIENT_DIR:-...}` / `${NPM_PACKAGES_DIR:-...}`），挂载路径在参数
  校验阶段限制为安全字符。
