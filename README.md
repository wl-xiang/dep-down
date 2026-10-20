# Offline Package Downloader

跨平台的 Python 和 npm 离线包下载工具，用于在外网设备上为内网系统下载依赖包。

## 通过 GitHub Action 自动下载并打包

本仓库提供一个人工触发的 GitHub Actions 工作流 `.github/workflows/pip_download.yml`，你无需克隆仓库或安装环境，直接在 GitHub 网站上即可为指定平台/架构/Python 版本下载 pip wheel 包，并打包成可下载的产物（artifact）。

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
- 一个 `package.json`：把每个依赖都声明为本地 tarball（`file:./xxx.tgz`）的离线安装清单，在 `packages/` 内执行 `npm install --offline` 时 npm 只读取磁盘上的 tarball，不访问任何 registry。

### 校验机制

工作流内置以下检查，任一失败都会以错误退出：
- 解析镜像源：`Other (custom URL)` 但 `custom_registry_url` 为空，或未知镜像值时报错。
- `packages` 输入仅为空白时报错。
- 扫描 `npo_fetch.py` 的下载日志，发现 `ERROR` / `Error:` / `下载失败` 即判定失败。
- 校验 `packages/` 下存在 `.tgz` 文件，且存在 `packages/package.json`。
- 基于下载到的全部 `.tgz` 生成 `packages/package.json` 离线安装清单（每个依赖为 `file:./...`），并将产物归档为顶层 `packages/` 文件夹。

## 功能特性

### Python 包下载 (scripts/pip/pip_download.py)
- 支持多平台：Linux (manylinux_2_17) 和 Windows
- 支持多架构：x86_64/amd64、arm64/aarch64
- 支持多 Python 版本：3.6、3.8-3.13 及后续版本
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
- Node.js 12+
- npm 6+
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
  -v, --python-version TEXT Python版本 [36, 38, 39, 310, 311, 312, 313, ...]
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
ARCH=x86_64
PYTHON_VERSION=312
D=./wheels
R=requirements.txt
INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
NEED_PACK=true
```

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
3. 命令行参数

## 清理工具

### 清除所有缓存
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
1. 解压 `wheels_${PLATFORM}_${ARCH}_py${VERSION}.tar.gz`
2. 进入解压后的目录
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

> 若遇到 `npm error class extends value undefined is not a constructor or null`：这不是离线包的问题，而是离线机器上 **npm 自身加载失败**——报错堆栈停在 npm 内置模块（如 `fs-minipass`、`minipass-collect` 的 `class extends ... Minipass`）的模块加载阶段，此时还没有碰到任何我们下载的 tarball，所以任何 `npm` 命令都会报同样的错。
>
> 常见原因有两个：① 同一台机器装了多套 Node（典型是 nvm-windows 与官方安装包 / winget / Volta 互相冲突）；② 升级 Node 后残留了旧版本的全局 npm 目录（部分升级导致 npm 内部依赖损坏）。
>
> 排查与修复：
> 1. 先确认：`node -v` 正常但 `npm -v` 也报同样的错，即可判定 npm 本身损坏。
> 2. 确认是否有多套 npm：Windows 执行 `where npm`，Linux/macOS 执行 `which -a npm`，出现多个路径就是冲突。
> 3. 卸载多余的 Node；删除残留的全局 npm 目录（如 `C:\Program Files\nodejs\node_modules\npm`、`%AppData%\npm`、`/usr/lib/node_modules/npm`、`~/.nvm/versions/node/*/lib/node_modules/npm`）。
> 4. 用官方安装包重装 Node（离线机需先拷入匹配版本的安装包），并且不要在版本不匹配的 Node 上执行 `npm install -g npm`。
> 5. 修复后重新验证：`node -v`、`npm -v` 均正常，再执行 `cd packages && npm install --offline`。

## 项目结构

```
.
├── .github/
│   └── workflows/
│       ├── pip_download.yml       # pip 离线下载 Action
│       └── npm_download.yml       # npm 离线下载 Action
├── docs/                          # 文档目录
│   ├── npm-offline-package-guide.md
│   ├── platform-qa.md
│   ├── platforms.md
│   └── prompt.pip.txt
├── scripts/
│   ├── pip/                       # pip 相关文件与脚本
│   │   ├── .env.pip               # pip 配置
│   │   ├── pip_download.py        # Python 包下载工具
│   │   └── requirements.txt       # Python 依赖列表
│   └── npm/                       # npm 相关文件与脚本
│       ├── .env.npm               # npm 配置
│       ├── npm_install.sh         # npm 离线安装脚本
│       ├── npo_fetch.py           # npm 包下载工具 (Python 版本)
│       ├── npo_fetch.sh           # npm 包下载工具 (Shell 版本)
│       ├── npo_setup.sh           # npo 安装脚本
│       ├── package.json           # npm 项目配置
│       ├── package.json.j2        # jinja2 模板
│       └── packages.txt           # npm 包列表
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
