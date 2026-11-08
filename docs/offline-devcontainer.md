# 离线 Python 开发环境（build-devcontainer）使用手册

本工作流解决「外网开发 → 内网运行」的链路割裂问题：在外网 GitHub Actions 上
按参数构建通用的离线开发/运行 Docker 镜像并打包，内网机器只需有 Docker，
通过 Volume 挂载源码 + docker compose 即可开发与运行，**内网本机无需安装任何
Python 环境**。

## 运行模型

```
外网 GitHub Runner                         内网离线机器
────────────────────                       ────────────────────
参数解析与校验
模板渲染 (Dockerfile/compose.tpl/Makefile)
pip download → wheels/
docker build (prod → dev / 仅 dev)         docker load bundle tgz
docker pull (nginx/postgres, 按需)         bash install.sh <应用根目录>
打包 src tgz + bundle tgz + install.sh     → <应用根>/docs/devcontainer/
────────── 传输（3 个 Artifacts）────────→  cd <应用根>/docs/devcontainer
上传 Artifacts + 写 Summary                make check / shell / lint / compile / test
                                           make up (python main.py)
```

## 使用前提

- 已 Fork 本仓库到你的 GitHub 账号（工作流需以你的身份运行）。
- 内网机器：Docker >= 20.10（建议 23+），且带 compose v2 插件（`docker compose version` 可执行）。
- 内网机器 CPU 架构需与构建时选择的平台一致（amd64 / arm64），否则容器启动报
  `exec format error`。
- 应用代码放在独立的项目根目录（如 `~/apps/myapp1`），devcontainer 文件由
  `install.sh` 安装到该目录下的 `docs/devcontainer/`，与业务代码互不混放。

## 触发构建

1. 进入 Fork 后的仓库，点击 **Actions** → 左侧选择 **Build DevContainer** →
   **Run workflow**。
2. 填写参数后运行。运行完成后在 **Summary** 底部 **Artifacts** 下载三个产物：
   - `devcontainer-src_<时间戳>.tgz`：运行时源码包（compose 模板、Makefile 等）
   - `devcontainer-bundle_<时间戳>.tgz`：镜像 Bundle 包
   - `install.sh`：安装脚本（把 src 包安装到应用根目录的 `docs/devcontainer/`）

   > Artifacts 只能是 zip 封装，工作流已设置 `compression-level: 0`（仅存储、
   > 不再二次压缩），解压 zip 即得到产物文件。
3. Summary 页同时给出本次构建的完整摘要与内网使用步骤。

### 触发参数（Inputs）

| 参数 | 类型 | 取值 / 格式 | 默认值 | 说明 |
|------|------|------------|--------|------|
| `platform` | choice | `linux-amd64` / `linux-arm64` | `linux-amd64` | 目标平台（需与内网机器 CPU 架构一致） |
| `python_version` | choice | `3.12` / `3.13` | `3.13` | 容器内 Python 版本 |
| `glibc_version` | choice | `2.17` / `2.28` / `2.34` | `2.28` | 控制 pip download 选用的 manylinux 标签（见「glibc 语义」） |
| `pip_mirror` | choice | `pypi.org` / `aliyun` / `thu` | `thu` | pip 下载镜像源 |
| `pip_packages` | string | 用 `$` 分隔，如 `numpy$pandas$requests` | 空 | 附加 pip 包（空 = 无附加依赖） |
| `apt_packages` | string | 空格分隔，如 `git vim curl` | 空 | 镜像内安装的 APT 工具 |
| `custom_install_cmd` | string | shell 命令 | 空 | 个性化安装命令，在镜像内 `RUN` 执行 |
| `enable_nginx` | boolean | — | `false` | 启用 nginx 外挂服务（8080:80） |
| `enable_postgres` | boolean | — | `false` | 启用 postgres 外挂服务（postgres:16，数据卷 pgdata） |
| `app_depends_on_nginx` | boolean | — | `false` | app 服务 `depends_on` nginx（需先启用 nginx） |
| `app_depends_on_postgres` | boolean | — | `false` | app 服务 `depends_on` postgres（需先启用 postgres） |
| `prod_command` | string | 命令行 | `python main.py` | prod 服务启动命令 |
| `build_dev_image` | boolean | — | `true` | 是否同时构建 dev 镜像（ruff/pytest 等，继承 prod） |
| `dev_image_only` | boolean | — | `false` | 仅构建 dev 镜像：不再区分 prod/dev 两个镜像，部署（`make up`）也使用 dev 镜像，Bundle 只包含该 dev 镜像（优先于 `build_dev_image`） |
| `image_prefix` | string | 小写字母/数字/`._-` | `devcontainer` | 镜像名前缀（生成 `<prefix>-prod:<tag>` / `<prefix>-dev:<tag>`；仅 dev 镜像模式只有 `<prefix>-dev:<tag>`） |
| `app_source_dir` | string | 相对/绝对路径 | `.` | 挂载进容器 `/app` 的目录：`.` = 整个项目根目录；相对路径 = 项目根目录下的子目录（如 monorepo 中的应用子目录，可避免 ruff/pytest 扫到无关源码）；也支持绝对路径。项目根目录由 `install.sh` 安装时传入（不支持 `~`） |
| `app_port` | string | 端口号 | 空 | 应用在容器内监听的端口。设置后：无 nginx 时映射宿主机同端口；启用 nginx 时由 nginx 反代，app 仅容器网络暴露 |
| `env_file` | string | 逗号/空格分隔 | 空 | 注入 app 服务的 env 文件（相对应用根目录，如 `.env`；也支持绝对路径） |
| `selinux_relabel` | boolean | — | `false` | 给 `/app` 挂载追加 `:z` 重打标签（SELinux Enforcing 主机需要） |

> **提示**：`pip_packages` 输入框无法换行，使用 `$` 分隔多个包，与
> `pip_download.yml` 的约定一致。

### 参数校验规则

以下情况会在构建开始前直接失败并给出清晰错误：

- `app_depends_on_nginx=true` 但 `enable_nginx=false`
- `app_depends_on_postgres=true` 但 `enable_postgres=false`
- `platform` / `python_version` / `glibc_version` / `pip_mirror` 不在取值范围内
- `image_prefix` 含非法字符（仅允许小写字母/数字/`.`/`_`/`-`）
- `prod_command` 无法解析为命令
- `app_port` 不是 1-65535 的整数
- `app_source_dir` / `env_file` 使用 `~`（不会展开，请写绝对路径或相对路径）

## 产物说明

### devcontainer-src_<yyyymmdd-HHMMSS>.tgz

解压后得到顶层目录 `devcontainer-src/`（正常使用无需手动解压，由 `install.sh`
完成）：

```
devcontainer-src/
├── Dockerfile                   # 多阶段 prod/dev；仅 dev 镜像模式下为单阶段 dev
├── docker-compose.yaml.tpl      # compose 模板（install.sh 渲染为 docker-compose.yaml）
├── Makefile                     # check/up/down/shell/lint/compile/test 等
├── main.py                      # 占位入口（应用根目录无 main.py 时由 install.sh 复制）
├── requirements.txt             # pip 包清单
├── nginx/conf.d/                # 仅 enable_nginx 且指定 app_port 时生成反代配置
├── scripts/                     # 仓库随附的离线下载工具（pip/npm）
└── README.md                    # 快速上手说明
```

`wheels/` 不再随源码包分发：所有 wheel 已在镜像构建阶段安装，并固化在镜像
`/wheels` 内，内网可直接在容器中离线安装（见「prod / dev 镜像」）。

### install.sh

安装脚本（独立 Artifact）。把本脚本与 src tgz 放在同一目录，执行：

```bash
bash install.sh ~/apps/myapp1        # 参数 = 你的项目根目录
```

脚本会：

1. 在 `<项目根>/docs/devcontainer/` 下解压 src 包（目录已存在则报错，
   避免新旧版本混装；重新安装请先删除该目录）；
2. 渲染 `docker-compose.yaml.tpl` → `docker-compose.yaml`：`{{SRC_ROOT}}`
   占位符替换为项目根目录**绝对路径**（挂载为容器 `/app`），并按项目目录名
   生成 compose 项目名（如 `devcontainer-myapp1`）；
3. 项目根目录没有 `main.py` 且启动命令为默认的 `python main.py` 时，复制
   占位 `main.py`（不覆盖已有文件）。

> 为什么 compose 文件带 `.tpl` 后缀：避免被 docker compose 自动发现或被
> `-f` 误用，与项目根目录下用户自己的 compose 配置彻底隔离——compose 多
> 文件合并对 `ports` 等列表只做并集、无法通过 override 移除，`*.override.yaml`
> 自动合并也会产生同样问题。渲染出的 `docker-compose.yaml` 位于
> `docs/devcontainer/`，可放心手工修改。

### devcontainer-bundle_<yyyymmdd-HHMMSS>.tgz

该文件是 `docker save` 输出经 gzip 压缩得到的镜像归档（prod、dev、nginx、postgres，
按本次参数），可直接 `docker load -i` 导入，无需再解一层 tar。勾选 `dev_image_only`
时归档中只有一个 dev 镜像（外加按需启用的 nginx/postgres）。文件名时间戳与镜像
TAG 一致；Summary 中同时给出 SHA256，便于校验传输完整性。

## 内网使用步骤

```bash
# 1. 下载三个 Artifacts（各自解压 zip），放到同一目录：
#    install.sh  devcontainer-src_<ts>.tgz  devcontainer-bundle_<ts>.tgz

# 2. 导入镜像
docker load -i devcontainer-bundle_20260101-120000.tgz

# 3. 安装到应用根目录（参数 = 你的项目根目录）
bash install.sh ~/apps/myapp1

# 4. 离线自检：镜像是否已导入、CPU 架构是否匹配
cd ~/apps/myapp1/docs/devcontainer
make check

# 5. 开发阶段
make shell      # 进入 dev 容器交互式 bash（含 ruff/pytest 等）
make lint       # ruff check .
make compile    # python -m compileall -q .
make test       # pytest -q

# 6. 运行阶段（--no-build，不会联网构建/拉取）
make up
make logs       # 跟随日志
make down       # 停止
```

## Makefile 目标

所有 make 命令在 `<应用根目录>/docs/devcontainer/` 下执行。

| 目标 | 说明 |
|------|------|
| `make help` | 列出所有目标（目标说明须写在 `## ` 双井号之后才会显示） |
| `make check` | **离线自检**：打印 docker 架构，逐个确认本次镜像已导入（缺失时提示 `docker load`） |
| `make build` | `docker compose build`（**需联网**：发布包不含 wheels/，deps 从 apt/pip 源安装；离线机器勿用） |
| `make up` | `docker compose up -d --no-build`，后台启动 prod 服务（及已启用的外挂服务） |
| `make down` | 停止并移除容器与网络 |
| `make ps` | 查看容器状态 |
| `make logs` | 跟随查看日志 |
| `make shell` / `make dev` | 进入 dev 容器交互式 bash |
| `make lint` | ruff check . |
| `make compile` | python -m compileall -q . |
| `make test` | pytest -q |
| `make package-src` | 重新打包当前源码目录为 tgz |

> `shell/dev/lint/compile/test` 依赖 dev 镜像（`build_dev_image=true` 或
> `dev_image_only=true` 时才有），通过 compose 的 `dev` profile 激活，不影响
> `make up` 的运行行为。
>
> 容器默认以当前用户身份运行：Makefile 自动导出 `HOST_UID`/`HOST_GID`
> （`$(id -u)` / `$(id -g)`），避免挂载目录出现 root 属主文件。临时需要
> root 时：`make shell HOST_UID=0 HOST_GID=0`（命令行变量优先于默认值）。

## 外挂服务

- **nginx**（`enable_nginx`）：`nginx:stable`，宿主机 `http://<host>:8080` →
  容器 80 端口。指定 `app_port` 时会生成 `nginx/conf.d/default.conf` 并挂载，
  自动反代到 `app:<app_port>`；未指定 `app_port` 时只启动默认 nginx，需要自行
  提供配置文件。
- **postgres**（`enable_postgres`）：`postgres:16`，带 `pg_isready` 健康检查，
  仅容器网络内可达，连接串
  `postgres://postgres:postgres@postgres:5432/postgres`，数据持久化在 `pgdata`
  卷（`make down` 不删除数据卷）。
- `app_depends_on_*` 生成 compose 的 `depends_on`：nginx 用 `service_started`，
  postgres 用 `service_healthy`（等待健康检查通过，避免启动期连接被拒）。
- 所有服务均设置 `restart: unless-stopped` 与 `pull_policy: never`，离线环境
  不会尝试拉取镜像。

## 设计说明

### install.sh 与 compose 模板（.tpl）

- src 包内的 compose 文件名为 `docker-compose.yaml.tpl`：`.tpl` 后缀保证它
  不会被 docker compose 自动发现，也不会被 `-f` 误用。compose 多文件合并对
  `ports` 等列表只做**并集**（无法通过 override 移除），`*.override.yaml`
  自动合并也会产生同样的问题——隔离后，devcontainer 的 compose 与应用根目录
  下用户自己的 compose 配置互不影响。
- `install.sh <项目根目录>` 把 src 包解压到 `<项目根>/docs/devcontainer/`，
  并渲染模板：`{{SRC_ROOT}}` → 项目根目录绝对路径（挂载为容器 `/app`，
  避免「相对路径以第一个 -f 文件所在目录为基准」的歧义），项目名固定为
  `<image_prefix>-<项目目录名>`（避免默认取目录名导致多应用冲突）。
- 渲染出的 `docker-compose.yaml` 是用户可改的副本，`.tpl` 保持原样。
- 应用根目录没有 `main.py` 且启动命令为默认值时，install.sh 复制占位
  `main.py`，保证 `make up` 开箱即用（否则 `python main.py` 立即退出，配合
  `restart: unless-stopped` 会无限重启）。

### 容器用户（root 污染防护）

- compose 中 app/dev 服务均设置 `user: "${HOST_UID:-0}:${HOST_GID:-0}"`。
  Makefile 自动导出 `HOST_UID=$(id -u)` / `HOST_GID=$(id -g)`，容器默认以
  当前用户身份运行——否则 ruff（`.ruff_cache`）、pytest（`.pytest_cache`）、
  compileall（`__pycache__`）及应用写入的文件都会变成 root 属主，普通用户
  无法删除。
- 需要 root（容器内 `pip install` 到系统目录）时：
  `make shell HOST_UID=0 HOST_GID=0`。
- 已知无害副作用：非 root UID 在容器内没有 passwd 条目，bash 提示
  `I have no name!`；`app_port < 1024` 时非 root 无法绑定低端口。

### glibc 语义

- 基础镜像固定为 `python:<version>-slim-bookworm`（glibc 2.36），保证任何
  manylinux ≤ 2.34 标签的 wheel 都可运行。
- `glibc_version` 仅控制 **pip download 阶段选用的 manylinux 标签**：下载时会
  请求该 glibc 及其以下的所有 manylinux 标签（含 manylinux2014 别名），即
  「兼容目标 glibc」的 wheel 集合。
- 之所以传多个 `--platform`：pip（>= 25）对显式 `--platform` 不再做低版本 glibc
  标签展开，只传 `manylinux_2_28` 会漏掉仅带 `manylinux_2_17/manylinux2014`
  复合标签的 wheel（如 ruff）。

### prod / dev 镜像

- 单个 `Dockerfile` 多阶段构建：`prod` 只含运行时；`dev` 阶段 `FROM prod`
  追加 git/curl/vim/make 与 ruff/pytest/pytest-cov（wheel 在构建阶段随
  `wheels/` 离线安装）。
- 镜像使用 `CMD`（而非 `ENTRYPOINT`）承载默认命令：`make up` 时 compose 的
  `command` 直接覆盖 CMD 执行 `python main.py`；`make shell` 通过 dev 镜像的
  `CMD ["bash"]` 进入交互终端，两者互不干扰。
- 勾选 `dev_image_only` 时不再生成两个镜像：Dockerfile 只有单阶段 `dev`，
  compose 的 app 服务直接引用该 dev 镜像并显式写入 `command`（镜像 CMD 为
  bash），`make up` 与 `make shell/lint/test` 共用同一个镜像；Bundle 中也只
  保存这一个镜像。
- `wheels/` 在构建时被复制到镜像 `/wheels` 并保留下来（构建上下文中的
  `wheels/` 不会进入发布包），内网可在容器内继续离线安装：
  `pip install --no-index --find-links=/wheels <pkg>`。

### 依赖下载

- 复用 `pip download --only-binary=:all:` 快速失败策略：无 wheel 的源码包
  会直接报错，此时请改用 `custom_install_cmd` 预编译，或反馈调整参数。
- dev 工具（ruff/pytest/pytest-cov）的 wheel 会在构建 dev 镜像时一并下载。
- **业务依赖必须在 `pip_packages` 中显式列出**（构建端拿不到业务代码，无法
  自动解析业务 `requirements.txt`）。漏装会在离线运行时表现为
  `ModuleNotFoundError`，而内网无法现场安装（`/wheels` 只含构建时下载的包）。

## FAQ

**Q: 为什么内网 `make up` 报错找不到镜像 / 尝试联网构建？**
先执行 `docker load -i devcontainer-bundle_<时间戳>.tgz` 导入镜像，再在
`docs/devcontainer` 目录执行 `make check` 确认所有镜像存在；`make up` 使用
`--no-build`，compose 中也设置了 `pull_policy: never`，不会联网。若仍失败，
说明镜像 TAG 与 compose 中不一致，请确认使用同一时间戳的 src 与 bundle。

**Q: `docker load` 成功但容器起不来，日志报 `exec format error`？**
构建平台与服务器 CPU 架构不一致（例如构建时选了 `linux-arm64`，服务器是 x86）。
用 `uname -m` / `docker version` 确认后，按服务器架构重新构建。

**Q: 传输后 `docker load` 报 `unexpected EOF` / 校验不符？**
bundle 通常几百 MB 到 1 GB+，传输中断很常见。对比 Summary 中的 SHA256：
`sha256sum devcontainer-bundle_<tag>.tgz`，不一致就重新传输。

**Q: `docker load` 磁盘空间不足？**
导入过程需要约 2 倍镜像体积的临时空间（`docker info` 查看 Docker Root Dir 所在分区）。

**Q: 业务项目里会被放进哪些 devcontainer 文件？**
只有 `docs/devcontainer/` 一个目录（以及应用根目录没有 `main.py` 时复制的
占位 `main.py`）。其余业务文件一律不动，也不会与业务自带的
`requirements.txt` / `README.md` 冲突（同名文件都在 `docs/devcontainer/` 内）。

**Q: 如何重新安装 / 更新到新构建的版本？**
删除旧的 `<应用根>/docs/devcontainer`（注意保留你手工修改过的
`docker-compose.yaml` 等文件），再用新的 `install.sh` + src tgz 重新安装。
`install.sh` 遇到已存在的目录会直接报错，避免新旧版本混装。

**Q: `make up` 后容器一直重启（Restarting）？**
`python: can't open file '/app/main.py'` 类错误说明启动命令指向的入口不存在：
确认项目根目录（或 `app_source_dir` 指定的子目录）下有对应入口文件，或修改
`docs/devcontainer/docker-compose.yaml` 中的 `command`。注意镜像 TAG 必须与
src 同时间戳（先 `make check` 自检）。

**Q: 挂载目录里出现 root 属主文件 / 宿主机无法修改？**
默认不会：Makefile 自动导出 `HOST_UID`/`HOST_GID`（当前用户），容器以你的
身份运行。若你曾用 `HOST_UID=0` 运行产生了 root 文件，用
`sudo rm -rf <路径>` 清理，或 `sudo chown -R $(id -u):$(id -g) <路径>` 改回
属主。容器内需要 root 时：`make shell HOST_UID=0 HOST_GID=0`。

**Q: SELinux Enforcing 主机上容器读不到 `/app`？**
构建时把 `selinux_relabel` 设为 `true`（挂载追加 `:z`），或手动修改
`docs/devcontainer/docker-compose.yaml` 中 app/dev 服务的 `volumes`，在挂载
路径末尾追加 `:z`。

**Q: 应用起来了但宿主机访问不到？**
构建时设置 `app_port`（应用在容器内监听的端口），并确认应用监听 `0.0.0.0`
而不是 `127.0.0.1`。启用 nginx 时宿主机访问 `:8080`，由 nginx 反代到 app。

**Q: 跨架构构建（amd64 Runner 构建 arm64 镜像）很慢？**
arm64 构建通过 QEMU 模拟执行，速度约为原生 1/5~1/10，属正常现象；工作流已
设置 90 分钟超时。条件允许时优先在原生架构 Runner 上构建。

**Q: 某个 pip 包下载失败（No matching distribution）？**
多为该包无目标平台的 wheel（只有 sdist）。改用 `custom_install_cmd` 预编译，
或换用 `platform`/`python_version` 组合。

**Q: 如何使用私有 PyPI？**
第一版未内置私有源选项。可 Fork 后在 `scripts/devcontainer-builder/lib/params.py`
的 `PIP_MIRRORS` 中增加条目（含认证 URL），或经镜像反代公开化。

**Q: bundle 体积偏大？**
bundle 含 prod+dev（或仅 dev）+外挂服务镜像，几百 MB 到 1GB+ 属正常。勾选
`dev_image_only` 可少打一个 prod 镜像；后续可引入分层/增量导出方案优化；
Summary 中记录了每次产物大小作为基线。

**Q: 内网 Docker / Compose 版本较老？**
建议 Docker >= 20.10（23+ 更稳妥，兼容 containerd image store 导出的归档）、
compose v2。生成的 compose 使用 `profiles`、`depends_on` 的 `condition`、
`pull_policy`（均需 compose v2）。若不支持，`make up` 仍可用（dev 服务会被忽略），
但 `make shell/lint/test` 需升级 compose 或改用
`docker run -it --rm -v $PWD:/app -w /app <dev镜像> bash`。
