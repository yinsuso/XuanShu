# 📜 更新记录 (CHANGELOG)

本项目遵循语义化版本管理。所有重大更新、功能新增及漏洞修复均记录于此。

## [Unreleased]

### Added
- 集群协作协议层（evolution/cluster/）：
  - MessageType 枚举（8种消息类型）
  - ClusterMessage 基类（序列化/反序列化）
  - 便捷构造函数：create_capability_advertisement, create_task_assignment, create_auth_request, create_auth_response, create_heartbeat, create_leave_notification
- 连接层增强
  - ClusterNode 扩展：capability_score, last_heartbeat, connection, pending_tasks
  - 简易能力评估（模型排行榜 + GPU 加成）
  - TCP 握手流程加入能力广播
- 单元测试套件：tests/cluster/ (23 tests)
- **Phase 2: 集群任务管理**
  - `ClusterNode` 任务状态机（PENDING / RUNNING / COMPLETED / FAILED）
  - 集群 API 端点：`POST /cluster/tasks`、`POST /cluster/tasks/batch`、`GET /cluster/status`、`WebSocket /cluster/ws/updates`
  - FastAPI 集成（CORS 支持、startup 事件、Agent 挂载）
  - Agent 任务执行与状态推送钩子
- **配置扩展**：新增 `CLUSTER_ENABLED`、`CLUSTER_ROLE`、`CLUSTER_MANAGER_HOST`、`CLUSTER_MANAGER_PORT`、`CLUSTER_NODE_ID`、`CLUSTER_NODE_NICKNAME`、`CLUSTER_WORKER_THREADS`、`CLUSTER_API_TOKEN`
- **依赖更新**：`fastapi==0.104.1`、`uvicorn[standard]==0.24.0`

### Changed
- N/A

### Fixed
- N/A

## [v5.0.0] - 2026-05-02
### 🚀 重大更新
- **认知系统升级**：引入 `process_adaptive` 自适应处理链路，支持在 Simple 和 ReAct 模式间动态切换。
- **集群协作模式**：实现基于 UDP 广播的局域网房间发现机制，支持多 Agent 协作。
- **前端架构重构**：完成由单体 `index.html` 向 `HTML/CSS/JS` 模块化结构的迁移，提升维护性。
- **视觉境界体系**：新增【原点·极简黑】、【空灵·禅意白】、【赛博·霓虹蓝】三套完整视觉方案及主题持久化。

### 🛠️ 核心修复与优化
- **存储加固**：`memory_core.py` 引入 SQLite WAL 模式，彻底解决并发写入锁死问题。
- **资源直显**：建立 `/media` 静态资源路由，支持模型生成的图片、音频、视频在 Web 端直接预览。
- **跨平台适配**：完成 macOS 适配，提供 `setup_mac.sh` 一键部署脚本，剔除所有 Linux 硬编码路径。
- **全量审计**：执行“白虎审计”，修复了 100+ 处导入规范问题及所有语法漏洞。

### 📦 新增特性
- 增加 Web 端协作控制面板 $	ext{🤝}$。
- 实现主题切换下拉菜单与本地缓存记忆。
- 增加对话记录导出为 Markdown 的功能。

---
*记录生成于：2026-05-02*
