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
| `requirements` | 否 | 文本 | 空 | requirements.txt 内容；留空则使用仓库内的 `requirements.txt` |

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

## 功能特性

### Python 包下载 (pip_download.py)
- 支持多平台：Linux (manylinux_2_17) 和 Windows
- 支持多架构：x86_64/amd64、arm64/aarch64
- 支持多 Python 版本：3.6、3.8-3.13 及后续版本
- 自动平台标签映射
- 支持从 requirements.txt 或直接指定包名下载
- 自动打包功能

### npm 包下载 (npo_fetch.py)
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
./npo_setup.sh

# Windows (Git Bash)
./npo_setup.sh
```

## 快速开始

### Python 包下载

#### 基本用法
```bash
# 使用默认配置
python pip_download.py

# 指定 Python 版本
python pip_download.py -v 311

# 指定平台和架构
python pip_download.py -p linux -a arm64

# 启用打包
python pip_download.py --need-pack

# 直接下载指定包
python pip_download.py requests flask
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
python npo_fetch.py --pt packages.txt

# 使用 package.json
python npo_fetch.py -p package.json

# 直接下载指定包
python npo_fetch.py vue axios react

# 启用打包
python npo_fetch.py --need-pack
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

### .env.pip (Python 配置)
```env
PLATFORM=linux
ARCH=x86_64
PYTHON_VERSION=312
D=./wheels
R=requirements.txt
INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
NEED_PACK=true
```

### .env.npm (npm 配置)
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
1. 解压 `packages.tar.gz`
2. 进入解压后的目录
3. 运行：
```bash
npm install --registry file://./packages
```

## 项目结构

```
.
├── docs/                          # 文档目录
│   ├── npm-offline-package-guide.md
│   ├── platform-qa.md
│   ├── platforms.md
│   └── prompt.pip.txt
├── .env.npm                       # npm 配置
├── .env.pip                       # Python 配置
├── .gitignore
├── README.md
├── clear.bat                      # Windows 清理脚本
├── clear.sh                       # Linux/Mac 清理脚本
├── npm_install.sh
├── npo_fetch.py                   # npm 包下载工具 (Python 版本)
├── npo_fetch.sh                   # npm 包下载工具 (Shell 版本)
├── npo_setup.sh                   # npo 安装脚本
├── package.json                   # npm 项目配置
├── package.json.j2                # jinja2 模板
├── packages.txt                   # npm 包列表
├── pip_download.py                # Python 包下载工具
└── requirements.txt               # Python 依赖列表
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
