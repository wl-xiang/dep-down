# Offline DevKit

跨平台的离线依赖与开发环境工具箱：在外网为内网/隔离网络下载 Python 与 npm 依赖包，并构建可直接带进内网运行的 Python 开发环境镜像（DevContainer）。

## 通过 GitHub Action 自动下载并打包

本仓库提供一个人工触发的 GitHub Actions 工作流 `.github/workflows/pip_download.yml`，你无需克隆仓库或安装环境，直接在 GitHub 网站上即可为指定平台/架构/Python 版本/glibc 下载 pip wheel 包，并打包成可下载的产物（artifact）。

### 使用方法（Fork 后用）

1. **Fork 本仓库** 到你自己的 GitHub 账号（工作流需要以你的身份在 Actions 中运行）。
2. 进入 Fork 后的仓库，点击顶部 **Actions** 标签。
3. 在左侧工作流列表中选择 **Pip Download**，点击 **Run workflow**。
4. 填写触发参数（见下表），点击 **Run workflow** 启动。
5. 运行完成后打开该次运行，在 **Summary** 底部的 **Artifacts** 区域下载 `wheels_<platform>_<arch>_py<version>.zip` 产物。
6. 解压产物后，在内网/目标机器上执行 `pip install -r requirements.txt` 即可离线安装全部依赖。

### 触发参数（Inputs）

| 参数 | 必填 | 取值 | 默认值 | 说明 |
|------|------|------|--------|------|
| `platform` | 是 | `linux` / `win` | `linux` | 目标平台 |
| `arch` | 是 | `x86_64` / `arm64` | `x86_64` | 目标架构 |
| `python_version` | 是 | `3.6`–`3.14` | `3.10` | 目标 Python 版本 |
| `glibc_version` | 是 | `2.17` / `2.28` / `2.34` | `2.28` | Linux 目标 glibc 版本（Windows 忽略），决定 manylinux 平台标签 |
| `pip_mirror` | 是 | `THU (tuna)` / `Aliyun` / `USTC` / `Official (pypi.org)` / `Other (custom URL)` | `THU (tuna)` | pip 镜像源 |
| `custom_mirror_url` | 否 | 任意 URL | 空 | 仅当 `pip_mirror` 为 `Other (custom URL)` 时必填 |
| `requirements` | 否 | 文本 | 空 | requirements.txt 内容；留空则使用仓库内的 `scripts/pip/requirements.txt` |

> **提示：`requirements` 输入框无法直接换行**，请使用 `$` 表示换行。例如输入
> `requests!=2.0.0$fastapi$oracledb` 会被解析为三行：
> 1. `requests!=2.0.0`
> 2. `fastapi`
> 3. `oracledb`

### 产物内容

下载产物 `wheels/` 目录包含所有 `.whl` 文件以及一个 `requirements.txt`，其首行为 `--no-index --find-links=./`，保证离线安装时不会连接网络：

```bash
pip install -r requirements.txt
```

### 校验机制

工作流内置以下检查，任一失败都会以错误退出：
- 解析镜像源：`Other (custom URL)` 但 `custom_mirror_url` 为空，或未知镜像值时报错。
- `requirements` 输入仅为空白时报错。
- 扫描 `pip_download.py` 的下载日志，发现 `ERROR` / `Error:` / `失败` 即判定失败。
- 校验 `wheels/` 下存在 `.whl` 文件，并校验 `wheels/requirements.txt` 首行正确。

## 通过 GitHub Action 构建离线 Python 开发环境镜像（Build DevContainer）

本仓库提供一个人工触发的工作流 `.github/workflows/build-devcontainer.yml`，在外网按参数（平台、Python 版本、pip 包、APT 工具、个性化安装命令、nginx/postgres 外挂服务等）构建 prod/dev 两个 Docker 镜像并打包。内网机器只需 Docker，通过 Volume 挂载源码 + docker compose 即可开发与运行，本机无需安装任何运行环境。

此外还支持：Oracle Instant Client 三选一模式（`none` / `runtime_deps_only` 只装依赖并由宿主机挂载客户端 / `full` 客户端完整打进镜像）；`》` 分隔的预设环境变量；以及 Node.js 24 / npm 前端离线开发（vite / webpack / vue / react），可直接挂载 Npm Download 工作流产出的 `packages/` 目录。

### 使用方法（Fork 后用）

1. Fork 本仓库，进入 **Actions** → **Build DevContainer** → **Run workflow**。
2. 填写参数（完整参数表见 [docs/offline-devcontainer.md](docs/offline-devcontainer.md)）。
3. 运行完成后，在 **Summary** 底部下载唯一产物 `<镜像前缀>_devcontainer_<架构>_<时间戳>.zip`
   （架构为 `amd64` / `arm64`，时间戳为 UTC+8），解压得到五个文件：
   - `devcontainer-docker-images_<架构>_<时间戳>.tgz`：Docker Images 镜像归档（gzip 压缩的 `docker save` 归档，可直接 `docker load`）
   - `devcontainer-src_<架构>_<时间戳>.tgz`：运行时源码包（包含 Dockerfile、compose 模板、Makefile、requirements.txt 等）
   - `install.sh`：安装脚本（与 src tgz 放同一目录）
   - `readme.html`：图文安装说明
   - `workflow-params.json`：本次运行的 workflow 输入参数快照（minimal/normal/full 三层，仅供追溯，install.sh 不安装它）
   > Artifacts 下载得到的是 zip 封装（已设为不压缩，仅存储），解压即得上述文件。
4. Summary 页同时给出构建摘要（参数、镜像清单、产物大小）与内网使用步骤。

### 内网使用

```bash
# 唯一产物解压后，五个文件放到同一目录：
docker load -i devcontainer-docker-images_<arch>_<ts>.tgz   # 镜像归档可直接导入
bash install.sh ~/apps/myapp1                         # 安装到应用根目录 docs/devcontainer/（compose 文件复制到项目根）
cd ~/apps/myapp1                                     # 所有 make 命令都在项目根目录执行
make check      # 离线自检镜像/架构
make shell      # dev 容器交互 bash（ruff/pytest 已内置）
make lint && make compile && make test
make up         # docker compose up -d --no-build，运行 python main.py
```

> 参数校验（如依赖未启用的外挂服务）、多平台/多 glibc 组合、镜像命名与产物规范等说明详见 [docs/offline-devcontainer.md](docs/offline-devcontainer.md)。

> 安装到项目根的 `README-devcontainer.md` 包含面向 AI Agent 的使用约定：Python/Node 命令一律在容器内执行，不依赖宿主机的本地运行环境（如 Python）。

## 通过 GitHub Action 下载并打包 npm 包

本仓库另提供一个人工触发的 GitHub Actions 工作流 `.github/workflows/npm_download.yml`，无需克隆仓库或安装环境，直接在 GitHub 网站上即可把指定 npm 包（含全部子依赖）下载并打包成可下载的产物（artifact）。

### 使用方法（Fork 后用）

1. **Fork 本仓库** 到你自己的 GitHub 账号（工作流需要以你的身份在 Actions 中运行）。
2. 进入 Fork 后的仓库，点击顶部 **Actions** 标签。
3. 在左侧工作流列表中选择 **Npm Download**，点击 **Run workflow**。
4. 填写触发参数（见下表），点击 **Run workflow** 启动。
5. 运行完成后打开该次运行，在 **Summary** 底部的 **Artifacts** 区域下载 `npm_packages` 产物。
6. 解压产物后得到一个顶层 `packages/` 文件夹（所有内容都在其中，不会散落到当前目录）。在内网机器上进入该目录执行 `npm install --offline` 即可完全离线安装（详见下方“内网安装”）。

### 触发参数（Inputs）

| 参数 | 必填 | 取值 | 默认值 | 说明 |
|------|------|------|--------|------|
| `packages` | 否 | 文本 | 空 | 包列表；一行一个包名，用 `$` 表示换行。留空则使用 `source` 选中的仓库文件 |
| `source` | 是 | `packages.txt` / `package.json` | `packages.txt` | 当 `packages` 留空时使用的仓库文件 |
| `registry` | 是 | `npmmirror (taobao)` / `Tencent` / `Huawei` / `THU (tuna)` / `USTC` / `Official (npmjs.org)` / `Other (custom URL)` | `npmmirror (taobao)` | npm 镜像源 |
| `custom_registry_url` | 否 | 任意 URL | 空 | 仅当 `registry` 为 `Other (custom URL)` 时必填 |
| `node_version` | 是 | `18` / `20` / `22` / `24` | `20` | 运行 npo 的 Node.js 版本 |

> **提示：`packages` 输入框无法直接换行**，请使用 `$` 表示换行。例如输入 `vue$axios$react`
> 会被解析为三行 `vue`、`axios`、`react`。当同时填写了 `packages` 与选择了 `source` 时，以 `packages` 为准。

### 产物内容

产物 `npm_packages` 解压后为顶层 `packages/` 文件夹（不会散落到当前目录），其中包含：
- 所有依赖的 `.tgz` 离线包（含全部子依赖）；
- 一个 `package.json`：把每个依赖都声明为本地 tarball（`file:./xxx.tgz`）的离线安装清单，在 `packages/` 内执行 `npm install --offline` 时 npm 只读取磁盘上的 tarball，不访问任何 registry；
- 一个 `README.md`：包含包列表、离线安装说明，以及发布到本地 Verdaccio 的命令。

### 发布到本地 Verdaccio

`packages/package.json` 中 `private` 为 `false`，因此可直接发布到私有 registry：

```bash
cd packages
npm login --registry http://localhost:4873
npm publish --registry http://localhost:4873
```

内网机器随后配置 registry 即可安装：

```bash
npm config set registry http://<verdaccio-host>:4873
npm install npm-offline-packages
```

### 校验机制

工作流内置以下检查，任一失败都会以错误退出：
- 解析镜像源：`Other (custom URL)` 但 `custom_registry_url` 为空，或未知镜像值时报错。
- `packages` 输入仅为空白时报错。
- 扫描 `npo_fetch.py` 的下载日志，发现 `ERROR` / `Error:` / `下载失败` 即判定失败。
- 校验 `packages/` 下存在 `.tgz` 文件，且存在 `packages/package.json`。
- 基于下载到的全部 `.tgz` 生成 `packages/package.json` 离线安装清单（每个依赖为 `file:./...`）和 `packages/README.md` 使用说明，并将产物归档为顶层 `packages/` 文件夹。

## 通过 GitHub Action 清理工作流运行历史

本仓库提供一个人工触发的工作流 `.github/workflows/cleanup-run-history.yml`，用于按规则清理本仓库的 GitHub Actions 运行历史（删除整条 run，含日志与 Artifact），避免历史记录与存储无限增长。

### 使用方法

1. 进入 **Actions** → **Clean Workflow Run History** → **Run workflow**。
2. 选择清理依据与保留范围，保持默认的预演模式（`dry_run=true`）运行一次，确认 Summary 中列出的待删记录符合预期。
3. 再次运行并将 `dry_run` 设为 `false`，真正执行删除。

### 触发参数（Inputs）

| 参数 | 必填 | 取值 | 默认值 | 说明 |
|------|------|------|--------|------|
| `clean_by` | 是 | `num` / `date` | `num` | 清理依据：按保留条数或按保留天数 |
| `keep_count` | 否 | 正整数 | `10` | `clean_by=num` 时保留最近 N 条运行记录 |
| `keep_days` | 否 | 正整数 | `30` | `clean_by=date` 时保留最近 N 天内完成的记录 |
| `dry_run` | 否 | `true` / `false` | `true` | 预演模式：只打印待删记录，不真正删除 |

> 安全策略：永不删除排队/进行中（`queued` / `in_progress`）的记录，也不删除本工作流自身的运行记录；删除操作需要 `actions: write` 权限。

## 功能特性

### Python 包下载 (scripts/pip/pip_download.py)
- 支持多平台：Linux（manylinux_2_17 / 2_28 / 2_34，由 glibc 版本决定）和 Windows
- 支持多架构：x86_64/amd64、arm64/aarch64
- 支持多 Python 版本：3.6–3.14
- 自动平台标签映射
- 支持从 requirements.txt 或直接指定包名下载
- 自动打包功能

### npm 包下载 (scripts/npm/npo_fetch.py)
- 支持从 package.json 或 packages.txt 下载
- 使用 npm-offline-packager (npo) 工具
- 自动基于 packages.txt 生成 package.json（使用 jinja2 模板）
- 自动打包功能

## 环境要求

### Python
- Python 3.6+
- click
- jinja2 (用于 npo_fetch.py)

### npm
- Node.js 18+（GitHub Actions 可选 18 / 20 / 22 / 24）
- npm 9+
- npm-offline-packager (全局安装)

## 安装依赖

### Python 依赖
```bash
pip install click jinja2
```

### npm 依赖
```bash
npm install -g npm-offline-packager
```

或使用提供的脚本：
```bash
# Linux/Mac
./scripts/npm/npo_setup.sh

# Windows (Git Bash)
./scripts/npm/npo_setup.sh
```

## 快速开始

### Python 包下载

#### 基本用法
```bash
# 使用默认配置
python scripts/pip/pip_download.py

# 指定 Python 版本
python scripts/pip/pip_download.py -v 311

# 指定平台和架构
python scripts/pip/pip_download.py -p linux -a arm64

# 指定 Linux 目标的 glibc 版本（决定 manylinux 标签）
python scripts/pip/pip_download.py -g 2.28

# 启用打包
python scripts/pip/pip_download.py --need-pack

# 直接下载指定包
python scripts/pip/pip_download.py requests flask
```

#### 完整参数
```
Options:
  -p, --platform TEXT       目标平台 [linux, win], 可传入多个
  -a, --arch TEXT           目标架构 [x86_64, amd64, arm64, aarch64]
  -v, --python-version TEXT Python版本 [36, 38, 39, 310, 311, 312, 313, 314, ...]
  -g, --glibc TEXT          Linux 目标 glibc 版本 [2.17, 2.28, 2.34], 仅 Linux 生效
  -d TEXT                   下载目录, 默认值为 ./wheels
  -r TEXT                   依赖文件 [auto, requirements.txt, 自定义文件路径]
  -i, --index, --index-url TEXT
                            pip镜像源
  --need-pack / --no-need-pack
                            是否在下载完成后打包
  -h, --help                Show this message and exit.
```

### npm 包下载

#### 基本用法
```bash
# 使用 packages.txt
python scripts/npm/npo_fetch.py --pt packages.txt

# 使用 package.json
python scripts/npm/npo_fetch.py -p package.json

# 直接下载指定包
python scripts/npm/npo_fetch.py vue axios react

# 启用打包
python scripts/npm/npo_fetch.py --need-pack
```

#### 完整参数
```
Options:
  -r, --registry TEXT       npm镜像源
  -d, --destination TEXT    下载目录
  -p, --package-json TEXT   package.json文件路径
  --packages-txt, --pt TEXT
                            packages.txt文件路径（一行一个包名）
  --need-pack / --no-need-pack
                            是否在下载完成后打包
  -h, --help                Show this message and exit.
```

## 配置文件

### .env.pip (scripts/pip/.env.pip)
```env
PLATFORM=linux
ARCH=amd64
PYTHON_VERSION=312
D=./wheels
R=./requirements.txt
INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
NEED_PACK=true
```

> 如需指定 Linux 目标的 glibc 版本，可在 `.env.pip` 中增加 `GLIBC=2.28`（默认 `2.17`）。

### .env.npm (scripts/npm/.env.npm)
```env
REGISTRY=https://registry.npmmirror.com
D=./packages/
PT=./packages.txt
NEED_PACK=true
```

## 参数优先级

所有工具都遵循以下优先级（从低到高）：
1. 脚本默认值
2. 环境配置文件（.env.pip / .env.npm）
3. 系统环境变量（如 Actions 注入的 `PLATFORM`、`ARCH`、`PYTHON_VERSION` 等）
4. 命令行参数

## 清理工具

### 清除所有缓存
不带参数时清除 `wheels`、`packages`、`node_modules`、`tarballs`：

```bash
# Linux/Mac
./clear.sh

# Windows
clear.bat
```

### 清除指定目录
```bash
# Linux/Mac
./clear.sh wheels
./clear.sh packages node_modules

# Windows
clear.bat wheels
clear.bat packages node_modules
```

## 内网安装

### Python 包安装
1. 下载并解压 Action 产物 `wheels_<platform>_<arch>_py<version>.zip`（或本地打包的 `tarballs/wheels_${PLATFORM}_${ARCH}_py${VERSION}.tar.gz`），得到 `wheels/` 目录。
2. 进入 `wheels/` 目录：
```bash
cd wheels
```
3. 运行：
```bash
pip install -r requirements.txt
```

### npm 包安装
1. 下载并解压 Action 产物 `npm_packages`（或解压 `packages.tar.gz`），得到顶层 `packages/` 文件夹。
2. 进入 `packages/` 目录：
```bash
cd packages
```
3. 执行离线安装（npm 只读取本地 tarball，不访问任何网络）：
```bash
npm install --offline
```
4. 如希望直接安装进你自己的项目，则在项目根目录执行 `npm install ./packages/*.tgz --offline`（Windows PowerShell：`npm install (Get-ChildItem ./packages/*.tgz).FullName --offline`）。

> 若遇到 `npm error class extends value undefined is not a constructor or null`，通常说明离线机器上的 Node.js + npm 安装损坏或版本不匹配（npm 自身内置模块加载失败），此时任意 npm 命令都会报同样的错，与下载的包无关。请重装 Node.js 并清理残留的全局 npm 目录，确保 `node -v` 与 `npm -v` 版本匹配。

## 项目结构

```
.
├── .github/
│   └── workflows/
│       ├── pip_download.yml       # pip 离线下载 Action
│       ├── npm_download.yml       # npm 离线下载 Action
│       ├── build-devcontainer.yml # 离线开发环境镜像构建 Action
│       └── cleanup-run-history.yml # 工作流运行历史清理 Action
├── docs/                          # 文档目录
│   ├── npm-offline-package-guide.md
│   ├── offline-devcontainer.md    # 离线开发环境（build-devcontainer）使用手册
│   ├── platform-qa.md
│   ├── platforms.md
│   └── prompt.pip.txt
├── scripts/
│   ├── pip/                       # pip 相关文件与脚本
│   │   ├── .env.pip               # pip 配置
│   │   ├── pip_download.py        # Python 包下载工具
│   │   └── requirements.txt       # Python 依赖列表
│   ├── npm/                       # npm 相关文件与脚本
│   │   ├── .env.npm               # npm 配置
│   │   ├── README.template.md     # 产物 packages/README.md 的模板
│   │   ├── npm_install.sh         # npm 离线安装脚本
│   │   ├── npo_fetch.py           # npm 包下载工具 (Python 版本)
│   │   ├── npo_fetch.sh           # npm 包下载工具 (Shell 版本)
│   │   ├── npo_setup.sh           # npo 安装脚本
│   │   ├── package.json           # npm 项目配置
│   │   ├── package.json.j2        # jinja2 模板
│   │   └── packages.txt           # npm 包列表
│   └── devcontainer-builder/      # 离线开发环境镜像构建工具
│       ├── main.py                # 总入口
│       ├── README.md              # 构建工具说明（参数/模板/本地运行）
│       ├── lib/                   # params/render/pip/docker/package/summary
│       └── templates/             # Dockerfile/compose/Makefile 等模板
├── .gitignore
├── README.md
├── clear.bat                      # Windows 清理脚本
└── clear.sh                       # Linux/Mac 清理脚本
```

## 镜像源

### Python PyPI 镜像
- 清华大学：https://pypi.tuna.tsinghua.edu.cn/simple
- 阿里云：https://mirrors.aliyun.com/pypi/simple/
- 中科大：https://pypi.mirrors.ustc.edu.cn/simple/

### npm 镜像
- 淘宝：https://registry.npmmirror.com
- 腾讯云：https://mirrors.cloud.tencent.com/npm/
- 华为云：https://repo.huaweicloud.com/repository/npm/

## 许可证

MIT License
