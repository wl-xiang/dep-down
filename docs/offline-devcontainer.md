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
模板渲染 (Dockerfile/compose/Makefile)
pip download → wheels/
docker build (prod → dev)                  解压 bundle → docker load
docker pull (nginx/postgres, 按需)         解压 src → 进入项目目录
打包 src tgz + bundle tgz ──── 传输 ────→  make shell / lint / compile / test
上传 Artifacts + 写 Summary                make up (python main.py)
```

## 使用前提

- 已 Fork 本仓库到你的 GitHub 账号（工作流需以你的身份运行）。
- 内网机器：Docker >= 20.10，且带 compose v2 插件（`docker compose version` 可执行）。
- 内网机器 CPU 架构需与构建时选择的平台一致（amd64 / arm64）。

## 触发构建

1. 进入 Fork 后的仓库，点击 **Actions** → 左侧选择 **Build DevContainer** →
   **Run workflow**。
2. 填写参数后运行。运行完成后在 **Summary** 底部 **Artifacts** 下载两个产物：
   - `devcontainer-src_<时间戳>.tgz`：运行时源码包
   - `devcontainer-bundle_<时间戳>.tgz`：镜像 Bundle 包

   > Artifacts 只能是 zip 封装，工作流已设置 `compression-level: 0`（仅存储、
   > 不再二次压缩），解压 zip 即得到唯一的 tgz 产物。
3. Summary 页同时给出本次构建的完整摘要与内网使用步骤。

### 触发参数（Inputs）

| 参数 | 类型 | 取值 / 格式 | 默认值 | 说明 |
|------|------|------------|--------|------|
| `platform` | choice | `linux-amd64` / `linux-arm64` | `linux-arm64` | 目标平台 |
| `python_version` | choice | `3.12` / `3.13` | `3.13` | 容器内 Python 版本 |
| `glibc_version` | choice | `2.17` / `2.28` / `2.34` | `2.28` | 控制 pip download 选用的 manylinux 标签（见「glibc 语义」） |
| `pip_mirror` | choice | `pypi.org` / `aliyun` / `thu` | `thu` | pip 下载镜像源 |
| `pip_packages` | string | 用 `$` 分隔，如 `numpy$pandas$requests` | 空 | 附加 pip 包（空 = 无附加依赖） |
| `apt_packages` | string | 空格分隔，如 `git vim curl` | 空 | prod 镜像内安装的 APT 工具 |
| `custom_install_cmd` | string | shell 命令 | 空 | 个性化安装命令，在 prod 镜像内 `RUN` 执行 |
| `enable_nginx` | boolean | — | `false` | 启用 nginx 外挂服务（8080:80） |
| `enable_postgres` | boolean | — | `false` | 启用 postgres 外挂服务（postgres:16，数据卷 pgdata） |
| `app_depends_on_nginx` | boolean | — | `false` | app 服务 `depends_on` nginx（需先启用 nginx） |
| `app_depends_on_postgres` | boolean | — | `false` | app 服务 `depends_on` postgres（需先启用 postgres） |
| `prod_command` | string | 命令行 | `python main.py` | prod 服务启动命令 |
| `build_dev_image` | boolean | — | `true` | 是否同时构建 dev 镜像（ruff/pytest 等，继承 prod） |
| `image_prefix` | string | 小写字母/数字/`._-` | `devcontainer` | 镜像名前缀（生成 `<prefix>-prod:<tag>` / `<prefix>-dev:<tag>`） |
| `app_source_dir` | string | 相对路径 | `.` | 挂载进容器 `/app` 的源码目录（相对 compose 文件） |

> **提示**：`pip_packages` 输入框无法换行，使用 `$` 分隔多个包，与
> `pip_download.yml` 的约定一致。

### 参数校验规则

以下情况会在构建开始前直接失败并给出清晰错误：

- `app_depends_on_nginx=true` 但 `enable_nginx=false`
- `app_depends_on_postgres=true` 但 `enable_postgres=false`
- `platform` / `python_version` / `glibc_version` / `pip_mirror` 不在取值范围内
- `image_prefix` 含非法字符（仅允许小写字母/数字/`.`/`_`/`-`）
- `prod_command` 无法解析为命令

## 产物说明

### devcontainer-src_<yyyymmdd-HHMMSS>.tgz

解压后得到顶层目录 `devcontainer-src/`：

```
devcontainer-src/
├── Dockerfile              # 多阶段：prod（+ dev，若构建）
├── docker-compose.yaml     # app + dev(profile) + 外挂服务
├── Makefile                # up/down/shell/lint/compile/test 等
├── requirements.txt        # pip 包清单
├── scripts/                # 仓库随附的离线下载工具（pip/npm）
└── README.md               # 快速上手说明
```

`wheels/` 不再随源码包分发：所有 wheel 已在镜像构建阶段安装，并固化在镜像
`/wheels` 内，内网可直接在容器中离线安装（见「prod / dev 镜像」）。

应用代码默认放在该目录下（整目录挂载为容器 `/app`）。

### devcontainer-bundle_<yyyymmdd-HHMMSS>.tgz

内含 `images.tar`：`docker save` 导出的镜像集合（prod、dev、nginx、postgres，
按本次参数）。文件名时间戳与镜像 TAG 一致。

## 内网使用步骤

```bash
# 1. 导入镜像
tar xzf devcontainer-bundle_20260101-120000.tgz
docker load -i images.tar

# 2. 解压运行时产物
tar xzf devcontainer-src_20260101-120000.tgz
cd devcontainer-src

# 3. 将应用代码放入本目录（如 main.py；prod 默认命令为 python main.py）

# 4. 开发阶段
make shell      # 进入 dev 容器交互式 bash（含 ruff/pytest 等）
make lint       # ruff check .
make compile    # python -m compileall -q .
make test       # pytest -q

# 5. 运行阶段
make up         # docker compose up -d（prod + 外挂服务）
make logs       # 跟随日志
make down       # 停止
```

## Makefile 目标

| 目标 | 说明 |
|------|------|
| `make help` | 列出所有目标 |
| `make build` | `docker compose build`（**需联网**：发布包不含 wheels/，deps 从 apt/pip 源安装；离线机器勿用） |
| `make up` | 后台启动 prod 服务（及已启用的外挂服务） |
| `make down` | 停止并移除容器与网络 |
| `make ps` | 查看容器状态 |
| `make logs` | 跟随查看日志 |
| `make shell` / `make dev` | 进入 dev 容器交互式 bash |
| `make lint` | ruff check . |
| `make compile` | python -m compileall -q . |
| `make test` | pytest -q |
| `make package-src` | 重新打包当前源码目录为 tgz |

> `shell/dev/lint/compile/test` 依赖 dev 镜像（`build_dev_image=true` 时才有），
> 通过 compose 的 `dev` profile 激活，不影响 `make up` 的 prod 行为。

## 外挂服务

- **nginx**（`enable_nginx`）：`nginx:stable`，宿主机 `http://<host>:8080` →
  容器 80 端口。反向代理配置可在解压目录中自行挂载扩展。
- **postgres**（`enable_postgres`）：`postgres:16`，仅容器网络内可达，连接串
  `postgres://postgres:postgres@postgres:5432/postgres`，数据持久化在 `pgdata`
  卷（`make down` 不删除数据卷）。
- `app_depends_on_*` 生成 compose 的 `depends_on`（启动顺序，不含健康检查）；
  应用如需等待数据库就绪，请在代码中实现重试。

## 设计说明

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
- `wheels/` 在构建时被复制到镜像 `/wheels` 并保留下来（构建上下文中的
  `wheels/` 不会进入发布包），内网可在容器内继续离线安装：
  `pip install --no-index --find-links=/wheels <pkg>`。

### 依赖下载

- 复用 `pip download --only-binary=:all:` 快速失败策略：无 wheel 的源码包
  会直接报错，此时请改用 `custom_install_cmd` 预编译，或反馈调整参数。
- dev 工具（ruff/pytest/pytest-cov）的 wheel 会在构建 dev 镜像时一并下载。

## FAQ

**Q: 为什么内网 `make up` 报错找不到镜像 / 尝试联网构建？**
先执行 `docker load -i images.tar` 导入镜像；`make up` 不会自动构建。若仍提示
build，说明镜像 TAG 与 compose 中不一致，请确认使用同一时间戳的 src 与 bundle。

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
bundle 含 prod+dev+外挂服务镜像，几百 MB 到 1GB+ 属正常。后续可引入分层/增量
导出方案优化；Summary 中记录了每次产物大小作为基线。

**Q: 内网 Docker Compose 版本较老？**
生成的 compose 使用 `profiles`（需 compose v1.27+/v2）与 `depends_on` 列表
语法。若内网 compose 不支持 profiles，`make up` 仍可用（dev 服务会被忽略），
但 `make shell/lint/test` 需升级 compose 或改用
`docker run -it --rm -v $PWD:/app -w /app <dev镜像> bash`。
