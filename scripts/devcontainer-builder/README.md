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
│   ├── docker.py            # buildx 构建、外挂镜像 pull、docker save
│   ├── package.py           # src / bundle 两个 tgz 打包
│   └── summary.py           # GITHUB_STEP_SUMMARY / GITHUB_OUTPUT
└── templates/
    ├── Dockerfile.prod.tmpl       # prod 阶段（基础镜像 + APT/自定义命令 + 离线 pip install）
    ├── Dockerfile.dev.tmpl        # dev 阶段（FROM prod + 开发工具）
    ├── compose.base.tmpl          # compose 骨架（app 服务 + 占位块）
    ├── compose.service.nginx.tmpl # nginx 服务子模板
    ├── compose.service.postgres.tmpl # postgres 服务子模板
    ├── Makefile.tmpl              # make 目标（up/shell/lint/compile/test 等）
    ├── requirements.txt.tmpl      # pip 包清单
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
| `CUSTOM_INSTALL_CMD` | 空 | prod 镜像内的个性化安装命令 |
| `ENABLE_NGINX` | `false` | 启用 nginx 服务 |
| `ENABLE_POSTGRES` | `false` | 启用 postgres 服务 |
| `APP_DEPENDS_ON_NGINX` | `false` | app depends_on nginx |
| `APP_DEPENDS_ON_POSTGRES` | `false` | app depends_on postgres |
| `PROD_COMMAND` | `python main.py` | prod 服务命令 |
| `BUILD_DEV_IMAGE` | `true` | 是否构建 dev 镜像 |
| `IMAGE_PREFIX` | `devcontainer` | 镜像名前缀 |
| `APP_SOURCE_DIR` | `.` | 挂载为 /app 的源码目录 |
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

- **多阶段 Dockerfile**：`prod`（运行时）与 `dev`（`FROM prod` + ruff/pytest
  等工具）在同文件内分阶段构建，compose 通过 `target` 区分；dev 服务挂
  `profiles: [dev]`，仅 `make shell/lint/test` 激活，不影响 `make up`。
- **CMD 而非 ENTRYPOINT**：prod/dev 镜像默认命令均通过 `CMD` 承载，
  `docker compose up` 时由 compose `command` 覆盖执行 `python main.py`，
  `docker compose run dev` 时落到 dev 镜像的 `CMD ["bash"]`，互不冲突。
- **镜像 TAG**：`<yyyymmdd-HHMMSS>`（UTC），与两个产物文件名的时间戳一致，
  保证 compose 引用与 `docker save` 的镜像名一一对应。
- **glibc 语义**：基础镜像固定 slim-bookworm（glibc 2.36），glibc 参数仅决定
  pip download 请求的 manylinux 标签集合（目标 glibc 及以下全部标签）。
- **YAML 安全**：compose 中的 `command` 与 `volumes` 挂载路径使用
  JSON 转义后的双引号标量注入，避免命令含 `:` / 空格时破坏 YAML 结构。
