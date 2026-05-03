# 玄枢 (XuanShu) 新功能规划文档

**版本**: v5.0 安全增强版  
**创建日期**: 2026-05-03  
**状态**: Planning  
**适用范围**: 玄枢本地 AI Agent 系统的安全加固与新功能开发

---

## 📖 目录

1. [项目背景](#项目背景)
2. [核心设计理念](#核心设计理念)
3. [7大新功能规划](#7大新功能规划)
4. [审计技能设计](#审计技能设计)
5. [倒推审查与安全攻防推敲结果](#倒推审查与安全攻防推敲结果)
6. [实施路线图](#实施路线图)
7. [验收标准](#验收标准)
8. [决策清单](#决策清单)
9. [附录](#附录)

---

## 项目背景

玄枢（XuanShu）是一个**本地优先、内网隔离**的 AI Agent 系统，旨在为用户提供安全、可控、自进化的智能助手服务。

随着功能扩展和用户增长，现有架构在**安全性、隔离性、审计能力**方面存在明显短板：

### 当前安全短板
1. **代码执行无沙箱** - 技能直接在主机进程运行，存在命令注入风险
2. **路径遍历风险** - 文件操作未严格校验路径
3. **API 密钥明文存储** - 配置文件未加密
4. **日志脱敏不完整** - 部分日志未脱敏
5. **缺乏审批机制** - 高危操作无用户确认
6. **无网络隔离** - 可访问外网和内网元数据
7. **无系统调用监控** - 无法检测异常行为
8. **集群功能缺陷** - 加入房间功能未实现

### 审计能力缺失
- 缺少系统化的**前后端一致性检查**机制
- 缺少**安全攻防推敲**流程
- 缺少大型项目的**代码质量审计工具**

---

## 核心设计理念

### 安全原则（零信任）
- **最小权限** - 每个技能仅拥有必要权限
- **用户可控** - 所有高危操作需人工或策略审批
- **审计一切** - 所有操作记录可追溯
- **隔离运行** - 代码执行在独立环境

### 架构哲学（减法思维）
- **渐进式加固** - 不破坏现有架构，通过模块化增量增强
- **向后兼容** - 新旧 API 平滑过渡
- **可配置化** - 安全策略通过配置文件控制

### 用户体验平衡
- 安全性 vs 便利性
- 自动审批 vs 人工确认
- 性能开销 vs 隔离程度

---

## 7大新功能规划

### 🚨 功能 1: 类防火墙机制（前置扫描 + 审批）

#### 功能描述
在终端命令/技能执行前进行风险扫描，识别潜在注入攻击、密钥泄露等风险，并根据策略决定是否执行。

#### 用户价值
- 防止恶意技能执行破坏系统
- 保护敏感信息不被泄露
- 用户对高危操作有完全控制权

#### 技术设计
```python
# security/firewall.py
class FirewallScanner:
    def scan(self, skill_name: str, args: dict) -> ScanResult:
        """扫描技能调用的风险"""
        # 1. 参数注入检测（SQL、命令、路径遍历）
        # 2. 敏感信息识别（密钥、token、个人信息）
        # 3. 风险评估（基于技能类型和历史行为）
        return ScanResult(risk_level, reasons)
```

**风险等级判定规则**：
- 🔴 **Critical**: `rm -rf`, `dd`, `mkfs` 等破坏性命令
- 🟡 **High**: 文件删除、网络访问、环境变量读取
- 🟢 **Medium**: 文件写入、外部 API 调用
- ⚪ **Low**: 纯计算、读取白名单文件

#### 审批流程
```python
# security/approval.py
class ApprovalManager:
    def request_approval(self, skill_name, args, risk_level):
        if risk_level == "critical":
            return ApprovalMode.MANUAL  # 必须人工确认
        elif risk_level == "high":
            return ApprovalMode.PROMPT  # 弹窗询问
        else:
            return ApprovalMode.AUTO    # 自动放行
```

**审批渠道**：
- Web 界面弹窗（实时）
- 命令行输入（交互模式）
- 配置文件白名单（自动）

#### 实施步骤
1. 设计风险评估引擎（3天）
2. 实现参数注入检测（2天）
3. 集成审批流程（3天）
4. Web 界面审批组件（2天）
5. 测试与调优（2天）

---

### 🌐 功能 2: 网络风险控制

#### 功能描述
防止 Agent 被利用攻击内网或访问元数据服务（如 AWS metadata、GCP metadata）。

#### 用户价值
- 保护内网安全，防止横向移动
- 避免云环境元数据泄露
- 满足企业合规要求

#### 技术设计
**方案A: 容器网络隔离（推荐）**
- Docker 容器运行所有代码执行
- 使用 `--network none` 禁用网络
- 特定域名白名单（如 `api.openai.com`）
- 使用 `--add-host` 重写恶意域名

**方案B: eBPF 监控（高级）**
- 挂载 eBPF 程序监控所有网络连接
- 拦截到 `169.254.169.254` (AWS metadata) 的连接
- 实时告警并阻断

**实施方案（渐进）**：
```python
# Phase 1: 静态规则过滤
BLOCKED_DOMAINS = [
    "169.254.169.254",  # AWS metadata
    "metadata.google.internal",  # GCP
    "100.100.100.200",  # Alibaba Cloud
]

# Phase 2: Docker 网络命名空间
docker run --network none ...

# Phase 3: eBPF 深度监控（可选）
```

#### 配置示例
```json
{
  "network_policy": {
    "default_action": "deny",
    "allowed_domains": ["api.openai.com", "ollama.local"],
    "blocked_ips": ["169.254.169.254"],
    "max_connections_per_minute": 60
  }
}
```

#### 实施步骤
1. 网络访问监控实现（3天）
2. Docker 默认无网络隔离（2天）
3. 域名/IP 白名单配置（1天）
4. 云元数据防护规则（1天）
5. 高级 eBPF（可选，2周）

---

### 🐳 功能 3: 执行环境隔离（Docker）

#### 功能描述
所有技能代码在独立的 Docker 容器中执行，实现资源隔离和权限控制。

#### 用户价值
- 防止恶意代码破坏宿主机
- 资源限制（CPU、内存、磁盘）
- 干净的运行环境，避免污染
- 便于审计和清理

#### 技术设计
```python
# security/sandbox.py
class DockerSandbox:
    def execute(self, code: str, skill_name: str, args: dict):
        """在 Docker 容器中执行代码"""
        container = self.docker_client.containers.run(
            image="python:3.10-slim",
            command=f"python -c '{code}'",
            # 安全配置
            network_mode="none",      # 禁用网络
            read_only=True,           # 只读文件系统
            mem_limit="256m",         # 内存限制
            cpu_period=100000,
            cpu_quota=50000,          # 50% CPU
            # 挂载临时目录
            volumes={
                self.temp_dir: {'bind': '/tmp', 'mode': 'rw'}
            },
            # 安全配置
            security_opt=[
                "no-new-privileges",   # 不提升权限
                "apparmor:unconfined"  # 或自定义 AppArmor 配置
            ],
            # 超时控制
            remove=True  # 执行后自动删除
        )
        return container.logs().decode()
```

**容器镜像优化**：
```dockerfile
FROM python:3.10-slim
RUN pip install --no-cache-dir numpy pandas  # 预装常用库
WORKDIR /app
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

**资源限制配置**：
```yaml
sandbox:
  cpu_limit: 0.5     # 50% CPU
  memory_limit: 256m # 256MB RAM
  disk_limit: 1g     # 1GB 临时存储
  timeout: 30s       # 执行超时
  max_file_size: 10m # 最大文件操作
```

#### 性能优化
- 使用 Docker 镜像缓存，避免每次拉取
- 容器池化（预热几个空闲容器）
- 只挂载必要的目录，减少开销

#### 实施步骤
1. 设计 Docker 封装器（2天）
2. 创建安全容器镜像（1天）
3. 资源限制与超时（1天）
4. 文件系统隔离（1天）
5. 性能测试与优化（2天）

---

### ✅ 功能 4: 操作审批机制

#### 功能描述
支持**手动审批**、**智能自动**、**拒绝**三种模式，用户对高危操作有最终决定权。

#### 用户价值
- 透明化：所有操作可见
- 可控性：可随时阻断风险
- 智能化：安全且便捷

#### 技术设计
```python
# security/approval.py
class ApprovalWorkflow:
    def request(self, operation, context):
        """
        请求审批
        
        Args:
            operation: 操作名称（技能名）
            context: 上下文（参数、风险等级）
        
        Returns:
            ApprovalDecision (approve/reject/pending)
        """
        policy = self.get_policy(operation)
        
        if policy.mode == "manual":
            return self.manual_approval(operation, context)
        elif policy.mode == "auto":
            return self.auto_approval(operation, context)
        else:  # reject
            return ApprovalDecision(rejected=True, reason="策略拒绝")
```

**审批策略配置**：
```json
{
  "approval_policies": {
    "file_write": {"mode": "manual", "confirm_message": "将写入文件，确定吗？"},
    "shell_exec": {"mode": "manual", "require_reason": true},
    "web_fetch": {"mode": "auto"},
    "dangerous_skills": {"mode": "reject"}
  }
}
```

**Web 界面审批组件**：
```html
<!-- 审批弹窗 -->
<div class="approval-modal">
  <h3>⚠️ 需要确认</h3>
  <p>{{ operation }}</p>
  <p>参数: {{ args }}</p>
  <p>风险: {{ risk_level }}</p>
  <button onclick="approve()">允许</button>
  <button onclick="reject()">拒绝</button>
  <button onclick="always_allow()">始终允许</button>
</div>
```

#### 审批渠道
1. **Web 实时弹窗**（默认）
2. **命令行交互**（CLI 模式）
3. **静默自动**（配置文件白名单）

#### 实施步骤
1. 审批策略引擎（2天）
2. Web 审批组件（2天）
3. CLI 审批交互（1天）
4. 审批历史记录（1天）
5. 白名单管理（1天）

---

### 📊 功能 5: 异常行为检测

#### 功能描述
实时监测异常的系统调用和文件访问模式，识别潜在攻击行为。

#### 用户价值
- 早期威胁检测
- 自动化安全响应
- 满足合规审计要求

#### 技术设计
**监控指标**：
- 短时间内大量文件删除
- 访问敏感路径（`/etc/passwd`, `~/.ssh/`）
- 异常网络连接（外网IP、非标端口）
- 系统调用异常（`ptrace`, `mount`）

**检测规则**：
```python
# security/anomaly_detector.py
class AnomalyDetector:
    RULES = [
        {
            "name": "大量文件删除",
            "condition": "count(file_delete) > 10 within 60s",
            "severity": "high"
        },
        {
            "name": "敏感文件访问",
            "condition": "file_path startswith('/etc/') or file_path contains('.ssh')",
            "severity": "critical"
        },
        {
            "name": "出网连接",
            "condition": "network_connection and not domain in whitelist",
            "severity": "medium"
        }
    ]
```

**告警与响应**：
```python
def on_anomaly(event, rule):
    logger.warning(f"异常行为: {rule['name']}", details=event)
    if rule['severity'] == "critical":
        # 立即阻断
        sandbox.kill_container(event.container_id)
        notify_admin(f"高危异常: {event}")
```

#### 实施阶段
- **Phase 1**: 文件操作监控（3天）
- **Phase 2**: 网络连接监控（2天）
- **Phase 3**: 系统调用审计（3天，需 eBPF）
- **Phase 4**: 机器学习异常检测（可选）

#### 实施步骤
1. 系统调用拦截设计（3天）
2. 文件/网络监控实现（3天）
3. 规则引擎（2天）
4. 告警与响应（2天）
5. 误报优化（持续）

---

### 📝 功能 6: 运行日志机制（增强）

#### 功能描述
完善结构化日志系统，支持实时查看、搜索、分析，便于快速定位问题。

#### 现有基础
- ✅ 已有 JSON 结构化日志
- ✅ 异步批量写入
- ✅ 自动轮转与压缩
- ✅ Trace ID 跨组件追踪

#### 增强需求
1. **Web 日志查看器**
   - 实时 tail 日志流
   - 按级别、组件、时间筛选
   - 搜索功能（关键词、正则）

2. **日志分析仪表盘**
   - 错误频率统计
   - 异常模式识别
   - Token 使用趋势（已存在）

3. **日志轮转策略增强**
   - 按大小+时间双重轮转
   - 远程日志转发（可选）

#### 实施步骤
1. Web 日志查看器（2天）
2. 日志搜索 API（1天）
3. 仪表盘增强（2天）
4. 配置优化（1天）

---

### 🛡️ 功能 7: 敏感信息脱敏（扩展）

#### 功能描述
对所有日志、API 响应、记忆存储中的敏感信息（API keys、Bearer tokens、环境变量）进行自动脱敏。

#### 现有基础
- ✅ `data_masker.py` 已实现基础正则脱敏
- ✅ 支持常见密钥模式
- ✅ 统计追踪

#### 增强需求
1. **扩展脱敏模式库**
   - 新增 JWT tokens
   - 新增 GitHub/GitLab tokens
   - 新增数据库连接字符串
   - 新增证书指纹

2. **上下文感知脱敏**
   - 仅对日志脱敏，保留技能执行时的原始参数（用于调试）
   - 预览模式（审计员可以看到脱敏前后对比）

3. **性能优化**
   - 预编译正则（已实现）
   - 增量统计（已实现）

4. **JSON 结构化脱敏**（已存在，需确保全覆盖）

#### 扩展的脱敏正则
```python
MASKING_PATTERNS = [
    # 现有
    r"Bearer\s+[A-Za-z0-9_\-]+",
    r"sk-[A-Za-z0-9]{48}",  # OpenAI
    r"ghp_[A-Za-z0-9]{36}", # GitHub
    
    # 新增
    r"eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{20,}",  # JWT
    r"AIza[0-9A-Za-z\\-_]{35}",  # Google API Key
    r"AKIA[0-9A-Z]{16}",  # AWS Access Key (已有)
    r"xoxb-[0-9]{12}-[0-9]{12}-[0-9A-Za-z]+",  # Slack Bot Token
    r"mongodb://[^:]+:[^@]+@",  # MongoDB connection string
]
```

#### 实施步骤
1. 扩展正则库（1天）
2. 上下文感知（1天）
3. 性能测试（1天）
4. 文档更新（0.5天）

---

## 审计技能设计

### 技能名称
`project_security_audit`

### 技能触发条件
当需要对大型项目进行**安全审计**、**前后端一致性验证**、**代码质量检查**时使用。

### 技能参数
| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| `project_root` | string | ✅ | 项目根目录绝对路径 |
| `output_format` | string | ❌ | 输出格式：`markdown` 或 `json`（默认 markdown） |
| `audit_scope` | array | ❌ | 审计范围：`["frontend"]`, `["backend"]`, `["security"]`, `["all"]`（默认） |

### 审计内容

#### 1. 前端审计
- 扫描 `web/templates/` 和 `web/static/` 文件
- 提取所有 HTML 页面
- 分析 JavaScript 中的 API 调用（`fetch`, `axios`）
- 生成前端使用的 API 端点清单

#### 2. 后端审计
- 扫描 Python 文件，提取 FastAPI/Flask 路由
- 检查 API 实现是否存在
- 验证参数处理是否正确
- 检查错误处理是否完善

#### 3. 安全攻防推敲
- **代码执行风险**：扫描 `eval`, `exec`, `os.system`, `subprocess`
- **API 密钥泄露**：检查 `model_config.json`, `.env` 是否明文
- **路径遍历**：文件操作是否校验路径
- **日志脱敏**：是否全流程脱敏
- **速率限制**：是否疏漏 Дета
- **SQL 注入**：检查参数化查询使用情况

#### 4. 依赖关系审计
- 提取 `requirements.txt` / `pyproject.toml`
- 分析 Python 文件的导入关系
- 检测潜在的循环依赖

#### 输出报告
生成的报告包含：
- ✅ **风险评估摘要**（整体风险等级）
- ✅ **前端分析**（页面、API 使用）
- ✅ **后端分析**（端点实现）
- ✅ **安全漏洞清单**（带修复建议）
- ✅ **依赖分析**（第三方库、循环依赖）
- ✅ **问题汇总**（按严重程度排序）
- ✅ **建议行动计划**

### 使用示例
```bash
# 在玄枢 CLI 中调用
/run project_security_audit project_root="/path/to/project"

# 指定输出格式
/run project_security_audit project_root="/path/to/project" output_format="json"

# 仅审计安全部分
/run project_security_audit project_root="/path/to/project" audit_scope=["security"]
```
---

## 实施路线图

### Phase 0: 立即修复（本周）
- [ ] 修复集群加入功能 bug（1小时）
- [ ] 创建安全技能审计框架（已完成）
- [ ] 完成安全加固设计评审（1天）

### Phase 1: 安全基石（2周）
- [ ] **路径校验** - 所有文件操作严格校验路径（3天）
- [ ] **Docker 隔离** - 实现代码执行容器化（5天）
- [ ] **防火墙扫描** - 技能执行前风险扫描（5天）
- [ ] **密钥加密** - 使用系统密钥库存储 API keys（3天）
- [ ] **日志脱敏全覆盖** - 确保所有输出通道脱敏（2天）

### Phase 2: 审批控制（1周）
- [ ] 审批策略引擎（3天）
- [ ] Web 审批界面（2天）
- [ ] CLI 审批交互（1天）
- [ ] 白名单与历史记录（1天）

### Phase 3: 运维增强（2周）
- [ ] 速率限制（1天）
- [ ] 集群安全加固（TLS + 认证）（3天）
- [ ] 异常行为检测（文件/网络监控）（5天）
- [ ] 审计日志增强（2天）

### Phase 4: 智能优化（1周）
- [ ] 自动审批策略（ML 评分）（3天）
- [ ] 风险画像（用户/技能画像）（2天）
- [ ] 告警与通知（1天）

### Phase 5: 高级防护（可选）
- [ ] eBPF 深度监控（2周）
- [ ] 自动应急响应（1周）
- [ ] 零知识证明（研究）

---

## 验收标准

### 功能验收

#### 功能 1: 防火墙机制
- [ ] 高风险技能执行前必须弹窗确认
- [ ] 参数包含 `rm -rf` 时自动拦截
- [ ] API key 出现在参数中时自动脱敏
- [ ] 白名单技能自动放行

#### 功能 2: 网络风险控制
- [ ] 默认容器无网络访问权限
- [ ] 访问 `169.254.169.254` 被自动阻断
- [ ] 外网调用需白名单批准
- [ ] 网络请求记录到审计日志

#### 功能 3: 执行环境隔离
- [ ] 所有技能在独立容器运行
- [ ] 容器内存限制 256MB
- [ ] 只读文件系统（除 `/tmp`）
- [ ] 执行超时 30 秒自动终止

#### 功能 4: 操作审批
- [ ] 审批记录可查询
- [ ] 支持"始终允许"白名单
- [ ] CLI 和 Web 双渠道审批
- [ ] 审批超时自动拒绝（可配置）

#### 功能 5: 异常行为检测
- [ ] 10 秒内删除 5+ 文件触发告警
- [ ] 访问 `/etc/` 敏感路径记录
- [ ] 异常行为邮件/界面通知

#### 功能 6: 运行日志机制
- [ ] Web 日志查看器可实时 tail
- [ ] 支持按级别、时间搜索
- [ ] 日志文件自动压缩归档

#### 功能 7: 敏感信息脱敏
- [ ] JWT token 自动识别脱敏
- [ ] 数据库连接字符串脱敏
- [ ] 脱敏统计可查询

### 安全验收
- [ ] 通过 **倒推审查** 工具无 Critical 漏洞
- [ ] 通过 **网络安全攻防推敲** 无高危风险
- [ ] 所有 API 端点都有 WAF 防护
- [ ] 完成渗透测试（可选）

### 性能验收
- [ ] 技能执行延迟 < 500ms（不包括模型推理）
- [ ] Web 页面加载 < 2s
- [ ] 数据库查询 < 100ms
- [ ] 日志写入不影响主流程

### 用户体验验收
- [ ] 新用户 10 分钟内完成部署
- [ ] 高危操作弹窗清晰说明风险
- [ ] 审批流程不超过 3 步
- [ ] 提供详细操作手册

---

## 决策清单（开工前需确认）

### 1. 安全合规
- [ ] 是否需要满足等保/ISO27001 要求？
- [ ] 数据保留策略是什么？（日志保存 90 天？）
- [ ] 是否需要加密所有存储数据？（at-rest encryption）

### 2. 部署环境
- [ ] 操作系统：Windows / macOS / Linux？（密钥库选择）
- [ ] Docker 是否已安装并可用？
- [ ] 是否需要支持无 Docker 模式？（降级方案）

### 3. 用户体验取舍
- [ ] 每次高危操作都弹窗？还是提供"始终允许"选项？
- [ ] 自动审批的阈值是什么？（基于什么评分？）
- [ ] 是否允许用户自定义风险策略？

### 4. 资源投入
- [ ] 预计多少人月？（当前规划约 8-10 人周）
- [ ] 是否引入专业安全审计服务？
- [ ] 测试环境何时准备就绪？

### 5. 性能与兼容性
- [ ] 可接受的 Docker 开销？（当前 ~200-500ms）
- [ ] 是否支持 ARM 架构？（Mac M1/M2）
- [ ] 最低硬件要求？（内存、CPU）

---

## 附录

### A. API 端点完整清单

| 端点 | 方法 | 功能 | 风险等级 | 审批需求 |
|------|------|------|----------|----------|
| `/api/chat` | POST | 对话 | Medium | 否 |
| `/api/export` | GET | 导出 | Low | 否 |
| `/api/memory` | GET | 读取记忆 | Low | 否 |
| `/api/token-stats` | GET | 统计 | Low | 否 |
| `/api/models` | GET | 模型列表 | Low | 否 |
| `/api/switch_model` | POST | 切换模型 | Medium | 否 |
| `/api/save_model` | POST | 保存配置 | Medium | 否（API key 脱敏） |
| `/api/delete_model` | POST | 删除配置 | High | 确认弹窗 |
| `/api/cluster/create` | POST | 创建房间 | Medium | 否 |
| `/api/cluster/join` | POST | 加入房间 | Medium | 否 |
| `/api/cluster/status` | GET | 状态查询 | Low | 否 |

### B. 文件操作技能清单（需沙箱）

| 技能名 | 描述 | 风险等级 | 建议隔离 |
|--------|------|----------|----------|
| `read_file` | 读取文件 | Medium | ✅ |
| `write_file` | 写入文件 | High | ✅ |
| `edit_file` | 编辑文件 | High | ✅ |
| `delete_file` | 删除文件 | Critical | ✅ |
| `list_directory` | 列目录 | Low | 可选 |
| `search_files` | 搜索文件 | Medium | 可选 |

### C. 审计技能快速参考

```bash
# 完整审计
python -c "from skills.audit.project_security_audit import execute; print(execute('/path/to/project'))"

# 只审计安全部分
execute(project_root='/path', audit_scope=['security'])

# JSON 输出
execute(project_root='/path', output_format='json')
```

### D. 术语表

- **倒推审查**：从前端页面开始，逐层向后端追溯，确保每个功能都有完整实现
- **四象协作**：青龙（架构）、白虎（规范）、朱雀（验证）、玄武（审核）
- **零信任**：默认不信任任何操作，每个请求都验证
- **沙箱**：隔离的执行环境，限制资源访问
- **WAF**：Web Application Firewall

---

## 维护计划

- **每周**：运行 `project_security_audit` 技能，检查新代码
- **每月**：更新脱敏正则库
- **每季度**：进行完整渗透测试
- **每年**：评估新的安全威胁，更新策略

---

**Document End**  
*本文档将持续更新，作为玄枢安全开发的指导性文件。*
