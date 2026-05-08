# 🤖 玄枢 (XuanShu) v5.4.1

**一个具备自进化能力的本地AI智能体集群系统**

玄枢 (XuanShu) 不仅仅是一个对话界面，它是一个能够自我反思、自我升级并支持局域网协作的认知系统。它遵循“本地优先”原则，确保所有数据不出域，打造真正的私人数字大脑。

## 主要是针对用户：
- **1.本地不是大模型而开发的项目，通过局域网协作模式可以将多台1080、2080等显卡并联协作。**
- **2.有保密需要的设备在本地部署模型，防止泄露**
- **3.本地、无后门、开源、可自己进行优化升级**

## ✨ 核心特性

- **🧠 自进化认知**：内置 `EvolutionEngine`，能够从错误中学习并自动生成新的 Python 技能插件。
- **🌐 局域网协作**：支持一键创建/加入协作房间，实现多台设备间的 AI 协同工作。
- **💾 双轨记忆系统**：结合 SQLite (高性能潜意识) 与 Markdown (可编辑意识)，实现长期记忆的精准检索与人工引导。
- **🎨 三大视觉境界**：提供【原点·极简黑】、【空灵·禅意白】、【赛博·霓虹蓝】三套完整视觉方案，适配不同心境。
- **👁️ Web 资源直显**：完美支持模型生成的图片、音频、视频在 Web 端直接预览。

## 🚀 快速开始

### 环境要求
- Python 3.10+
- Ollama (本地模型运行环境)

### 一键启动（推荐）

现在有了 **智能启动器**，你只需要运行：

```bash
# 两种等价方式
python launcher.py
# 或
python xuan_cli.py
```

启动器会自动：
1. ✅ 检查Python版本
2. ✅ 检查并自动安装依赖
3. ✅ 检测Ollama状态
4. ✅ 自动启动Ollama（如果需要）
5. ✅ 列出已安装的模型
6. ✅ 帮助你选择或下载模型
7. ✅ 更新配置
8. ✅ 启动你选择的界面

### 传统启动方式

#### 命令行界面

```bash
# 使用新版SkillAgent v4.0（推荐）
python agent.py

# 或使用旧版Agent v3.1（保留兼容）
python agent_v3_1.py
```

#### Web界面

```bash
python web_app.py
```

然后打开浏览器访问：`http://localhost:30000`

### 安装部署
**Windows 用户：**
```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活虚拟环境
.\venv\Scripts\activate

# 3. 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 4. 启动项目
python launcher.py
```


**macOS 用户：**
```bash
chmod +x setup_mac.sh
./setup_mac.sh
source venv/bin/activate
python3 launcher.py
```

**Linux 用户：**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 launcher.py
```

### 前置准备

#### 1. 安装Ollama

如果还没有安装Ollama，请先访问：
- https://ollama.com/download

下载并安装适合你系统的版本。

#### 2. 拉取模型（可选）

虽然启动器会帮你下载，但你也可以预先拉取：

```bash
# 推荐模型（代码能力强）
ollama pull qwen2.5-coder:7b

# 或更轻量的模型
ollama pull phi3:3.8b

# 或通用模型
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
```

### 使用技巧

#### 在交互界面中

- 输入 `skills` - 查看所有可用技能
- 输入 `clear` - 清空对话记忆
- 输入 `exit` / `quit` - 退出

#### 使用技能

Agent会根据你的需要自动调用技能，例如：

| 你说的话 | 可能调用的技能 |
|---------|--------------|
| "帮我列出当前目录" | list_dir |
| "读取config.py文件" | read_file |
| "搜索Python教程" | web_search |
| "计算100以内的素数和" | run_code |

### 故障排除

#### Ollama无法启动

检查Ollama是否安装：
```bash
ollama --version
```

手动启动Ollama：
```bash
ollama serve
```

#### 依赖安装失败

尝试手动安装：
```bash
pip install -r requirements.txt
```

#### 模型下载慢

你可以手动下载：
```bash
ollama pull qwen2.5-coder:7b
```

#### 端口被占用

Web界面默认使用30000端口，你可以修改config.py或设置：
```bash
set WEB_PORT=8080  # Windows
export WEB_PORT=8080  # Linux/Mac
```

## 🛠️ 技术栈
- **Backend**: FastAPI, SQLite (WAL), Python 3.10
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **LLM**: Ollama / OpenAI / DeepSeek / Moonshot (适配多种 Provider)

## ⚙️ 配置参数说明

所有配置都在 `config.py` 文件中，你可以通过环境变量覆盖：

```bash
# 更改模型
set MODEL_NAME=phi3:3.8b  # Windows
export MODEL_NAME=phi3:3.8b  # Linux/Mac

# 启用向量记忆
set USE_VECTOR_MEMORY=true
```

### 核心配置参数

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| **基础路径** |
| PROJECT_ROOT | str | 自动检测 | - | 项目根目录 |
| MEMORY_DB_PATH | str | `agent_memory.db` | - | SQLite数据库路径 |
| **Ollama配置** |
| OLLAMA_BASE_URL | str | `http://localhost:11434` | OLLAMA_BASE_URL | Ollama服务地址 |
| MODEL_NAME | str | None | MODEL_NAME | 使用的模型名称 |
| **Web服务** |
| WEB_HOST | str | `0.0.0.0` | WEB_HOST | Web服务监听地址 |
| WEB_PORT | int | `30000` | WEB_PORT | Web服务端口 |
| **安全配置** |
| MAX_CODE_EXECUTIONS | int | `10` | - | 单次对话最大代码执行次数 |
| CODE_EXECUTION_TIMEOUT | int | `10` | - | 代码执行超时时间(秒) |
| **Docker沙箱** |
| SANDBOX_ENABLED | bool | `true` | SANDBOX_ENABLED | 是否启用Docker沙箱 |
| SANDBOX_CPU_LIMIT | float | `0.5` | SANDBOX_CPU_LIMIT | CPU限制(0.0-1.0) |
| SANDBOX_MEMORY_LIMIT | str | `256m` | SANDBOX_MEMORY_LIMIT | 内存限制 |
| SANDBOX_TIMEOUT | int | `30` | SANDBOX_TIMEOUT | 沙箱执行超时(秒) |
| **网络控制** |
| NETWORK_ENABLED | bool | `true` | NETWORK_ENABLED | 是否启用网络访问控制 |
| NETWORK_DEFAULT_ACTION | str | `deny` | NETWORK_DEFAULT_ACTION | 默认操作(allow/deny) |
| NETWORK_WHITELIST | list | 见config.py | NETWORK_WHITELIST | 域名白名单(逗号分隔) |
| **日志配置** |
| LOG_LEVEL | str | `INFO` | LOG_LEVEL | 日志级别(DEBUG/INFO/WARNING/ERROR) |
| LOG_FORMAT | str | `text` | LOG_FORMAT | 日志格式(text/json) |
| LOG_FILE | str | None | LOG_FILE | 日志文件路径 |
| **记忆系统** |
| USE_VECTOR_MEMORY | bool | `false` | USE_VECTOR_MEMORY | 是否启用向量记忆 |
| VECTOR_MODEL | str | `all-MiniLM-L6-v2` | VECTOR_MODEL | 向量模型名称 |
| **进化功能** |
| ENABLE_EVOLUTION | bool | `false` | ENABLE_EVOLUTION | 是否启用自进化功能 |
| **集群协作** |
| CLUSTER_ENABLED | bool | `false` | CLUSTER_ENABLED | 是否启用集群协作 |
| CLUSTER_ROLE | str | `worker` | CLUSTER_ROLE | 角色(manager/worker) |
| CLUSTER_MANAGER_HOST | str | `127.0.0.1` | CLUSTER_MANAGER_HOST | Manager地址 |
| CLUSTER_MANAGER_PORT | int | `30001` | CLUSTER_MANAGER_PORT | Manager端口 |


## 🗺️ 集群协作（实验性）

玄枢支持多节点协作模式，通过内网发现与 TCP 连接实现任务分发与负载均衡。

### 角色

- **Manager**：负责房间创建、节点管理、任务调度。启动时设置 `CLUSTER_ROLE=manager`。
- **Worker**：执行任务，向 Manager 注册能力。设置 `CLUSTER_ROLE=worker` 及 `CLUSTER_MANAGER_HOST`、`CLUSTER_MANAGER_PORT`。

### 快速启动

1. 配置环境变量（可从 `.env.example` 复制），至少启用 `CLUSTER_ENABLED=true`，并设置角色及网络参数。
2. 启动 Manager 节点（默认监听 0.0.0.0:30001）。
3. 启动 Worker 节点，填入 Manager 的 IP 与端口，即可自动加入房间。
4. 通过 Web 控制面板 (`/static/index.html`) 查看集群状态、节点负载与任务队列。

### 调度策略

默认使用 **能力优先**（Capability），根据模型基准分、硬件算力、实时负载、历史表现和网络质量进行综合评估。可在 `config.py` 中调整 `SCHEDULER_STRATEGY` 为 `load`（负载均衡）、`round_robin`（轮询）或 `affinity`（亲和性匹配）。

### 安全特性

- Manager 可设置房间密码（最大 32 字符），通过 bcrypt 加密存储。
- 所有集群 API 需验证 `X-Cluster-Token`（与 `CLUSTER_API_TOKEN` 一致）。

### 监控与日志

- Manager 自动监控任务超时并重派。
- 通过 `LOG_LEVEL` 控制日志详细程度。

### 前端交互

- 访问 `/static/index.html` 进入主界面。
- 集群控制面板提供：
  - 房间状态、成员列表
  - 节点实时负载（CPU、内存、GPU）
  - 任务队列与完成状态
  - 一键启停协作任务

## AI声明：
本项目由 qwen3.5 、step-3.5-flash 与 gemma 4 模型提供技术辅助，部分代码由这两个代码编写并审核。


## 📜 开源协议
本项目采用 **Apache License 2.0** 协议开源。