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
docker build (prod → dev / 仅 dev)         zip 放入项目根目录 dist/ 解压
docker pull (nginx/postgres, 按需)         docker load 镜像归档 tgz
打包镜像归档 tgz + src tgz + install.sh    bash install.sh ../ (dist/ 内执行)
  + readme.html → 1 个 Artifact zip       → 项目根: Makefile/Dockerfile/build.sh/
────────── 传输（1 个 Artifact zip）─────→   README-devcontainer.md/.dockerignore/
上传唯一 Artifact + 写 Summary               .gitignore/docker-compose.yml
                                           → docs/devcontainer/ (原始副本, 重置用)
cd <项目根>（所有命令都在根目录执行）
make check / shell / lint / compile / test
make up (python main.py)
```

## 使用前提

- 已 Fork 本仓库到你的 GitHub 账号（工作流需以你的身份运行）。
- 内网机器：Docker >= 20.10（建议 23+），且带 compose v2 插件（`docker compose version` 可执行）。
  仅安装了 `docker-compose`（v1）时，install.sh 会自动把 Makefile 的 `COMPOSE` 改为 `docker-compose`；
  两者都没有时安装仍可完成，但会提示先安装 docker compose。
- 内网机器 CPU 架构需与构建时选择的平台一致（amd64 / arm64），否则容器启动报
  `exec format error`。
- 应用代码放在独立的项目根目录（如 `~/apps/myapp1`）。`install.sh` 会把
  `Makefile`、`Dockerfile`、`build.sh`、`README-devcontainer.md`、
  `.dockerignore`、`.gitignore`、`docker-compose.yml` 安装到该根目录
  （**所有 make / build.sh 命令都在根目录执行**），原始副本与模板安装到
  `docs/devcontainer/`（仅用于把改坏的根目录文件复制回去重置），bundle 产物
  放在根目录的 `dist/` 下。根目录已有同名文件（如你自己的 Makefile/Dockerfile）
  时安装会终止，不会覆盖。

## 触发构建

1. 进入 Fork 后的仓库，点击 **Actions** → 左侧选择 **Build DevContainer** →
   **Run workflow**。
2. 填写参数后运行。运行完成后在 **Summary** 底部 **Artifacts** 下载唯一产物
   `<image_prefix>_devcontainer_<架构>_<时间戳>.zip`（架构为 `amd64` / `arm64`，
   时间戳为 UTC+8），zip 解压得到四个文件：
   - `devcontainer-docker-images_<架构>_<时间戳>.tgz`：Docker Images 镜像归档
     （gzip 压缩的 `docker save` 输出，可直接 `docker load`）
   - `devcontainer-src_<架构>_<时间戳>.tgz`：运行时源码包
   - `install.sh`：安装脚本（与 src tgz 放同一目录使用）
   - `readme.html`：简易安装说明（把 zip 放到项目根目录 `dist/` 解压后
     `bash install.sh ../`；加 `--load` 可在安装开始前自动 `docker load`
     镜像归档）

   > Artifacts 只能是 zip 封装，工作流已设置 `compression-level: 0`（仅存储、
   > 不再二次压缩），解压 zip 即得到产物文件。"Bundle" 专指这个外部 zip 产物；
   > 内部用于 `docker load` 的 tgz 文件名为 "Docker Images"。
3. Summary 页同时给出本次构建的完整摘要与内网使用步骤。

### 触发参数（Inputs）

| 参数 | 类型 | 取值 / 格式 | 默认值 | 说明 |
|------|------|------------|--------|------|
| `platform` | choice | `linux-amd64` / `linux-arm64` | `linux-amd64` | 目标平台（需与内网机器 CPU 架构一致） |
| `python_version` | choice | `3.10` / `3.11` / `3.12` / `3.13` | `3.13` | 容器内 Python 版本 |
| `pip_packages` | string | 用 `$` 分隔，如 `numpy$pandas$requests` | 空 | 附加 pip 包（空 = 无附加依赖） |
| `apt_packages` | string | 空格分隔，如 `git vim curl` | 空 | 镜像内安装的 APT 工具 |
| `custom_install_cmd` | string | shell 命令 | 空 | 个性化安装命令，在镜像内 `RUN` 执行 |
| `enable_lucide` | boolean | — | `false` | 预装 lucide（SVG 图标库，Django/Jinja 模板渲染 lucide.dev 图标，pip 纯 Python 包） |
| `enable_oracle_instantclient` | choice | `none` / `runtime_deps_only` / `full` | `none` | Oracle Instant Client 19 安装模式：`none` 不安装；`runtime_deps_only` 只装运行依赖（`libaio1`/`libnsl2`）+ `oracledb==2.5.1` + 环境变量，客户端本体由 compose 从宿主机只读挂载到 `/opt/oracle/instantclient19`（多容器共用）；`full` 完整安装，构建期从 Oracle 官方直链下载 Basic 包解压进镜像（客户端随镜像分发，无需挂载） |
| `preset_envs` | string | 用单个 `》` 分隔，如 `DB_HOST=10.0.0.1》DB_PORT=1521` | 空 | 预设环境变量，注入 app 与 dev 服务（同名值覆盖 Oracle 默认变量；值按字面量处理，`$` 无需转义） |
| `enable_node` | boolean | — | `false` | 镜像内置 Node.js 24 + npm，用于前端离线开发（vite / webpack / vue / react） |
| `npm_packages` | string | 用 `$` 分隔，如 `vite$webpack$webpack-cli$vue$react` | 空 | 构建期全局安装的 npm 包（需要 `enable_node=true`；构建机联网安装，内网容器可直接使用） |
| `npm_packages_dir` | string | 相对/绝对路径 | `packages` | **Npm Download 产物所在目录**：把该工作流产出的 `packages/` 内容（`*.tgz` + `package.json`）放这里，compose 会把它只读挂载到容器 `/opt/npm-packages`，供 `make npm-install` 离线安装前端依赖。相对项目根或绝对路径（需 `enable_node=true`） |
| `sidecars` | string | 逗号/空格分隔，如 `nginx postgres` | 空 | 启用的外挂服务：`nginx`（8080:80）、`postgres`（postgres:16，数据卷 pgdata） |
| `app_depends_on` | string | 逗号/空格分隔，如 `nginx postgres` | 空 | app 服务 `depends_on` 的外挂服务（须在 `sidecars` 中同时启用） |
| `prod_command` | string | 命令行 | `python main.py` | prod 服务启动命令（同时写入镜像 CMD 与 compose 的 app 服务 `command`，安装后可直接改 compose 免重建） |
| `image_mode` | choice | `prod+dev` / `prod-only` / `dev-only` | `prod+dev` | `prod+dev`：同时构建 prod 与 dev 镜像；`prod-only`：只构建 prod；`dev-only`：只构建 dev 镜像并用于部署（镜像归档只含该镜像） |
| `image_prefix` | string | 小写字母/数字/`._-` | `mydevc1` | 镜像名前缀：prod 镜像为 `<prefix>:<tag>`，dev 镜像为 `<prefix>-dev:<tag>`；仅 dev 镜像模式只有 `<prefix>-dev:<tag>`。Artifact 名也使用该前缀（`<prefix>_devcontainer_<架构>_<时间戳>`，架构为 `amd64` / `arm64`） |
| `image_tag` | choice | `latest` / `timestamp` | `latest` | 镜像 TAG：`latest`（每次构建覆盖同名镜像）或 `timestamp`（构建时间戳，UTC+8，如 `20260101-120000`） |
| `app_source_dir` | string | 相对/绝对路径 | `.` | 挂载进容器 `/app` 的目录：`.` = 整个项目根目录；相对路径 = 项目根目录下的子目录（如 monorepo 中的应用子目录，可避免 ruff/pytest 扫到无关源码）；也支持绝对路径。项目根目录由 `install.sh` 安装时传入（不支持 `~`） |
| `app_port` | string | `host:container` 或单个端口号 | `3000:3000` | 应用端口映射：写成 `3000:3000` 表示宿主机 3000 → 容器 3000；只写 `3000` 等价于 `3000:3000`；空 = 不映射。启用 nginx 时 app 仅容器网络暴露容器端口，由 nginx 反代 |
| `env_file` | string | 逗号/空格分隔 | 空 | **注入 app 服务的环境变量文件**（等价 compose `env_file`）：文件中的变量会进入 app 容器，常用于放置数据库密码、密钥等不适合写进 `preset_envs` 的配置。相对项目根或绝对路径（如 `.env`） |
| `selinux_relabel` | boolean | — | `false` | 给 `/app` 挂载追加 `:z` 重打标签（SELinux Enforcing 主机需要） |

> **固定值（不再作为输入暴露）**：`glibc_version=2.28`（manylinux 标签）、
> `pip_mirror=Official (pypi.org)`、Node.js `24`、
> `npm_registry=Official (npmjs.org)`。

> **提示**：`pip_packages` 输入框无法换行，使用 `$` 分隔多个包，与
> `pip_download.yml` 的约定一致。

### 参数校验规则

以下情况会在构建开始前直接失败并给出清晰错误：

- `app_depends_on` 含 `nginx` 但 `sidecars` 未启用 nginx
- `app_depends_on` 含 `postgres` 但 `sidecars` 未启用 postgres
- `platform` / `python_version` / `image_tag` / `enable_oracle_instantclient` 不在取值范围内
- `image_prefix` 含非法字符（仅允许小写字母/数字/`.`/`_`/`-`）
- `prod_command` 无法解析为命令
- `app_port` 不是 1-65535 的端口号，或不是合法的 `host:container` 映射
- `app_source_dir` / `env_file` 使用 `~`（不会展开，请写绝对路径或相对路径）
- `preset_envs` 不是 `KEY=VALUE` 形式、变量名非法或重复
- `npm_packages` 非空但 `enable_node=false`；npm 包名非法（仅 `name` / `@scope/name`，可带 `@版本`）
- `npm_packages_dir` 含空白、`:`、`~` 等非法字符（仅允许字母/数字/`.`/`_`/`-`/`/`）

## 产物说明

唯一 Artifact 为 `<image_prefix>_devcontainer_<架构>_<yyyymmdd-HHMMSS>.zip`
（架构为 `amd64` / `arm64`，时间戳 UTC+8），
zip 内含以下四个文件（`compression-level: 0`，仅存储不再二次压缩）：

| 文件 | 用途 |
|------|------|
| `devcontainer-docker-images_<架构>_<时间戳>.tgz` | Docker Images 镜像归档（`docker load` 用） |
| `devcontainer-src_<架构>_<时间戳>.tgz` | 运行时源码包 |
| `install.sh` | 安装脚本（与 src tgz 放同一目录） |
| `readme.html` | 简易安装说明（建议把 zip 放到项目根目录 `dist/` 下解压后 `bash install.sh ../`；`--load` 可自动导入镜像） |

### devcontainer-docker-images_<架构>_<yyyymmdd-HHMMSS>.tgz

该文件是 `docker save` 输出经 gzip 压缩得到的镜像归档（prod、dev、nginx、postgres，
按本次参数），可直接 `docker load -i` 导入，无需再解一层 tar。`image_mode=dev-only`
时归档中只有一个 dev 镜像（外加按需启用的 nginx/postgres）。Summary 中同时给出
SHA256，便于校验传输完整性。

### devcontainer-src_<架构>_<yyyymmdd-HHMMSS>.tgz

解压后得到顶层目录 `devcontainer-src/`（正常使用无需手动解压，由 `install.sh`
完成）：

```
devcontainer-src/
├── Dockerfile                   # 多阶段 prod/dev；仅 dev 镜像模式下为单阶段 dev
│                                # （联网重建版；install.sh 会把 Dockerfile.addon 改名
│                                #  为 Dockerfile 安装到项目根目录，供离线补装用）
├── docker-compose.yml.tpl       # compose 模板（install.sh 原样复制到项目根为 docker-compose.yml）
├── Makefile                     # check/up/down/shell/lint/compile/test 等（复制到项目根）
├── main.py                      # 占位入口（应用根目录无 main.py 时由 install.sh 复制）
├── requirements.txt             # pip 包清单
├── Dockerfile.addon             # 离线补装：基于现有镜像把 wheels/ 打进 addon 镜像
│                                # （复制到项目根目录时改名为 Dockerfile）
├── build.sh                     # 离线补装入口（复制到项目根）
├── .dockerignore                # 复制/合并到项目根：构建上下文排除 dist/ wheels/ 等
├── .gitignore                   # 复制/合并到项目根：忽略离线产物与补装缓存
├── nginx/conf.d/                # 仅 sidecars 含 nginx 且指定 app_port 时生成反代配置
└── README.md                    # 快速上手说明（复制到项目根时改名为 README-devcontainer.md）
```

src 包内**只有 `docker-compose.yml.tpl` 模板，不包含渲染后的
`docker-compose.yaml`**；模板中的 `${SRC_ROOT:-./src/}` 与 `${SRC_ROOT_NAME:-app}`
两个环境变量由 docker compose 在运行时以 `:-` 默认值语法解析（默认
`./src/`、项目名后缀 `app`）。启用 Node 时模板还会内置
`${NPM_PACKAGES_DIR:-./packages}` 只读挂载；Oracle 为 `runtime_deps_only`
模式时另有 `${ORACLE_CLIENT_DIR:-/opt/oracle/instantclient19}` 只读挂载。
两者都可在运行时用环境变量覆盖（`full` 模式客户端已打进镜像，不生成挂载）。

`wheels/` 不再随源码包分发：所有 wheel 已在镜像构建阶段安装（云端构建经
BuildKit bind mount 参与，不落入任何镜像层），运行容器内没有 wheels；
离线补装见「离线补装 Python 包」。

### install.sh

安装脚本（与两个 tgz、readme.html 同在 bundle zip 内）。建议把 bundle zip 放到
项目根目录的 `dist/` 文件夹下解压后在 `dist/` 中执行：

```bash
bash install.sh ../              # 参数 = 你的项目根目录（dist/ 的上级）
bash install.sh --load ../       # 加 --load：安装开始前自动 docker load
                                 # 同目录的镜像归档 tgz（无需再手动 load）
```

脚本会（先做全部前置检查、再写盘，任一检查失败都不会留下半套安装）：

1. 在 `<项目根>/docs/devcontainer/` 下解压 src 包（目录已存在则报错，
   避免新旧版本混装；重新安装请先删除该目录）——这是**原始副本目录**，
   仅用于把改坏的根目录文件复制回去重置，不要在该目录下运行任何脚本；
2. 把包内 `docker-compose.yml.tpl` **原样复制**到项目根目录，命名为去掉
   `.tpl` 后缀的 `docker-compose.yml`（不做任何渲染；目标文件已存在则报错，
   避免覆盖你自己的 compose 配置）；
3. 把 `Makefile`、`build.sh`、`Dockerfile.addon`（改名 `Dockerfile`）、
   `README.md`（改名 `README-devcontainer.md`）复制到项目根目录——所有
   make / build.sh 命令此后都在项目根目录执行；目标文件已存在时报错终止，
   不会覆盖你自己的同名文件；
4. 把 `.dockerignore` 与 `.gitignore` 安装到项目根目录：文件不存在时创建；
   已存在时仅**追加缺失条目**（原有内容不动）；
5. 创建 `<项目根>/wheels/requirements.txt` 离线安装头（内容
   `--no-index --find-links=./`，仅缺失时创建）。pip 会把 `--find-links=./`
   解析到该文件所在目录：把 wheel 放进 `wheels/` 后，容器内外均可用
   `pip install -r wheels/requirements.txt <包名>` 离线安装；
6. 项目根目录没有 `main.py` 且启动命令为默认的 `python main.py` 时，复制
   占位 `main.py` 到项目根目录（不覆盖已有文件）；
7. 检测 compose 命令：有 `docker compose` 插件时不改 Makefile；只有
   `docker-compose` 时把 Makefile 的 `COMPOSE` 改为 `docker-compose`；
   两者都没有时保持默认，并在结束时给出红色警告。

> 为什么 compose 文件带 `.tpl` 后缀：避免被 docker compose 自动发现或被
> `-f` 误用，与项目根目录下用户自己的 compose 配置彻底隔离——compose 多
> 文件合并对 `ports` 等列表只做并集、无法通过 override 移除，`*.override.yaml`
> 自动合并也会产生同样问题。复制到项目根目录的 `docker-compose.yml` 是
> compose 实际使用的运行文件，可放心手工修改；`${SRC_ROOT:-./src/}` /
> `${SRC_ROOT_NAME:-app}` 也可在运行 `docker compose` 时用环境变量覆盖。

## 内网使用步骤

```bash
# 1. 下载唯一 Artifact <image_prefix>_devcontainer_<架构>_<时间戳>.zip，
#    放到你的项目根目录 dist/ 文件夹下（没有就新建），并在 dist/ 中解压：

# 2. 导入镜像 + 安装到项目根目录（均在 dist/ 中执行，参数 ../ 即项目根目录）
#    --load 会在安装开始前自动 docker load 同目录的镜像归档（一步到位）
bash install.sh --load ../
#    （等价的两步写法：
#      docker load -i devcontainer-docker-images_amd64_20260101-120000.tgz
#      bash install.sh ../）

# 3. 离线自检：镜像是否已导入、CPU 架构是否匹配（在项目根目录执行）
cd ..
make check

# 4. 开发阶段（均在项目根目录执行）
make shell      # 进入 dev 容器交互式 bash（含 ruff/pytest 等）
make lint       # ruff check .
make compile    # python -m compileall -q .
make test       # pytest -q

# 5. 运行阶段（--no-build，不会联网构建/拉取）
make up
make logs       # 跟随日志
make down       # 停止
```

## 离线补装 Python 包（build.sh + Dockerfile.addon）

构建时漏了的包、后来才需要的包，都可以在**不联网**的内网机器上补进镜像，
无需重新跑一次 Action：

```bash
# 1. 联网机器：下载缺的包为 wheel（仓库 scripts/pip/ 即本工具，
#    或直接使用仓库的 Pip Download Action）
python scripts/pip/pip_download.py <包名...> -d /tmp/wheels
#    产物含 *.whl 和带 --no-index 头的 requirements.txt
#    把 /tmp/wheels 整个目录拷回内网项目根目录 wheels/

# 2. 内网机器，在项目根目录执行：
bash build.sh [新TAG后缀]     # 后缀默认 addon-<时间戳>；prod 新镜像 <前缀>:<后缀>，
                             # dev 新镜像 <前缀>-dev:<后缀>

# 3. 按输出的 sed 命令把项目根目录的 docker-compose.yml 切换到新镜像（如
#    devcontainer-dev:addon-20260101-120000），然后：
make up && make logs
```

工作原理与说明：

- `Dockerfile.addon`（install.sh 复制到项目根目录时改名为 `Dockerfile`）
  按构建模式对每个应用镜像生成一个阶段（prod+dev 模式分别基于 prod / dev
  镜像；仅 dev 镜像模式只有 dev），`build.sh` 逐个
  `docker build --target` 生成 addon 镜像：prod 为 `<前缀>:addon-<时间戳>`，
  dev 为 `<前缀>-dev:addon-<时间戳>`（如 `devcontainer:addon-20260101-120000` /
  `devcontainer-dev:addon-20260101-120000`，可传参自定义后缀）。
- wheel 通过临时构建上下文复制到镜像内 `/tmp/addon-wheels`，`pip install
  --no-index --find-links` 安装后**同一 RUN 层内删除**——不会增大最终镜像
  体积；已在基础镜像中安装的依赖 pip 自动跳过。
- `wheels/requirements.txt` 含真实包名（非 `--no-index --find-links=./`
  这类选项/注释/空行）时按清单安装（`--no-index` 头保证不联网）；只有
  离线安装头（install.sh 预置的初始状态）时，安装目录下全部 `*.whl`——
  只扔 wheel 进目录、不改 requirements 也能直接补装。
- 构建上下文是临时目录 `.addon-build`（只含 wheels），不会把整个项目目录
  发给 docker daemon。docker 只按**上下文根目录**查找 `.dockerignore`，因此
  项目根目录那份（排除 wheels/）不会作用于补装构建；build.sh 还会显式清理
  上下文内的任何 dockerignore（双保险），云端每次构建也在 Verify 步骤用
  mock docker 干跑回归测试断言这一点。构建结束临时目录自动清理。请勿在
  项目根目录直接 `docker build .`——那会把整个项目作为上下文，且 `wheels/`
  已被 .dockerignore 排除导致 COPY 失败。
- 回滚：重新 `docker load -i devcontainer-docker-images_<架构>_<时间戳>.tgz` 即可
  恢复原镜像。

## Makefile 目标

所有 make 命令在**项目根目录**执行（Makefile 由 install.sh 安装到项目根目录；
`docs/devcontainer/` 下的原始副本仅用于重置，不要在该目录执行 make）。

| 目标 | 说明 |
|------|------|
| `make help` | 列出所有目标（目标说明须写在 `## ` 双井号之后才会显示） |
| `make check` | **离线自检**：打印 docker 架构，确认 compose 文件存在、逐个确认本次镜像已导入（缺失时提示 `docker load`） |
| `make build` | `docker compose build`（**需联网**：发布包不含 wheels/，deps 从 apt/pip 源安装；离线机器勿用） |
| `make up` | `docker compose up -d --no-build`，后台启动 prod 服务（及已启用的外挂服务） |
| `make down` | 停止并移除容器与网络 |
| `make ps` | 查看容器状态 |
| `make logs` | 跟随查看日志 |
| `make shell` / `make dev` | 进入 dev 容器交互式 bash |
| `make lint` | ruff check . |
| `make compile` | python -m compileall -q . |
| `make test` | pytest -q |
| `make package-src` | 重新打包 `docs/devcontainer` 为 tgz（输出到 `dist/`，可配 install.sh 再次安装） |

> `shell/dev/lint/compile/test` 依赖 dev 镜像（`image_mode=prod+dev` 或
> `dev-only` 时才有），通过 compose 的 `dev` profile 激活，不影响
> `make up` 的运行行为。
>
> 容器默认以当前用户身份运行：Makefile 自动导出 `HOST_UID`/`HOST_GID`
> （`$(id -u)` / `$(id -g)`），避免挂载目录出现 root 属主文件。临时需要
> root 时：`make shell HOST_UID=0 HOST_GID=0`（命令行变量优先于默认值）。

## 给 AI Agent 的使用约定

安装到项目根的 `README-devcontainer.md`（bundle 内 src 包的 `README.md`）包含
面向 AI 编码 Agent 的约定，核心是：**Python / Node 运行环境只在容器内，
宿主机无需安装，也不要用宿主机的 `python` / `pip` / `pytest` / `npm`**。
所有命令都在项目根目录执行：

| 目的 | 推荐命令（prod+dev / dev-only） |
|------|------|
| 查看 Python 版本 | `docker compose run --rm dev python -V` |
| 执行 Python 脚本 | `docker compose run --rm dev python path/to/script.py` |
| 交互式 shell | `make shell` |
| 运行测试 | `make test`（单个文件：`docker compose run --rm dev pytest -q tests/test_x.py`） |
| 静态检查 / 编译检查 | `make lint` / `make compile` |
| 启动应用 / 查看日志 | `make up` / `make logs` |
| 前端离线依赖 | `make npm-install`（`enable_node=true` 时） |

- 容器把项目根目录挂载为 `/app`，容器内修改会直接写回宿主机。
- 首次使用先 `make check`；离线机器不要执行 `make build` / `docker compose build`。
- 缺 Python 包时不要在宿主机 `pip install`，走「离线补装 Python 包」流程。
- 仅 prod 镜像模式（`prod-only`）没有 ruff/pytest，一次性命令用
  `docker compose run --rm app python ...`；需要测试工具时重新构建并选择
  `prod+dev` 或 `dev-only`。

## 外挂服务

- **nginx**（`sidecars` 含 `nginx`）：`nginx:stable`，宿主机 `http://<host>:8080` →
  容器 80 端口。指定 `app_port` 时会生成 `nginx/conf.d/default.conf` 并挂载，
  自动反代到 `app:<容器端口>`（`app_port` 冒号后的端口）；未指定 `app_port`
  时只启动默认 nginx，需要自行提供配置文件。
- **postgres**（`sidecars` 含 `postgres`）：`postgres:16`，带 `pg_isready` 健康检查，
  仅容器网络内可达，连接串
  `postgres://postgres:postgres@postgres:5432/postgres`，数据持久化在 `pgdata`
  卷（`make down` 不删除数据卷）。
- `app_depends_on` 生成 compose 的 `depends_on`：nginx 用 `service_started`，
  postgres 用 `service_healthy`（等待健康检查通过，避免启动期连接被拒）。
- 所有服务均设置 `restart: unless-stopped` 与 `pull_policy: never`，离线环境
  不会尝试拉取镜像。

## Oracle Instant Client

`enable_oracle_instantclient` 是三选一模式：`none`（默认，不安装）、
`runtime_deps_only`、`full`。

### runtime_deps_only（客户端由宿主机挂载）

- 镜像内**只安装运行依赖**（`libaio1`、`libnsl2`）+ `oracledb==2.5.1`，
  并配置环境变量：
  `ORACLE_HOME=/opt/oracle/instantclient19`、
  `LD_LIBRARY_PATH=/opt/oracle/instantclient19`、`TNS_ADMIN=/app`、
  `PATH` 追加客户端目录。
- 客户端本体不下载、不打进镜像，而是由 `docker-compose.yml` 内置只读挂载：
  `${ORACLE_CLIENT_DIR:-/opt/oracle/instantclient19}:/opt/oracle/instantclient19:ro`
  ——同一台服务器上的多个容器共用同一份客户端，镜像体积也不再包含客户端。
- 内网准备步骤：
  1. 下载 Instant Client 19 Basic 包（x64 / arm64 与服务器一致）并解压，把
     其中的 `instantclient_19_19` 目录内容放到 `/opt/oracle/instantclient19`，
     确保 `/opt/oracle/instantclient19/libclntsh.so.19.1` 直接存在；
     官方直链目录
     `https://download.oracle.com/otn_software/linux/instantclient/1919000/`
     （x64：`instantclient-basic-linux.x64-19.19.0.0.0dbru.zip`，
     arm64：`instantclient-basic-linux.arm64-19.19.0.0.0dbru.zip`）；
  2. 客户端在其它目录（例如解压后就在 `/opt/oracle/instantclient_19_19`）：
     `export ORACLE_CLIENT_DIR=/opt/oracle/instantclient_19_19` 后再
     `make up`（无需重新构建镜像），或修改项目根 `docker-compose.yml` 中的
     默认值；
  3. 验证 Thick 模式加载：
     ```bash
     docker compose run --rm app python -c "import oracledb; oracledb.init_oracle_client(); print('OCI OK')"
     ```
     输出 `OCI OK` 即成功；报 `DPI-1047` / 找不到 `libclntsh.so` 说明宿主机
     目录为空或路径不对。
- `install.sh` 安装结束与 bundle 的 `readme.html` 都会打印以上提示。
- 挂载是只读的：升级客户端只需替换宿主机目录内容，再
  `make down && make up` 重启容器。

### full（客户端完整安装进镜像）

- 参考
  [`oracle2excel` 的 Dockerfile](https://github.com/wl-xiang/oracle2excel/blob/main/Dockerfile)：
  镜像内安装 `libaio1`、`libnsl2`、`wget`、`unzip`，并在**构建期**从 Oracle
  官方公开直链下载 Instant Client 19 Basic 包（按 BuildKit `TARGETARCH`
  选择 x64 / arm64），解压到 `/opt/oracle/instantclient19`，同时校验
  `libclntsh.so.19.1` 的 ELF 架构与目标平台一致。
- 环境变量与 `runtime_deps_only` 完全一致，`oracledb==2.5.1` 同样预装。
- 客户端随镜像分发，**compose 不再挂载客户端**，内网无需准备任何 Oracle 文件；
  代价是镜像体积增大，升级客户端需要重新构建镜像。
- 验证：
  ```bash
  docker compose run --rm app python -c "import oracledb; oracledb.init_oracle_client(); print('OCI OK')"
  ```

## 前端离线开发（Node.js / npm）

勾选 `enable_node` 后，镜像内置 Node.js 24 + npm（从官方
`node:24-slim-bookworm` 镜像复制，运行期无需联网），用于
vite / webpack / vue / react 等前端框架的离线开发。与 **Npm Download** 工作流
（仓库 `.github/workflows/npm_download.yml`）的集成方式：

1. 外网：运行 **Npm Download** 工作流，得到 `npm_packages` 产物（顶层
   `packages/`，含全部依赖的 `.tgz` 与离线安装清单）。
2. 内网：把产物中的 `packages/` 放到构建参数 `npm_packages_dir` 指定的目录
   （默认项目根目录 `packages/`）。`install.sh` 会提前创建该目录；compose 以
   只读卷挂载到容器 `/opt/npm-packages`：
   `${NPM_PACKAGES_DIR:-./packages}:/opt/npm-packages:ro`。
3. 离线安装依赖到 `/app`（项目根目录执行）：
   ```bash
   make npm-install
   # 等价于容器内：npm install --offline /opt/npm-packages/*.tgz
   ```
4. 开发调试（二选一）：
   - 推荐：构建参数 `prod_command` 设为 `npm run dev -- --host 0.0.0.0`，
     `app_port` 设为前端端口映射（vite `5173:5173` / webpack `8080:8080`），
     `make up` 即带宿主机端口映射；源码经 `/app` 挂载，支持热更新；
   - 临时：在项目根执行
     `docker compose run --rm -p 5173:5173 dev npm run dev -- --host 0.0.0.0`
     （`make shell` 进入容器手动启动时需自行发布端口）。
- 离线包目录不在项目根时：`export NPM_PACKAGES_DIR=/data/packages`，或
  `make npm-install NPM_PACKAGES_DIR=/data/packages`（Makefile 已导出该变量，
  compose 会自动使用）。
- `npm_packages`（`$` 分隔，如 `vite$webpack$webpack-cli$vue$react`）会在
  构建期以固定的官方源（`https://registry.npmjs.org`）全局安装，内网容器内
  可直接使用这些 CLI（如 `vite --version`）；`make check` 会检查离线包目录
  是否存在 `.tgz`。
- `make npm-install` 需要 dev 镜像（`image_mode=prod+dev` 或
  `dev-only`），与 `make shell` 一致。

## 设计说明

### install.sh 与 compose 模板（.tpl）

- src 包内的 compose 文件名为 `docker-compose.yml.tpl`：`.tpl` 后缀保证它
  不会被 docker compose 自动发现，也不会被 `-f` 误用。compose 多文件合并对
  `ports` 等列表只做**并集**（无法通过 override 移除），`*.override.yaml`
  自动合并也会产生同样的问题——隔离后，devcontainer 的 compose 与应用根目录
  下用户自己的 compose 配置互不影响。
- `install.sh <项目根目录>`（推荐在项目根目录 `dist/` 中以 `bash install.sh ../`
  调用）把 src 包解压到 `<项目根>/docs/devcontainer/`，并把模板**原样复制**
  到项目根目录为 `docker-compose.yml`（仅去掉 `.tpl` 后缀，不做渲染）。
  模板中的两个环境变量以 compose 的 `:-` 默认值语法书写、运行时解析：
  `${SRC_ROOT:-./src/}` 应用根目录（默认 `./src/` = docker-compose.yml 所在
  项目根目录下的 src 子目录，挂载为容器 `/app`）、`${SRC_ROOT_NAME:-app}` compose 项目名后缀
  （项目名 = `<image_prefix>-<SRC_ROOT_NAME>`，避免多应用冲突）。需要时可在
  运行 compose 前设置环境变量覆盖（如 `SRC_ROOT=/data/other`）。
- 项目根目录的 `docker-compose.yml` 是用户可改的副本，`.tpl` 保持原样；
  `docker-compose.yml` 已存在时 install.sh 报错退出，不会覆盖。
- 应用根目录没有 `main.py` 且启动命令为默认值时，install.sh 复制占位
  `main.py` 到项目根目录，保证 `make up` 开箱即用（否则 `python main.py`
  立即退出，配合 `restart: unless-stopped` 会无限重启）。

### 根目录操作文件与原始副本（docs/devcontainer）

- install.sh 把 `Makefile` / `build.sh` / `Dockerfile.addon`（改名
  `Dockerfile`）/ `README.md`（改名 `README-devcontainer.md`）从
  `docs/devcontainer/` 复制到**项目根目录**：所有 make / build.sh 命令都在
  项目根目录执行，无需 cd 进子目录。这些脚本的全部路径按**执行时的工作目录
  （pwd）解析**，因此 docs/devcontainer 下的原始副本与根目录文件内容完全
  一致、可互相替换——根目录文件被改坏时，直接
  `cp docs/devcontainer/Makefile .` 即可重置。
- `docs/devcontainer/` 只是原始副本 + 模板的存放处（compose `.tpl`、nginx
  配置、README 原件等），**不要在该目录下运行任何脚本**（脚本按 pwd 解析
  路径，在错误目录执行只会得到清晰报错）。根目录同名文件已存在时 install.sh
  报错终止，绝不覆盖用户自己的文件。
- `Dockerfile.addon` 在根目录改名为 `Dockerfile`，供 build.sh 以
  `-f Dockerfile` 引用；compose 的 `build.dockerfile` 则指向
  `docs/devcontainer/Dockerfile`（联网重建版，`make build` 需外网），二者
  各司其职、互不覆盖（README.md → README-devcontainer.md 同理避免与项目
  自身的 README.md 冲突）。
- `.dockerignore` / `.gitignore` 安装到项目根目录（已存在时仅追加缺失
  条目）：`dist/`（bundle 产物）、`wheels/`（离线补装 wheel）、
  `.addon-build/`（补装构建临时目录）等不进入 docker 构建上下文/不误提交
  git。wheels 构建时已装进镜像（不落层、不进入运行容器），无需随上下文或
  git 分发。
- install.sh 还会创建 `<项目根>/wheels/requirements.txt` 离线安装头
  （`--no-index --find-links=./`）：pip 对 requirements 文件内的相对
  `--find-links` 按**该文件所在目录**解析，因此把 wheel 放进 `wheels/` 后，
  在任意目录执行 `pip install -r wheels/requirements.txt <包名>` 都能离线
  安装。Dockerfile.addon 安装时只有该文件含真实包名才按清单装，否则装目录
  下全部 `*.whl`——空清单不会静默装个寂寞。

### 容器用户（root 污染防护）

- compose 中 app/dev 服务均设置 `user: "${HOST_UID:-0}:${HOST_GID:-0}"`。
  Makefile 自动导出 `HOST_UID=$(id -u)` / `HOST_GID=$(id -g)`，容器默认以
  当前用户身份运行——否则 ruff（`.ruff_cache`）、pytest（`.pytest_cache`）、
  compileall（`__pycache__`）及应用写入的文件都会变成 root 属主，普通用户
  无法删除。
- 需要 root（容器内 `pip install` 到系统目录）时：
  `make shell HOST_UID=0 HOST_GID=0`。
- 已知无害副作用：非 root UID 在容器内没有 passwd 条目，bash 提示
  `I have no name!`；容器端口小于 1024（`app_port` 冒号后的端口）时非 root 无法绑定低端口。

### glibc 语义

- 基础镜像固定为 `python:<version>-slim-bookworm`（glibc 2.36），保证任何
  manylinux ≤ 2.34 标签的 wheel 都可运行。
- `glibc_version` 固定为 `2.28`（不再作为输入）：仅控制 **pip download 阶段
  选用的 manylinux 标签**，下载时会请求该 glibc 及其以下的所有 manylinux 标签
  （含 manylinux2014 别名），即「兼容目标 glibc」的 wheel 集合。
- 之所以传多个 `--platform`：pip（>= 25）对显式 `--platform` 不再做低版本 glibc
  标签展开，只传 `manylinux_2_28` 会漏掉仅带 `manylinux_2_17/manylinux2014`
  复合标签的 wheel（如 ruff）。

### prod / dev 镜像

- 单个 `Dockerfile` 多阶段构建：`prod` 只含运行时；`dev` 阶段 `FROM prod`
  追加 git/curl/vim/make 与 ruff/pytest/pytest-cov（wheel 在构建阶段随
  `wheels/` 离线安装）。
- 镜像命名：prod 为 `<前缀>:<TAG>`，dev 为 `<前缀>-dev:<TAG>`。如
  `devcontainer:latest` / `devcontainer-dev:latest`（`image_tag=latest`，默认，
  每次构建覆盖）或 `devcontainer:20260101-120000` /
  `devcontainer-dev:20260101-120000`（`image_tag=timestamp`）。
- 镜像瘦身：基础镜像固定 slim-bookworm；apt 安装后同层执行 `apt-get clean` 并
  清理 lists/archives；pip 统一使用 `--no-compile`（不生成 `.pyc`，配合
  `PYTHONDONTWRITEBYTECODE=1`）；Node.js 只复制 node/npm 并删除 npm 自带文档；
  Oracle `full` 模式的 `wget`/`unzip` 只用于构建期下载，安装、解压与
  `apt-get purge --auto-remove` 在同一层完成，不残留在运行时镜像中。
- 启动方式显式写入 compose：`docker-compose.yml` 的 app 服务固定写入
  `entrypoint: []`（清空镜像 ENTRYPOINT）与 `command`（默认构建参数
  `prod_command`），直接改这两行即可调整启动命令，无需重建镜像。要用自定义
  启动脚本时，按 compose 文件内注释在 app 的 `volumes` 下追加脚本挂载并把
  `entrypoint` 改为 `["/bin/bash", "/opt/my-start.sh"]`、`command` 清空为
  `[]`（否则镜像 CMD 会被追加为脚本参数）。镜像本身仍用 `CMD` 承载默认命令，
  `docker compose run --rm app <命令>` 不受影响；`make shell` 通过 dev 镜像的
  `CMD ["bash"]` 进入交互终端，互不干扰。
- `image_mode=dev-only` 时不再生成两个镜像：Dockerfile 只有单阶段 `dev`，
  compose 的 app 服务直接引用该 dev 镜像，启动命令同样由 compose 的
  `command` 显式承载（镜像 CMD 为 bash），`make up` 与
  `make shell/lint/test` 共用同一个镜像；镜像归档中也只保存这一个镜像。
- `wheels/` 仅在构建时经 BuildKit bind mount 参与安装，不复制进任何镜像层
  （构建上下文中的 `wheels/` 不会进入发布包，运行容器内也没有 wheels）；
  内网补装新包走 `build.sh`（见「离线补装 Python 包」）。

### 依赖下载

- 复用 `pip download --only-binary=:all:` 快速失败策略：无 wheel 的源码包
  会直接报错，此时请改用 `custom_install_cmd` 预编译，或反馈调整参数。
- dev 工具（ruff/pytest/pytest-cov）的 wheel 会在构建 dev 镜像时一并下载。
- **业务依赖必须在 `pip_packages` 中显式列出**（构建端拿不到业务代码，无法
  自动解析业务 `requirements.txt`）。漏装会在离线运行时表现为
  `ModuleNotFoundError`；此时可用 `build.sh` 离线补装（见「离线补装
  Python 包」），或临时把 wheel 放入项目根 `wheels/` 后在容器内
  `pip install -r wheels/requirements.txt <pkg>`（仅当前容器生效，
  重建容器即失效）。

## FAQ

**Q: 为什么内网 `make up` 报错找不到镜像 / 尝试联网构建？**
先执行 `docker load -i devcontainer-docker-images_<架构>_<时间戳>.tgz` 导入镜像，再在
`docs/devcontainer` 原始副本所在的项目根目录执行 `make check` 确认所有镜像存在；`make up` 使用
`--no-build`，compose 中也设置了 `pull_policy: never`，不会联网。若仍失败，
说明镜像 TAG 与 compose 中不一致，请确认使用同一次构建的镜像归档与 src。

**Q: `docker load` 成功但容器起不来，日志报 `exec format error`？**
构建平台与服务器 CPU 架构不一致（例如构建时选了 `linux-arm64`，服务器是 x86）。
用 `uname -m` / `docker version` 确认后，按服务器架构重新构建。

**Q: 传输后 `docker load` 报 `unexpected EOF` / 校验不符？**
镜像归档通常几百 MB 到 1 GB+，传输中断很常见。对比 Summary 中的 SHA256：
`sha256sum devcontainer-docker-images_<架构>_<时间戳>.tgz`，不一致就重新传输。

**Q: `docker load` 磁盘空间不足？**
导入过程需要约 2 倍镜像体积的临时空间（`docker info` 查看 Docker Root Dir 所在分区）。

**Q: 业务项目里会被放进哪些 devcontainer 文件？**
项目根目录：`Makefile`、`Dockerfile`、`build.sh`、`README-devcontainer.md`、
`.dockerignore`、`.gitignore`（后两者已存在时只追加条目）、`docker-compose.yml`
（install.sh 从模板复制而来；以上文件已存在同名时安装报错退出，不会覆盖）、
`wheels/requirements.txt`（离线安装头，缺失时才创建），以及应用根目录没有
`main.py` 时复制的占位 `main.py`。`docs/devcontainer/` 一个目录存放原始副本
与模板。其余业务文件一律不动，也不会与业务自带的 `requirements.txt` /
`README.md` 冲突（README 改名 README-devcontainer.md，requirements 在
docs/devcontainer/ 内）。

**Q: 如何重新安装 / 更新到新构建的版本？**
删除旧的 `<应用根>/docs/devcontainer`、`<应用根>/docker-compose.yml`，以及
上次安装到根目录的 `Makefile` / `Dockerfile` / `build.sh` /
`README-devcontainer.md`（注意保留你手工修改过的配置），再用新的
`install.sh` + src tgz 重新安装（dist/ 内 `bash install.sh ../`）。
`install.sh` 遇到已存在的安装目录、compose 文件或根目录同名文件会直接报错，
避免新旧版本混装或覆盖你的配置。

**Q: `make up` 后容器一直重启（Restarting）？**
`python: can't open file '/app/main.py'` 类错误说明启动命令指向的入口不存在：
确认项目根目录（或 `app_source_dir` 指定的子目录）下有对应入口文件，或修改
项目根目录 `docker-compose.yml` 中 app 服务的 `entrypoint` / `command`
（启动方式已显式写入，无需重建镜像）。注意镜像 TAG 必须与本次导入
的镜像归档一致（先 `make check` 自检）。

**Q: 挂载目录里出现 root 属主文件 / 宿主机无法修改？**
默认不会：Makefile 自动导出 `HOST_UID`/`HOST_GID`（当前用户），容器以你的
身份运行。若你曾用 `HOST_UID=0` 运行产生了 root 文件，用
`sudo rm -rf <路径>` 清理，或 `sudo chown -R $(id -u):$(id -g) <路径>` 改回
属主。容器内需要 root 时：`make shell HOST_UID=0 HOST_GID=0`。

**Q: SELinux Enforcing 主机上容器读不到 `/app`？**
构建时把 `selinux_relabel` 设为 `true`（挂载追加 `:z`），或手动修改项目根
目录 `docker-compose.yml` 中 app/dev 服务的 `volumes`，在挂载路径末尾追加
`:z`。

**Q: 应用起来了但宿主机访问不到？**
构建时设置 `app_port`（`host:container` 端口映射，如 `3000:3000`），并确认应用
监听 `0.0.0.0` 而不是 `127.0.0.1`。启用 nginx 时宿主机访问 `:8080`，由 nginx
反代到 app 的容器端口。

**Q: 跨架构构建（amd64 Runner 构建 arm64 镜像）很慢？**
不会出现：`platform=linux-arm64` 时工作流自动切换到 ARM 原生 Runner
（`ubuntu-24.04-arm`），docker build 全程原生执行，无需 QEMU 模拟。
公共仓库该 Runner 免费；私有仓库按分钟计费（2026-01 起可用）。若你把
`runs-on` 改回 x86 Runner 又要构建 arm64，需自行恢复
`docker/setup-qemu-action` 步骤（模拟执行速度约为原生 1/5~1/10）。

**Q: 某个 pip 包下载失败（No matching distribution）？**
多为该包无目标平台的 wheel（只有 sdist）。改用 `custom_install_cmd` 预编译，
或换用 `platform`/`python_version` 组合。

**Q: 离线运行时报 `ModuleNotFoundError`，缺的包怎么补？**
两步：联网机器用 `scripts/pip/pip_download.py` 下载该包 wheel 拷到
`<应用根目录>/wheels/`，内网在项目根目录执行 `bash build.sh`
生成 addon 镜像并按提示切换 compose。详见「离线补装 Python 包」。

**Q: 如何使用私有 PyPI？**
第一版未内置私有源选项。可 Fork 后在 `scripts/devcontainer-builder/lib/params.py`
的 `PIP_MIRRORS` 中增加条目（含认证 URL），或经镜像反代公开化。

**Q: 镜像归档体积偏大？**
镜像归档含 prod+dev（或仅 dev）+外挂服务镜像，几百 MB 到 1GB+ 属正常。已内置的
瘦身措施：slim-bookworm 基础镜像、apt 同层清理、pip `--no-compile`、Node 文档
清理、Oracle `full` 模式构建工具同层 purge。进一步压缩可选：
`image_mode=prod-only`（少一个 dev 镜像）、`image_mode=dev-only`（只保留一个镜像）、
Oracle 用 `runtime_deps_only`（客户端不进镜像）、不启用 Node/Oracle 等可选组件；
dev 镜像与 prod 镜像共享层，归档中公共层只存一份。Summary 中记录了每次产物大小
作为基线。

**Q: 镜像里没有 Oracle Instant Client，容器报 `DPI-1047`？**
`runtime_deps_only` 模式按设计不把客户端放进镜像：确认宿主机已把 Instant
Client 19 解压到 `/opt/oracle/instantclient19`（或设置 `ORACLE_CLIENT_DIR` 指向
实际目录），并确认 `libclntsh.so.19.1` 存在、架构与服务器一致。
`docker compose config` 可查看实际挂载路径。若不想在宿主机准备客户端，构建时
改选 `full` 模式，客户端会直接打进镜像。验证命令见「Oracle Instant Client」一节。

**Q: 前端项目怎么离线 `npm install` / 启动 vite / webpack？**
构建时勾选 `enable_node`，把 Npm Download 产物 `packages/` 放到项目根目录
（或 `npm_packages_dir` 指定的目录），在项目根执行 `make npm-install`
（等价于 `npm install --offline /opt/npm-packages/*.tgz`），再 `make shell` 后
`npm run dev -- --host 0.0.0.0`。镜像内已内置 Node.js/npm，无需联网。

**Q: 内网 Docker / Compose 版本较老？**
建议 Docker >= 20.10（23+ 更稳妥，兼容 containerd image store 导出的归档）、
compose v2。生成的 compose 使用 `profiles`、`depends_on` 的 `condition`、
`pull_policy`（均需 compose v2）。若不支持，`make up` 仍可用（dev 服务会被忽略），
但 `make shell/lint/test` 需升级 compose 或改用
`docker run -it --rm -v $PWD:/app -w /app <dev镜像> bash`。
