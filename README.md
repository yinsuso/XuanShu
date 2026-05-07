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
python xuan_cli.py
```


**macOS 用户：**
```bash
chmod +x setup_mac.sh
./setup_mac.sh
source venv/bin/activate
python3 xuan_cli.py
```

**Linux 用户：**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 xuan_cli.py
```

## 🛠️ 技术栈
- **Backend**: FastAPI, SQLite (WAL), Python 3.10
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **LLM**: Ollama / OpenAI / DeepSeek / Moonshot (适配多种 Provider)


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