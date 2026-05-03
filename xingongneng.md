# 玄枢功能规划清单

# 玄枢自修改补丁系统（Controlled Self-Patching）

## 概述
本设计允许玄枢 Agent 在用户请求或任务复盘后，生成并应用对核心代码的修改，但同时严格保证安全、可审核、可回滚。系统不会自动执行高风险修改，而是引入人工审批环节。

## 核心组件

| 组件 | 职责 |
|------|------|
| **PatchGenerator** | 根据需求或复盘生成代码修改建议（git diff 格式） |
| **PatchValidator** | 静态分析：语法检查、危险操作扫描、导入白名单验证 |
| **PatchReviewer** | 展示补丁、评估风险、收集批准/拒绝决策 |
| **PatchApplier** | 批准后应用补丁、运行测试、合并分支 |
| **PatchRollbacker** | 撤销最近一次补丁，恢复到上一版本 |
| **PatchLogger** | 记录所有操作到 `logs/patch.log` |

## 详细流程

1. **触发**：用户请求修改核心功能（如“增加定时备份记忆库”），Agent 判定为核心代码调整。
2. **生成补丁**：调用 `PatchGenerator`（基于 LLM）生成 diff 及自然语言说明。
3. **验证**：`PatchValidator` 执行：
   - `python -m py_compile` 语法检查
   - 扫描禁止的危险操作（删除仓库、执行 shell 等）
   - 检查导入模块是否在白名单内
   - 若失败，直接拒绝并告知原因。
4. **人工审批**：在 `/patches` 界面（或 CLI）展示：
   - 修改文件列表
   - Diff 内容（可折叠）
   - 风险等级（高/中/低）
   - 建议的测试命令
   用户选择 **Approve** 或 **Reject**。
5. **应用补丁**：
   - 创建临时分支 `patch/auto/<timestamp>`
   - 应用 diff（`git apply`）
   - 运行快速健康测试（如 `curl /api/health`、单元测试）
   - 测试失败则自动回滚，记录失败
   - 成功则合并到 main 并提交，提交信息包含补丁说明
6. **日志与回滚**：
   - 每次操作写入 `logs/patch.log`（JSON 行格式）
   - 提供 `POST /api/rollback` 接口撤销最新补丁并重启

## 安全策略

- **文件范围白名单**：仅允许修改 `agent/`, `skills/`, `web_app.py`, `evolution/` 等；禁止 `.git`, `logs/`, `config_secrets.py`。
- **权限隔离**：生产环境需管理员 token 方可审批。
- **速率限制**：每分钟最多生成/应用 1 个补丁，避免 runaway。
- **自动备份**：应用前在 `backup/` 创建 zip 备份或 `git stash`。

## 参考实现（Python 伪代码）

```python
class PatchSystem:
    def __init__(self, repo_path: str):
        self.repo = git.Repo(repo_path)
        self.backup_dir = os.path.join(repo_path, 'backup')
    
    def generate(self, user_request: str) -> Patch:
        # 调用 LLM + validator 生成 diff
        pass
    
    def validate(self, patch: Patch) -> ValidationResult:
        # 语法检查、静态扫描
        pass
    
    def request_review(self, patch: Patch) -> bool:
        # 展示给用户，返回是否批准
        pass
    
    def apply(self, patch: Patch) -> bool:
        # 创建分支 -> 应用 -> 测试 -> 合并
        pass
    
    def rollback(self) -> bool:
        # 回滚到上一版本
        pass
```

## 使用示例（CLI）

```bash
$ hermes patch request "增加一个每天定时备份记忆库的功能"
[生成补丁 20250617-001]
[验证] 通过，风险等级: 中
修改文件: agent.py, config.py
diff: (已折叠)
审批? (Y/n): Y
[应用] 测试通过，已合并到 main
```

## 与现有系统的集成

- 复用 `evolution.skill_validator` 的语法检查
- 使用 `web_app.py` 的 `/api/health` 作为健康检查端点
- 日志写入 `logs/patch.log`，供审计

## 开放问题 / TODO

- 如何自动生成测试用例？可对接 `evolution` 测试生成模块
- 多用户场景下避免补丁冲突（需要锁机制）
- 补丁冲突处理策略（需用户介入合并）

## 可扩展功能清单（待实现）

### 1. 定时任务功能（Cron Jobs）
**目标**：让玄枢支持基于时间的自动执行任务（例如每天定时备份记忆库、每周生成报告、提醒待办事项）。

**设计要点**：
- 集成轻量级调度库（偏好APScheduler，支持CRON、interval、date触发器）
- 在 `agent.py` 新增 `TaskScheduler` 模块，负责加载、存储、执行定时任务
- 任务配置存储在项目根目录 `tasks.yaml`（可动态增删）
- 执行结果可写入记忆库或日志；失败时记录并通知用户
- 提供 `/api/tasks` REST 接口：列出、添加、删除任务（需认证）
- 与现有“系统心跳”结合，作为后台线程运行

**安全考虑**：
- 限制可执行模块仅限 `skills/` 和 `utils/`，禁止直接导入核心模块
- 避免任务堆积，设置最大并发数=1
- 任务失败重试次数上限（例如3次）

**示例任务配置**：
```yaml
- name: "backup_memory"
  trigger: "cron"
  hour: 2
  minute: 0
  skill: "memory_backup"
  args: {}
  description: "每天凌晨2点备份记忆库到本地文件"
```

---

### 2. 网络搜索功能（Bing Search Integration）
**目标**：在对话中自动使用 Bing 搜索获取最新公开信息，丰富回答的时效性与准确性。

**设计要点**：
- 新增技能 `web_search`（位于 `skills/web_search.py`），接受查询词、结果数量参数
- 使用微软 Bing Search API（需配置 `BING_API_KEY` 环境变量或配置项`search_bing_api_key`）
- 将搜索结果（标题、摘要、URL）作为“参考内容”插入到 Agent 的上下文记忆中，保持时效性
- 默认仅当用户问题涉及“最新”、“最近”、“2025”等时间敏感词汇且答案不在知识库时自动触发
- 提供 `/api/search` 端点供前端搜索框使用（可选）
- 支持结果去重、按相关性排序

**安全与成本**：
- 限制每日调用次数（默认50次/天，可配置）
- 仅允许HTTPS请求，禁止访问内部地址
- 搜索结果缓存（10分钟）以减少重复调用
- 禁止搜索特定敏感关键词（可配置黑名单）

**技能接口示例**：
```python
@skill(
    name="web_search",
    description="使用 Bing 搜索互联网，获取最新信息摘要",
    category=SkillCategory.WEB,
    requires_confirmation=False
)
def search(query: str, count: int = 5) -> str:
    """返回搜索结果标题和摘要列表"""
    ...
```

---

这两个功能可独立或组合作为补丁发布。建议优先实现定时任务（风险低），后实现网络搜索（需API密钥与成本控制）。

## 安全增强功能清单（新增）

### 概览
本批功能旨在构建多层安全防御体系，从命令执行、网络通信、环境隔离、审批机制、行为监测、日志追踪、敏感信息脱敏七个维度，全面提升玄枢系统的安全水位。遵循「防患于未然，审计于事后」的原则，实现安全能力的可观测、可管控、可追溯。

---

### 1. 类防火墙机制（Command Firewall）
**目标**：对所有终端命令执行进行前置扫描，识别潜在注入攻击、密钥泄露等风险，并根据风险等级触发审批流程。

**设计要点**：
- 新增 `CommandFirewall` 模块，作为 terminal 工具的前置拦截层。
- 采用规则引擎（优先正则表达式+关键词白名单）进行扫描：
  - 检测 `rm -rf`, `dd if=`, `curl http://`, `wget`, `nc`, `ssh`, `scp` 等高危命令
  - 检测环境变量引用（`$API_KEY`, `$SECRET`, `$PASSWORD`）
  - 检测密钥硬编码（形如 `sk-`, `ghp_`, `Bearer ` 等）
  - 检测管道与重定向的组合可能造成的注入
- 分级响应策略：
  - **低风险**：放行并记录
  - **中风险**：放行但标记，等待异步审批（不影响执行流）
  - **高风险**：阻塞执行，强制进入审批流程（用户手动确认）
- 所有扫描结果写入 `logs/firewall.log`，保持审计追踪。

**集成点**：
- `terminal()` 工具在真正执行前调用 `CommandFirewall.scan(command)`
- 提供 `/api/firewall/status` 端点查看拦截统计
- 配置项：`firewall.rules_path`, `firewall.default_action`, `firewall.auto_approve_threshold`

**风险评估**：
- **误报**：需持续迭代规则，支持用户白名单（用户确认的放行规则自动加入白名单）
- **性能**：正则扫描为轻量级操作，对执行延迟影响 < 5ms

---

### 2. 网络风险控制（Network Risk Control）
**目标**：防止 Agent 被恶意利用攻击内网或元数据服务（如云厂商的metadata端点），限制出站连接的目标范围。

**设计要点**：
- 实现 `NetworkController` 模块，对所有出站网络请求（terminal中的curl/wget，Python的requests库，Node的fetch等）进行目标地址校验。
- 配置 `allowed_domains` 白名单（如 `api.github.com`, `pypi.org`），默认拒绝所有非白名单域名。
- 特殊保护：禁止访问以下内网/敏感地址：
  - `169.254.169.254`（AWS/GCP/Azure metadata）
  - `127.0.0.1`, `localhost`, `0.0.0.0`（回环）
  - `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`（私有网络）
- 支持 `bypass` 标记：若某任务获得用户明确授权（审批通过），可临时放宽网络限制。

**集成点**：
- 在 `terminal()` 执行涉及 `curl`, `wget`, `nc`, `telnet` 等命令时，解析目标域名/IP，调用 `NetworkController.allow(host)`。
- 在 Python 代码中，通过 monkey-patch `socket.create_connection` 或 `requests.adapters.HTTPAdapter` 进行拦截。
- 记录拒绝事件到 `logs/network_denied.log`，包含时间、命令、目标、发起位置。

**配置**：
```json
{
  "network": {
    "allowed_domains": ["pypi.org", "github.com", "api.openai.com"],
    "blocked_ips": ["169.254.169.254"],
    "private_networks": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
    "require_approval_for": ["ssh", "scp", "nc"]
  }
}
```

**风险评估**：
- **过度限制**：需提供便捷的审批流程让用户快速放行合法请求。
- **绕过风险**：加密流量（如DNS tunneling）需额外检测（建议结合防火墙规则）。

---

### 3. 执行环境隔离（Execution Environment Isolation）
**目标**：所有终端命令在 Docker 容器中执行，确保宿主系统不受污染，且每次执行环境干净、可销毁。

**设计要点**：
- 引入 `ContainerExecutor` 模块，替代原本的 `subprocess.run`。
- 使用轻量级镜像（如 `python:3.11-slim`, `alpine:latest`），按需挂载必要的只读目录（如 `/usr/bin`, `/lib`）和可写临时目录 `/tmp`。
- 每次 execution 启动新容器（或使用预热的 pool），执行完成后自动销毁（`docker rm -f`）。
- 资源限制：CPU 配额、内存上限（默认 512MB）、30秒超时。
- 持久化需求：若命令需要读写文件，通过 `docker cp` 同步进出，或挂载项目的特定子目录（只读）。
- 日志捕获：容器 stdout/stderr 实时回传并存储。

**流程**：
1. Agent 调用 `terminal()` → 实际通过 `ContainerExecutor.run(command)` 执行。
2. `ContainerExecutor` 生成临时容器名称（`hermes-exec-<timestamp>-<rand>`）。
3. 容器启动，注入环境变量（过滤后的安全变量）。
4. 执行命令，获取退出码和输出。
5. 销毁容器，清理资源。

**配置**：
```json
{
  "container": {
    "enabled": true,
    "image": "alpine:latest",
    "memory_limit": "512m",
    "cpu_quota": 50000,
    "timeout": 30,
    "mounts": [
      {"source": "/usr/bin", "target": "/usr/bin", "readonly": true},
      {"source": "/lib", "target": "/lib", "readonly": true}
    ],
    "env_whitelist": ["PATH", "LANG", "TZ"]
  }
}
```

**依赖**：宿主机需安装 Docker 并允许当前用户操作（docker group 或 root）。

**风险评估**：
- **性能**：容器创建开销 ~200-300ms，适合中小型任务；超大型任务建议复用容器。
- **权限**：需确保 docker socket 安全，避免权限提升。

---

### 4. 操作审批机制（Approval Workflow）
**目标**：对高风险操作（包括但不限于终端命令、文件删除、网络访问）提供三种审批模式：手动审批、智能自动（基于规则）、直接拒绝。

**设计要点**：
- 引入 `ApprovalManager` 统一审批入口。
- 审批策略由 `approval_policy` 配置驱动，支持：
  - **manual**：每次高风险操作必须用户确认（CLI交互或Web界面弹窗）。
  - **auto**：根据风险评分自动决定（评分 < 阈值 → 通过；评分 > 阈值 → 拒绝或手动）。
  - **reject**：直接拒绝所有匹配规则的操作。
- 风险评估维度：命令类型、目标路径权限、网络目标、历史行为模式。
- 审批记录存储在 `data/approvals.json`，包含请求ID、操作者、操作内容、风险评分、决策、时间戳。

**用户界面**：
- Web 界面 `/approvals`：显示待审批列表，提供 Approve/Reject 按钮（需登录）。
- CLI 支持 `hermes approval list` / `hermes approval approve <id>` / `reject <id>`。

**与防火墙集成**：
- 防火墙扫描结果 → 风险评分 → 提交 `ApprovalManager.request(operation, score)` → 返回决策（allow/deny/pending）。

**配置示例**：
```json
{
  "approval": {
    "mode": "auto",
    "auto_threshold": 70,
    "high_risk_commands": ["rm", "dd", "shutdown", "reboot", "passwd"],
    "require_approval_for_paths": ["/etc/", "/var/log/", "~/.ssh"],
    "web_ui_enabled": true,
    "ttl_seconds": 86400
  }
}
```

**风险评估**：
- **用户体验**：手动审批过多会降低效率，需精细调整规则让大多数日常操作自动通过。
- **绕过**：需确保审批点在所有危险操作路径上不可绕过。

---

### 5. 异常行为检测（Anomaly Detection）
**目标**：实时监测 Agent 运行时的系统调用（syscall）、文件访问模式、网络连接等，发现异常行为（如突然大量访问敏感文件、外连可疑地址）并告警或阻止。

**设计要点**：
- 使用轻量级 eBPF（Linux）或 auditd（跨平台）进行系统调用追踪，或采用 Python 层面的 monkey-patch（更简单但覆盖有限）。
- 收集以下事件流：
  - 文件打开/读取/写入（路径、模式、大小）
  - 网络 connect/send/recv（目标IP、端口、字节数）
  - 进程创建（execve）
  - 环境变量读取
- 实时分析引擎（滑动窗口统计）：
  - 短时间大量读取 `/etc/passwd` 类文件 → 暴力破解嫌疑
  - 短时间大量外连不同 IP → 扫描/挖矿行为
  - 访问 `~/.ssh/id_rsa` 且伴随外连 → 密钥泄露风险
  - 执行 `base64` 解码大量数据 → 数据外泄嫌疑
- 响应策略：达到阈值 → 记录事件（`logs/anomaly.log`）→ 触发 `ApprovalManager.reject` 或直接中断当前任务（`SIGTERM`）。

**配置**：
```json
{
  "anomaly": {
    "enabled": true,
    "window_seconds": 60,
    "thresholds": {
      "file_access": {"etc_passwd": 10, "ssh_private": 1},
      "network_connections": 50,
      "external_ip_unique": 10
    },
    "actions": ["log", "alert", "terminate"]
  }
```

**依赖**：Linux 环境下建议使用 eBPF（bcc工具包），Windows 可试用 ETW（较复杂）。若无法使用底层追踪，则采用应用层 monkey-patch 作为降级方案。

**风险评估**：
- **误报**：需持续调优阈值，支持学习模式（建立基线，偏离基线时告警）。
- **性能**：事件流处理不可阻塞主线程，应异步缓冲+批量处理。

---

### 6. 运行日志机制（Structured Logging）
**目标**：为系统所有关键操作（命令执行、网络请求、审批决策、容器生命周期、异常事件）提供结构化日志，便于事后分析、审计与故障排查。

**设计要点**：
- 升级现有 `logger.py` 为结构化日志（JSON 行格式），每行包含：
  - `timestamp`（ISO8601）
  - `level`（DEBUG/INFO/WARN/ERROR/FATAL）
  - `component`（terminal/network/firewall/approval/container/anomaly）
  - `action`（具体操作名）
  - `trace_id`（跨组件追踪，一次用户请求一个 ID）
  - `details`（字典，操作参数、返回码、耗时等）
- 日志轮转：按日期分割，保留 30 天，压缩归档。
- 提供 `LogViewer` 工具：
  - 命令行：`hermes logs --component firewall --level WARN --since 2025-06-17`
  - Web 界面：`/logs`（支持组件、时间范围、关键词过滤，分页展示）。
- 日志安全：敏感字段（如命令中的 API_KEY）在写入前自动脱敏（调用同一脱敏引擎，见第7节）。

**集成点**：
- 替换所有 `print()` 和 `logging.basicConfig` 为 `logger = StructuredLogger(name)`。
- 在关键函数入口/出口、异常捕获处使用 `logger.log(level, action, **details)`。
- 日志存储路径：`logs/hermes_YYYY-MM-DD.jsonl`。

**配置**：
```json
{
  "logging": {
    "format": "json",
    "level": "INFO",
    "rotation": {
      "daily": true,
      "max_days": 30,
      "compress": true
    },
    "trace_id_header": "X-Hermes-Trace"
  }
```

**风险评估**：
- **性能**：同步写入可能成为瓶颈，采用异步队列 + 批量写入（每秒或每 1000 条刷一次）。
- **存储**：JSON 比文本行略大，但在压缩后差异可接受。

---

### 7. 敏感信息脱敏（Sensitive Data Masking）
**目标**：在日志、记忆库、用户可见的输出中，对环境变量、密钥、令牌等敏感信息进行自动脱敏，防止泄露。

**设计要点**：
- 实现 `DataMasker` 单例，提供 `mask(text: str) -> str` 方法。
- 识别模式（正则）：
  - `Bearer\s+[A-Za-z0-9_\-]+`
  - `sk-[A-Za-z0-9]{48}`（OpenAI 密钥）
  - `ghp_[A-Za-z0-9]{36}`（GitHub Token）
  - `AKIA[0-9A-Z]{16}`（AWS Access Key）
  - 环境变量值：通过 `os.getenv` 读取时记录键名，对值脱敏（如 `API_KEY=***`）。
- 脱敏策略：替换为 `***` 或 `[REDACTED]`，在脱敏映射表（内存）中保存原始值以便内部使用（仅限必要场景）。
- 应用范围：
  - 结构化日志写入前调用 `masker.mask()`
  - 记忆库持久化前
  - Web 界面显示前（前端也可二次处理，但后端必须保证）
  - 错误堆栈（自动过滤敏感信息）

**配置**：
```json
{
  "masking": {
    "enabled": true,
    "patterns": [
      "Bearer\s+[A-Za-z0-9_\-]+",
      "sk-[A-Za-z0-9]{48}",
      "ghp_[A-Za-z0-9]{36}",
      "AKIA[0-9A-Z]{16}"
    ],
    "replacement": "[REDACTED]",
    "preserve_length": false
  }
```

**与日志系统集成**：
- 日志组件在序列化 JSON 前，对所有字符串字段（包括 nested）递归调用 `masker.mask()`。
- 提供脱敏统计：每日脱敏次数、避免的泄露风险字段，写入单独的 `logs/masking_stats.json`。

**风险评估**：
- **过度脱敏**：可能影响调试（日志不可读），提供 `DEBUG` 模式临时关闭脱敏（需认证）。
- **漏报**：需定期更新正则规则库，支持用户自定义规则。

---

### 实施优先级建议
1. **第1批**：运行日志机制（6）+ 敏感信息脱敏（7）——为其他功能提供审计与防护基础。
2. **第2批**：类防火墙机制（1）+ 操作审批机制（4）——核心拦截与决策能力。
3. **第3批**：执行环境隔离（3）+ 网络风险控制（2）——运行时环境加固。
4. **第4批**：异常行为检测（5）——需要前3批成熟后的数据与规则积累。

---

## 四象协作标准注入（已列入待实现）

### 功能概述
将四象（青龙、白虎、朱雀、玄武）协作标准写入 Agent 的系统提示，并生成 CODING_STANDARD.md 文档，指导 Agent 在生成代码、编写脚本时按四阶段执行，从而提升本地代码能力。

### 修改点
1. 在 `agent.py` 的 `_build_system_prompt` 方法中，在【行为规则】后增加【四象协作标准】章节，详细描述四阶段要求。
2. 创建 `CODING_STANDARD.md` 文档，提供四阶段实施指南、示例结构和注意事项。

### 实施步骤
- 修改 agent.py（对应系统提示字符串）。
- 写入 CODING_STANDARD.md。
- 运行验证：重启 Agent，检查系统提示是否包含标准章节。

### 风险评估
低：仅文本修改；不影响核心逻辑；若引发异常，只需回滚字符串变更。

