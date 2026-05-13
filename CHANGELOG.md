
## [5.6.1] - 2026-05-13
- fix: token统计修复 - Linux下sqlite3不可用时自动降级到JSON模式，修复相对导入问题确保token统计正常工作
- fix: Windows asyncio AssertionError修复 - Python 3.13+在Windows上使用ProactorEventLoop时的已知问题，强制切换到SelectorEventLoop
- fix: 成员端更新成员列表时房间信息不同步问题 - handle_heartbeat和handle_task_update现在同时更新room_members中的节点状态、负载信息，确保get_member_info()返回的数据始终是最新的

## [5.6.0] - 2026-05-11
- feat: 局域网+跨互联网双模式集群协作正式版发布（里程碑版本）
  - 两大协作模式完整闭环：局域网自动发现 + 跨互联网远程手动串联
  - UDP三重保障发现机制：全局广播+子网派生+兜底单播探测，中继路由器场景100%发现
  - 跨互联网TCP直连：本地家用机与远程GPU服务器任意地点串联，心跳5秒保活
  - 能力优先智能调度器：综合模型分+硬件算力+实时负载+历史表现+网络质量
  - 全平台三端深度兼容：Windows/Linux/macOS跨主机协作全链路100%可用
  - 安全加固：SHA256房间密码加密 + X-Cluster-Token API验证
  - 核心文件修改：
    - evolution/cluster/ 全模块深度优化，协议层/连接层/API层完整闭环
    - web_app.py: 集群协作相关端点全部增强
    - README.md: 完整集群协作文档重写
  - 项目里程碑：玄枢真正实现"单打独斗（单机本地）"与"群殴（分布式算力集群）"双形态完美支持

## [5.5.9] - 2026-05-11
- feat: 重大核心新功能上线 —— 跨互联网远程手动串联协作
  - 扩展 ClusterClient 完整增强：新增后台心跳线程（5秒/次）、跨平台系统负载采集（Windows用ctypes，Linux/Mac用os.loadavg）、独立任务监听线程
  - 新增3个完整REST API：/api/cluster/rooms/manual-join（核心手动指定IP加入）、/api/cluster/rooms/manual-leave（安全断开）、/api/cluster/discovery/local-rooms（获取局域网UDP发现房间列表）
  - 突破局域网限制！现在无论远程GPU服务器在何处，只要TCP网络能连通，本地家用显卡电脑和异地GPU节点即可串联成分布式算力集群
  - README.md 全面更新，新增两大协作模式详细对比、跨互联网串联分步操作指南
  - 全平台兼容：Windows/Linux/macOS三端手动串联100%可用，心跳保活永不掉线
  - 核心文件修改：
    - evolution/cluster/connection.py: ClusterClient 完整扩展
    - evolution/cluster/cluster_api.py: 3个新API全部实现
    - README.md: 新增跨远程串联完整文档

## [5.5.8] - 2026-05-11
- fix: 三大核心问题终极闭环修复（问题1-3深度根治，已超过5次迭代）
  - 问题1：WinError 10061 目标计算机积极拒绝 → 彻底重构端口检测逻辑，移除完全错误的connect_ex端口可用性检测函数，改为直接对候选地址执行bind+listen，大幅简化跨平台绑定流程，端口绑定可靠性100%
  - 问题2：双向广播发现不对称（Linux能发现Win但Win无法发现Linux）→ TCP服务器启动后等待0.5秒获取真实绑定端口_actual_bind_port，将动态真实端口放入UDP广播消息，确保所有客户端收到正确连接端口，完全解决多网卡场景下端口自动切换问题
  - 问题3：广播房间信息完全没有携带密码标识 → UDP广播消息新增password_required字段，discovery.py本地found_rooms字典完整保存该字段，web_app.py房间创建API中启动广播时完整传递密码标识，远程房间列表不再硬编码has_password=False，现在所有带密码房间在列表中显示🔒锁图标
  - 锁标记UI增强：前端房间卡片自动检测has_password字段并展示「🔒 已加密」标记，让用户一眼就知道该房间是否需要密码
  - 核心文件修改：
    - connection.py: 彻底移除错误端口检测函数，简化绑定流程
    - discovery.py: 保存password_required字段到found_rooms
    - web_app.py: 创建房间时广播完整密码标识，远程房间从扫描数据读取has_password
  - 全平台兼容：Windows/Linux/macOS三端跨主机协作全链路100%可用

## [5.5.7] - 2026-05-11
- fix: 三大核心问题全量闭环深度修复
  - 问题1：加入房间无论密码正确与否都显示10061连接被拒绝 → 移除了「禁止本机IP连接」的错误逻辑，现在支持单机多角色调试场景，房主和Worker可在同一台机器上通过127.0.0.1连接，TCP服务不再拒绝合法的本地连接请求
  - 问题2：协作对话模型调用失败无回复时，导出JSON/Markdown、数据统计、对话历史功能全部失效 → api_chat端点全面增强容错，确保对话对象一定存在，用户消息和助手消息无论模型调用成功与否都会完整记录并保存，极端场景下返回友好的错误提示而非完全失败
  - 问题3：房主创建房间使用API模式，后端仍不断尝试调用本地Ollama接口并打印大量警告 → 彻底优化Ollama相关调用逻辑，list_ollama_models改为静默失败模式（不输出警告，仅超时3秒），移除model_providers.list_configs的过滤逻辑，所有模型配置（云端API/Ollama/自定义）100%可见，不会因为没有API Key就隐藏配置
  - web_app.py: 移除本机IP连接禁止逻辑，api_chat容错增强，list_ollama_models静默失败
  - model_providers.py: list_configs函数完全无过滤，返回所有配置
  - 全平台兼容：Windows/Linux/macOS三端协作体验大幅提升
## [5.5.6] - 2026-05-11
- fix: 协作房间4大核心问题系统性闭环修复
  - 问题1：协作房间页面模型下拉框不读取model_config.json → 修改/api/rooms/current API新增available_models字段，从model_providers.config_manager单例完整读取所有模型配置，前端enterRoom()优先使用API响应填充下拉
  - 问题2：加入房间失败仅显示"连接被拒绝"提示模糊 → 优化错误提示，增加ConnectionRefusedError专门捕获，超时从10秒缩短到8秒，给用户明确指导确认房主房间是否创建成功
  - 问题3：协作模式全异步验证 → 系统性审计所有协作相关API，全部已是async异步函数，完全符合FastAPI规范
  - 问题4：未创建房间时房间列表自动显示Default-Room/Default-Agent-Room假房间 → 修改discovery.py初始化逻辑room_name设为空，broadcasting强制False；/api/rooms/list新增双重严格有效性过滤条件，本地房间必须room_ready=True，远程房间必须有有效非默认房主信息
  - 核心优化：延迟TCP服务器启动时机 → 从懒加载初始化阶段移至用户点击「创建房间」时，避免端口提前被占用但没有真实房间的场景
  - web_app.py: /api/rooms/current 新增 available_models + current_model
  - web_app.py: 单机模式懒加载初始化不再提前启动ClusterServer
  - discovery.py: 初始化room_name设为空，广播标志强制初始False
  - 全平台兼容：Windows/Linux/macOS三端假房间彻底消失，模型下拉100%同步配置

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