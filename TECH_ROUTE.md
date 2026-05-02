# 玄枢 (XuanShu) 技术路线图 (Technical Roadmap)

## 1. 核心架构 (Core Architecture)
### 1.1 认知模型
- **自适应处理链路**：`agent.py` 实现 `process_adaptive` 逻辑，根据任务复杂度在 **Simple Loop** (直接响应) 与 **ReAct Loop** (推理-行动-观察) 之间动态切换。
- **闭环进化机制**：每个任务结束强制触发 `EvolutionEngine`，执行“执行 $ightarrow$ 反思 $ightarrow$ 技能生成 $ightarrow$ 验证”的闭环，实现 Agent 的自我升级。

### 1.2 记忆系统 (Dual-Track Memory)
- **潜意识层 (Subconscious)**：基于 **SQLite (WAL 模式)** 的结构化存储。负责海量对话历史、反思日志和技能注册表，解决高并发下的 `database is locked` 问题。
- **意识层 (Consciousness)**：基于 **Markdown/JSON** 的非结构化存储 (`SOUL.md`, `MEMORY.md`)。存储核心人格、长期价值观和用户偏好，允许人类直接编辑进行“灵魂引导”。

## 2. 协作模式 (Cluster Collaboration)
### 2.1 发现机制
- **UDP 广播**：`evolution/cluster/discovery.py` 实现局域网内的房间发现与心跳维持。
- **角色定义**：支持 `架构师`、`工程师`、`文案` 等多角色定义，实现分工协作。

### 2.2 交互协议
- **握手流程**：房主 (Host) 广播 $ightarrow$ 成员 (Node) 扫描 $ightarrow$ 握手确认 $ightarrow$ 状态同步。
- **Web 控制**：通过 `/api/cluster/*` 系列接口将底层集群状态映射至前端 UI。

## 3. Web 界面与交互 (Frontend Engineering)
### 3.1 技术栈
- **后端**：FastAPI (异步高并发) + Uvicorn。
- **前端**：纯净 HTML5 + CSS3 (变量体系) + 原生 JavaScript (模块化)。
- **资源托管**：`/media` 静态路由，解决本地生成文件 (图片/音频) 的浏览器显示问题。

### 3.2 视觉境界体系
- **theme-origin (极简黑)**：专注、冷峻，低干扰。
- **theme-zen (禅意白)**：轻盈、宁静，高可读性。
- **theme-cyber (霓虹蓝)**：前卫、流动，玻璃拟态效果。

## 4. 部署与兼容性 (Deployment)
- **跨平台适配**：通过 `os.path` 动态根目录，脱离 Linux 硬编码路径。
- **快速部署**：`setup_mac.sh` 提供一键式 venv 环境构建与依赖安装。
