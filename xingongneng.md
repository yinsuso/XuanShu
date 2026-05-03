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

## 四象协作标准注入

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
