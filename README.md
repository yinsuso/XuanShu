# 🤖 玄枢 (XuanShu) v5.5.7

**一个具备自进化能力的本地AI智能体集群系统**

玄枢 (XuanShu) 不仅仅是一个对话界面，它是一个能够自我反思、自我升级并支持局域网协作的认知系统。它遵循“本地优先”原则，确保所有数据不出域，打造真正的私人数字大脑。

## 主要是针对用户：
- **1. 专为中低端显卡打造，局域网模式可以将多台1080、2080等家用显卡并联协作。**
- **2. 新增【跨互联网远程串联】支持：本地显卡电脑 ↔ 远程GPU服务器，无论身处何地，只要能通过TCP连通，就能组成分布式算力集群！**
- **3. 有保密需要的设备全部本地部署模型，所有数据不出域，绝对防泄露。**
- **4. 完全本地、无后门、开源、完全可控，你可以自由进行优化升级。**

## ✨ 核心特性

- **🧠 自进化认知**：内置 `EvolutionEngine`，能够从错误中学习并自动生成新的 Python 技能插件。
- **🌐 局域网协作**：支持一键创建/加入协作房间，UDP三重发现机制确保中继路由器场景也能100%找到房间。
- **🚀 跨互联网远程串联**：【新增核心功能】手动指定IP/域名，突破局域网限制！本地显卡电脑和远程GPU服务器可以跨地区串联成分布式算力集群，心跳保活、负载实时上报、分工协作！
- **💾 双轨记忆系统**：结合 SQLite (高性能潜意识) 与 Markdown (可编辑意识)，实现长期记忆的精准检索与人工引导。
- **👁️ Web 资源直显**：完美支持模型生成的图片、音频、视频在 Web 端直接预览。

## 🚀 快速开始

### 环境要求
- Python 3.10+
- Ollama (本地模型运行环境)

### 一键启动（推荐）

现在有了 **智能启动器**，你只需要运行：

```bash
python launcher.py
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

```bash
python launcher.py
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

# 开放防火墙端口（以ufw为例，Ubuntu/Debian）
sudo ufw allow 30000/tcp  # Web服务端口
sudo ufw allow 30001/tcp  # 集群Manager TCP监听端口
sudo ufw allow 50005/udp  # 局域网UDP房间发现广播端口
sudo ufw reload

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
# 推荐轻量模型
ollama pull phi3:3.8b
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
ollama pull phi3:3.8b
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


## 🗺️ 集群协作 — 单机群殴，分布式算力协同

玄枢完全支持两种模式的集群协作：**局域网自动发现** + **跨互联网远程手动串联**，让你的本地1080/2080显卡可以和任何地方的GPU服务器完美分工。

### 🎯 两大协作模式对比

| 模式 | 适用场景 | 发现方式 | 跨地区支持 |
|------|---------|---------|-----------|
| **模式A：局域网自动发现** | 家里/办公室的多台电脑在同一网段 | UDP三重广播 + 智能单播探测 | ❌ 仅限局域网 |
| **模式B：手动指定IP跨互联网串联** | 本地家用机 + 云GPU服务器、异地分布式节点 | 直接TCP点对点连接 | ✅ 全球任何地方，只要网络连通 |

---

### 📖 模式A：局域网自动协作（中继路由器也能100%发现）

即使主路由器的设备列表里看不到中继路由器下的设备，玄枢的**UDP三重保障发现机制**依然能找到所有房间：
1. 无条件全局有限广播 `255.255.255.255`
2. 自动派生子网广播地址
3. 兜底上百个常用IP单播探测

#### 快速启动局域网协作
1. 所有机器在同一WiFi/局域网下
2. 第一台机器「创建房间」，自动启动UDP广播
3. 其他机器打开房间列表，稍等几秒自动发现并加入
4. 直接开始分工协作

---

### 🚀 模式B：跨互联网远程串联 — 本地 ↔ 异地GPU服务器 （核心新功能）

这是最强大的模式！无论你的远程GPU服务器在云端、在外地办公室，只要TCP网络能连通，就能组成分布式集群。

#### 使用步骤示例：「本地1080家用机 + 云GPU服务器 协同工作」

| 步骤 | 房主侧（远程GPU服务器） | 成员侧（本地家用显卡电脑） |
|------|-------------------------|---------------------------|
| 1️⃣ 前置准备 | 确保你能通过公网IP/SSH远程连接到云服务器，防火墙/云服务商安全组放行 **30001端口（TCP）** | 本地正常运行玄枢，不需要做额外端口映射 |
| 2️⃣ 创建房间 | 运行玄枢，正常「创建房间」，设置花名和大模型 | 打开玄枢主界面 |
| 3️⃣ 调用手动加入API | — | 发POST请求到 `/api/cluster/rooms/manual-join` |
| 4️⃣ 填入请求体 | — | `{ "host_ip": "你的云服务器公网IP或域名", "alias_name": "你的本地花名", "model": "你本地用的模型名如 qwen2.5:7b", "password": "房主设的房间密码（没密码就空字符串）" }` |
| 5️⃣ 完成 | 在房主的成员列表中可以看到你的本地节点在线了！心跳保活自动运行，负载实时上报 | 连接成功，加入协作，房主可以给你分配本地擅长的任务了 |

#### 配套API接口
- `POST /api/cluster/rooms/manual-join` — 核心接口，手动指定远程房主IP加入
- `POST /api/cluster/rooms/manual-leave` — 安全断开远程连接
- `GET /api/cluster/discovery/local-rooms` — 获取当前UDP自动发现的所有局域网房间列表

---

### 🧠 调度策略

默认使用 **能力优先**（Capability），根据模型基准分、硬件算力、实时负载、历史表现和网络质量进行综合评估。可在 `config.py` 中调整 `SCHEDULER_STRATEGY` 为 `load`（负载均衡）、`round_robin`（轮询）或 `affinity`（亲和性匹配）。

### 🔒 安全特性

- Manager 可设置房间密码（最大 32 字符），SHA256 加密验证。
- 所有集群 API 需验证 `X-Cluster-Token`（与 `CLUSTER_API_TOKEN` 一致）。

### 🌐 跨平台端口开放说明

为了让局域网内多台设备可以正常发现和连接协作房间，你需要确保防火墙开放以下关键端口，三端分别处理方式：

| 端口 | 协议 | 用途 | 说明 |
|------|------|------|------|
| **30000** | TCP | Web 界面服务 | 所有用户通过浏览器访问玄枢界面的默认端口 |
| **30001** | TCP | 集群 Manager 监听 | 所有Worker节点通过TCP连接房主进行任务分发的端口 |
| **50005** | UDP | 局域网房间发现广播 | UDP协议，用于扫描发现同一网段内其他主机的协作房间信息 |

#### 🪟 Windows 用户
Windows Defender防火墙会自动放行本地回环连接，但如果你需要其他局域网设备访问你的玄枢，需要手动添加入站规则：
```powershell
# 以管理员身份运行PowerShell
New-NetFirewallRule -DisplayName "玄枢 30000" -Direction Inbound -Protocol TCP -LocalPort 30000 -Action Allow
New-NetFirewallRule -DisplayName "玄枢 30001" -Direction Inbound -Protocol TCP -LocalPort 30001 -Action Allow
New-NetFirewallRule -DisplayName "玄枢 50005" -Direction Inbound -Protocol UDP -LocalPort 50005 -Action Allow
```

#### 🍎 macOS 用户
在「系统设置 - 网络 - 防火墙」中手动添加Python程序允许传入连接，或直接使用以下命令临时放行：
```bash
sudo pfctl -e  # 启用pf防火墙后配置规则放行30000/30001(UDP50005)
```

#### 🐧 Linux 用户（Ubuntu/Debian/CentOS通用）
```bash
# Ubuntu/Debian 使用ufw
sudo ufw allow 30000/tcp
sudo ufw allow 30001/tcp
sudo ufw allow 50005/udp
sudo ufw reload

# CentOS/RHEL 使用firewalld
sudo firewall-cmd --add-port=30000/tcp --permanent
sudo firewall-cmd --add-port=30001/tcp --permanent
sudo firewall-cmd --add-port=50005/udp --permanent
sudo firewall-cmd --reload
```

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
本项目由 qwen3.5 、step-3.5-flash 、kimi-k2.6 与 gemma 4 模型提供技术辅助，部分代码由这两个代码编写并审核。


## 📜 开源协议
本项目采用 **Apache License 2.0** 协议开源。