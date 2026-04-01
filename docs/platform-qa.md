# User Question1
## question
```sh
william@DESKTOP-RL3B3I2 MINGW64 /d/tmp/ta
$ pip download   --only-binary=:all:   --platform manylinux_2_28_x86_64   --python-version 310   -d ./wheels   -r requirements.txt
Collecting jinja2 (from -r requirements.txt (line 1))
  Using cached jinja2-3.1.6-py3-none-any.whl.metadata (2.9 kB)
Collecting mssql (from -r requirements.txt (line 2))
  Using cached mssql-1.0.1-py3-none-any.whl.metadata (664 bytes)
Collecting pyodbc (from -r requirements.txt (line 3))
  Using cached pyodbc-5.3.0-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (2.7 kB)
ERROR: Could not find a version that satisfies the requirement numpy (from versions: none)
ERROR: No matching distribution found for numpy
```
## answer
### 解决 pip 下载 numpy 报错：无匹配版本 (manylinux_2_28_x86_64)
你遇到的核心问题：**`numpy` 没有提供 `manylinux_2_28_x86_64` 这个平台标签的纯二进制包**，pip 找不到对应文件，所以报错。

### 问题原因
1. 你指定了强制参数：`--platform manylinux_2_28_x86_64` + `--only-binary=:all:`
2. **numpy 官方只发布了 `manylinux_2_17_x86_64` 等兼容标签**，**没有** `manylinux_2_28_x86_64` 专属包
3. 强制要求「仅二进制+指定平台」时，pip 不会自动兼容下级平台标签，直接报错无版本

### 解决方案（二选一，推荐方案1）
#### 方案1：修改平台标签（最稳妥，兼容你的目标环境）
把 `manylinux_2_28_x86_64` 换成 **`manylinux_2_17_x86_64`**（numpy 官方支持，且完全兼容 2_28 环境）

完整命令：
```bash
pip download \
  --only-binary=:all: \
  --platform manylinux_2_17_x86_64 \
  --python-version 310 \
  -d ./wheels \
  -r requirements.txt
```

#### 方案2：放宽二进制限制（不推荐，会下载源码包）
去掉 `--only-binary=:all:`，但会下载 `.tar.gz` 源码包，不符合你离线部署的需求。

---

### 补充说明
1. **兼容性**：`manylinux_2_17_x86_64` 向下兼容 `manylinux_2_28_x86_64` 系统，下载的包可以正常使用
2. **验证**：你可以去 [numpy PyPI 页面](https://pypi.org/project/numpy/#files) 查看，所有 numpy 轮子都只有 `manylinux_2_17` 标签
3. **其他包**：`jinja2`/`mssql`/`pyodbc` 都支持 `manylinux_2_28`，只有 numpy 不支持

### 总结
1. 核心错误：**numpy 无 manylinux_2_28 二进制包**
2. 修复方法：**将平台改为 manylinux_2_17_x86_64**
3. 替换后命令可直接运行，成功下载所有依赖包


# User Question2
## question
manylinux_2_28_x86_64 和 manylinux_2_17_x86_64有什么区别，还有manylinux2014_x86_64

## answer
这三个 `manylinux` 标签是 Python 二进制 wheel 包的**平台兼容性标准**，核心区别在于**基于的 `glibc` 版本不同**，决定了能在哪些 Linux 系统上运行。**`manylinux_2_17` 与 `manylinux2014` 完全等同且兼容最广，`manylinux_2_28` 要求更高、兼容性更窄。**

### 一、核心定义与对应关系
| 标签 | 对应 PEP | 基于系统 | **最低 glibc 版本** | 兼容性（可运行的系统） |
|:--- |:--- |:--- |:--- |:--- |
| **manylinux2014_x86_64** | PEP 599 | CentOS 7 | **2.17** | 极广：CentOS 7+, RHEL 7+, Ubuntu 14.04+, Debian 8+ 等几乎所有**2014年后**的 Linux |
| **manylinux_2_17_x86_64** | PEP 600 | 新命名规范 | **2.17** | **与 manylinux2014 完全等价**，只是命名更清晰（直接标注 glibc 版本） |
| **manylinux_2_28_x86_64** | PEP 600 | AlmaLinux 8 / Rocky Linux 8 | **2.28** | 较新系统：CentOS 8+, RHEL 8+, Ubuntu 18.10+, Debian 10+ 等**2018年后**的系统 |

### 二、关键区别详解
#### 1. 命名规则的进化
- **`manylinux2014`**：旧命名法（按年份），不易直观判断依赖。
- **`manylinux_2_17 / _2_28`**：新命名法（`manylinux_${主版本}_${次版本}`），**直接对应 glibc 版本号**，一目了然。
  - `manylinux_2_17` = glibc >= 2.17
  - `manylinux_2_28` = glibc >= 2.28

#### 2. 兼容性（向下兼容原则）
- **`manylinux_2_17` (manylinux2014) 最通用**
  - 它是目前**兼容性最广**的标准，支持绝大多数新旧服务器。
  - **可以运行在 `manylinux_2_28` 的系统上**（因为 glibc 2.28 高于 2.17，满足最低要求）。
- **`manylinux_2_28` 要求更高**
  - 仅支持较新的 Linux 发行版。
  - **不能运行在只支持 `manylinux_2_17` (glibc 2.17) 的老系统上**（如 CentOS 7），会报 `GLIBC_2.28` 未找到的错误。

#### 3. 为什么你会遇到 numpy 错误？
- **numpy 等主流库**：为了最大化兼容，官方只提供 **`manylinux_2_17` (manylinux2014)** 的二进制包。
- **你的命令**：`--platform manylinux_2_28_x86_64 --only-binary=:all:` 强制 pip **只找** `2_28` 专属包。
- **结果**：pip 找不到 numpy 的 `2_28` 包，因此报错。

### 三、总结与实践建议
1. **`manylinux2014_x86_64` = `manylinux_2_17_x86_64`**
    - 两者完全一样，**可以互换使用**。`_2_17` 是 `manylinux2014` 的新名字。
2. **`manylinux_2_28_x86_64`**
    - 要求系统 glibc >= **2.28**，兼容更新的系统，但**很多库（如 numpy）未提供此版本**。
3. **离线下载最佳实践（解决你之前的问题）**
    - 永远优先用 **`manylinux_2_17_x86_64`**（即 manylinux2014）。
    - 它能在你的目标服务器（`2_28` 环境）上完美运行，且能下载到所有库（包括 numpy）。

**结论**：你之前的命令只需将 `manylinux_2_28` 改为 `manylinux_2_17` 即可。