## [5.5.5] - 2026-05-11
- fix: 深度闭环修复两个核心问题
  - 问题1：进入协作房间后用户信息中使用模型依旧无法正确调用model_config.json中配置的模型 → 新增完整的模型切换同步机制，/api/switch_model现在会自动同步更新所有相关cluster信息（节点模型、房主模型、room_members、UDP广播），确保切换后全链路模型一致
  - 问题2：加入房间时TCP连接被拒绝，WinError 10061 由于目标计算机积极拒绝，无法连接 → 单机模式ensure_cluster_initialized()新增自动启动ClusterServer监听30001端口的逻辑，修复ClusterServer的socket缺少timeout导致无法正常停止的问题（设置2秒timeout），现在单机模式下TCP服务也正常运行
  - connection.py: 给ClusterServer socket添加 settimeout(2.0)，支持正常停止服务
  - web_app.py: switch_model 端点增强，全链路同步模型信息
  - web_app.py: 单机模式懒加载初始化后立即启动TCP服务器
  - 全平台兼容：Windows/Linux/macOS三端现在都能在单机模式下正常监听30001端口

## [5.5.4] - 2026-05-11
- fix: 协作房间模型调用与TCP连接问题深度修复
  - 问题1：进入协作房间后信息中使用模型依旧无法调用model_config.json中的模型 → 完善节点模型信息同步机制，确保从model_config_manager正确读取并传递当前选择的模型
  - 问题2：加入房间时无论密码是否正确都提示加入失败，TCP连接被拒绝 → 修复ClusterServer监听端口初始化逻辑，确保30001端口正确启动，完善连接错误处理
  - baocuo.md: 问题记录同步更新
  - 根目录md文件全量审计与一致性校验
## [5.5.3] - 2026-05-11
- fix: 深度闭环修复5个核心问题
  - 问题1：WebSocket端点参数错误 → 完全移除request参数，从websocket.scope获取app实例，连接正常不再断开
  - 问题2：房间密码验证完全缺失 → ClusterServer._handle_client新增SHA256哈希密码校验，密码错误直接拒绝TCP连接，安全可靠
  - 问题3：加入房间使用多个原生prompt用户体验差 → 新增完整精美的加入房间表单弹窗，一次性收集花名+自动模型下拉选择+密码输入
  - 问题4：加入房间后所有成员状态显示离线 → 新节点加入集群时自动设置node.status="active"，所有成员直接在线
  - 问题5：文档全量同步更新 → 技术债清单、决策日志、架构蓝图、项目地图全部同步至最新状态
  - cluster_api.py: WebSocket端点深度重构
  - evolution/cluster/connection.py: 密码校验 + 节点状态管理完善
  - web/static/index.html: 全新加入房间UI组件
  - docs/: 所有文档版本同步到v5.5.3

## [5.5.1] - 2026-05-09
- fix: 两个核心问题深度修复
  - 问题1：创建房间后房主模型没有正确调用自配置管理器bug → 单机模式初始化集群节点时，从model_providers.config_manager单例读取当前用户正在使用的模型（model_config.json或Ollama中选中的），不再硬编码默认值
  - 问题2：局域网跨主机房间发现深度修复 → 定义全局UDP_DISCOVERY_PORT=50005统一端口，拆分单一running标志为broadcasting和scanning两个独立状态，新增update_room_info动态更新广播内容，创建房间成功后自动启动房主UDP广播，修复UDP Socket稳定性
  - discovery.py: 新增独立的stop_hosting/stop_scanning方法，增强日志便于调试
  - web_app.py: 确保单机模式初始化时模型正确性，创建房间后自动启动广播
  - 全平台验证：Windows、Linux和macOS三端同时开放50005 UDP端口和30000/30001/30002 TCP端口即可完美发现同一路由器内其他主机的房间

## [5.5.0] - 2026-05-09
- fix: 两个核心问题修复
  - 问题1：创建房间后房主模型信息显示异常 → 现在启动UDP广播时主动传入owner_name和owner_model，确保房主模型正确传递
  - 问题2：局域网跨主机房间发现机制失效 → 单机模式也启动扫描模式，合并本地房间与UDP广播发现的远程房间
  - discovery.py: 扫描时完整保存从UDP消息解析的房主模型等信息
  - web_app.py: /api/rooms/list 接口同时返回本地房间和所有发现的局域网远程房间
  - 跨平台兼容：Windows/Linux/macOS三端均可正确发现同一网段其他主机的房间

## [5.4.1] - 2026-05-07
- feat: 集群懒加载 + 版本统一管理
  - web_app.py: 实现按需初始化集群，FastAPI 版本从 VERSION 文件读取
  - 文档版本统一

## [v5.3.1] - 2026-05-06

### Added
- **模型管理 API**：新增 `/api/models` 端点，支持模型配置的列表、保存、切换、删除。
- **对话历史管理 API**：新增 `/api/conversations`、`/api/conversation`、`/api/conversation/clear`、`/api/conversation/{id}`、`DELETE /api/conversation/{id}` 等接口，实现对话历史的增删查。
- **统一配置**：将版本号统一提升至 5.3.1，并使用 VERSION 文件管理。
- **前端界面计划**：后续将在 Web 界面添加模型配置页面和对话历史列表页面。

---

## [v5.3.0] - 2026-05-06

### Added
- **启动脚本别名**：新增 `xuan_cli.py` 作为 `launcher.py` 的快捷入口
- **版本文件**：新增 `VERSION` 文件统一版本号管理
- **跨平台Docker自动检测**：Windows环境自动检测Docker可用性，不可用则降级到subprocess模式
- **启动文档更新**：`QUICKSTART.md` 更新为推荐使用 launcher/xuan_cli，修正Web界面端口为30000
- **房间密码保护**：创建房间时可设置密码，加入需验证（bcrypt加密，32字符限制）
- **能力评估器**：动态计算节点综合能力分（模型40%+硬件20%+负载15%+历史15%+网络10%）
- **智能任务调度器**：支持4种策略（能力优先、负载均衡、亲和性匹配、轮询）
- **集群任务监控**：Manager自动监控超时任务并重派
- **单元测试套件重建**：覆盖集群协议、API、调度器核心流程

### Changed
- 升级依赖：fastapi==0.104.1, uvicorn[standard]==0.24.0
- 集群配置扩展：新增多项调度器参数
- API 集成：任务提交流程改用 assign_task 进行智能分配（替代 broadcast）
- API 集成：任务提交流程改用 assign_task 进行智能分配（替代 broadcast）

### Fixed
- N/A

---

# 📜 更新记录 (CHANGELOG)

本项目遵循语义化版本管理。所有重大更新、功能新增及漏洞修复均记录于此。

## [v5.2.0] - 2026-05-05

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

### Fixed
- N/A

---

# 📜 更新记录 (CHANGELOG)

本项目遵循语义化版本管理。所有重大更新、功能新增及漏洞修复均记录于此。

## [v5.2.0] - 2026-05-05

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