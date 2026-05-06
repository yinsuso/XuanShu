# 玄枢项目 配置参数文档

> 本文档自动生成，覆盖各阶段配置参数。

## 基础路径配置

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| _POTENTIAL_ROOTS | list | `[` |  |  |
| PROJECT_ROOT | str | `_root` |  |  |
| PROJECT_ROOT | str | `os.path.dirname(os.path.abspath(__file__))` |  |  |
| ALLOWED_DIR | str | `PROJECT_ROOT` |  |  |
| MEMORY_DB_PATH | str | `os.path.join(PROJECT_ROOT, "agent_memory.db")` |  |  |
## Ollama 配置

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| OLLAMA_BASE_URL | str | `http://localhost:11434` | OLLAMA_BASE_URL |  |
## 系统启动时将自动读取 data/model_config.json 中的当前配置。

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| MODEL_NAME | str | `os.getenv("MODEL_NAME", None)` | MODEL_NAME |  |
## 安全配置

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| MAX_CODE_EXECUTIONS | int | `10` |  |  |
| CODE_EXECUTION_TIMEOUT | int | `10` |  |  |
## Docker 沙箱配置（新增强）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| SANDBOX_ENABLED | bool | `true` | SANDBOX_ENABLED |  |
| SANDBOX_IMAGE | str | `python:3.10-slim` | SANDBOX_IMAGE |  |
| SANDBOX_CPU_LIMIT | str | `float(os.getenv("SANDBOX_CPU_LIMIT", 0.5))` | SANDBOX_CPU_LIMIT |  |
| SANDBOX_MEMORY_LIMIT | str | `256m` | SANDBOX_MEMORY_LIMIT |  |
| SANDBOX_TIMEOUT | str | `int(os.getenv("SANDBOX_TIMEOUT", 30))` | SANDBOX_TIMEOUT |  |
| SANDBOX_NETWORK_MODE | str | `none` | SANDBOX_NETWORK_MODE |  |
| SANDBOX_READ_ONLY | bool | `true` | SANDBOX_READ_ONLY |  |
| SANDBOX_TEMP_DIR | str | `os.getenv("SANDBOX_TEMP_DIR", os.path.join(PROJECT_ROOT, "tmp"))` | SANDBOX_TEMP_DIR |  |
## Docker 安全选项：如 ["no-new-privileges", "apparmor:unconfined"]

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| SANDBOX_SECURITY_OPTIONS | str | `no-new-privileges` | SANDBOX_SECURITY_OPTIONS |  |
## 网络访问控制配置

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| NETWORK_ENABLED | bool | `true` | NETWORK_ENABLED |  |
| NETWORK_DEFAULT_ACTION | str | `deny` | NETWORK_DEFAULT_ACTION | allow/deny |
## 域名白名单（逗号分隔列表）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| NETWORK_WHITELIST | str | `api.openai.com,ollama.local,huggingface.co` | NETWORK_WHITELIST |  |
| NETWORK_BLOCKED_DOMAINS | str | `metadata.google.internal,169.254.169.254` | NETWORK_BLOCKED_DOMAINS |  |
| NETWORK_BLOCKED_IPS | str | `169.254.169.254,100.100.100.200` | NETWORK_BLOCKED_IPS |  |
## 过滤空字符串，避免无效配置

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| NETWORK_WHITELIST | list | `[x for x in NETWORK_WHITELIST if x]` |  |  |
| NETWORK_BLOCKED_DOMAINS | list | `[x for x in NETWORK_BLOCKED_DOMAINS if x]` |  |  |
| NETWORK_BLOCKED_IPS | list | `[x for x in NETWORK_BLOCKED_IPS if x]` |  |  |
## 审批联动配置

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
## Web 审批服务地址（Agent 提交审批请求的目标）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| WEB_APP_URL | str | `http://localhost:8000` | WEB_APP_URL |  |
## 审批 API 共享令牌（用于 Agent ↔ Web 身份验证）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| APPROVAL_API_TOKEN | str | `change-me-to-secure-random` | APPROVAL_API_TOKEN |  |
## 审批等待超时（秒）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| APPROVAL_TIMEOUT | str | `int(os.getenv("APPROVAL_TIMEOUT", "60"))` | APPROVAL_TIMEOUT |  |
## 审批状态轮询间隔（秒）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| APPROVAL_POLL_INTERVAL | str | `int(os.getenv("APPROVAL_POLL_INTERVAL", "2"))` | APPROVAL_POLL_INTERVAL |  |
## 审批数据存储路径（SQLite）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| APPROVAL_DB_PATH | str | `os.getenv("APPROVAL_DB_PATH", os.path.join(PROJECT_ROOT, "data", "approvals.db"))` | APPROVAL_DB_PATH |  |
## Agent 配置

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| MAX_HISTORY_LENGTH | int | `20` |  |  |
| ENABLE_MEMORY | bool | `True` |  |  |
## Web界面配置（新增）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| WEB_HOST | str | `0.0.0.0` | WEB_HOST |  |
| WEB_PORT | str | `int(os.getenv("WEB_PORT", 30001))` | WEB_PORT |  |
| WEB_DEBUG | bool | `false` | WEB_DEBUG |  |
## 结构化日志配置（新增）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| LOG_LEVEL | str | `INFO` | LOG_LEVEL |  |
| LOG_FORMAT | str | `text` | LOG_FORMAT |  |
| LOG_FILE | str | `os.getenv("LOG_FILE", None)` | LOG_FILE |  |
## 日志轮转配置

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| LOG_ROTATION_DAYS | str | `int(os.getenv("LOG_ROTATION_DAYS", 30))` | LOG_ROTATION_DAYS | 保留天数 |
| LOG_COMPRESS | bool | `true` | LOG_COMPRESS | 是否压缩归档 |
| TRACE_ID_HEADER | str | `X-Hermes-Trace` | TRACE_ID_HEADER |  |
## 异步写入配置

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| LOG_ASYNC_QUEUE_SIZE | str | `int(os.getenv("LOG_ASYNC_QUEUE_SIZE", 1000))` | LOG_ASYNC_QUEUE_SIZE | 队列容量 |
| LOG_BATCH_SIZE | str | `int(os.getenv("LOG_BATCH_SIZE", 100))` | LOG_BATCH_SIZE | 批量写入条数 |
| LOG_FLUSH_INTERVAL | str | `float(os.getenv("LOG_FLUSH_INTERVAL", 1.0))` | LOG_FLUSH_INTERVAL | 刷盘间隔(秒) |
## 敏感信息脱敏配置（新增）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
## 是否启用脱敏

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| MASKING_ENABLED | bool | `true` | MASKING_ENABLED |  |
## 脱敏正则模式列表（按优先级顺序）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| MASKING_PATTERNS | list | `[` |  |  |
## 脱敏替换文本

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| MASKING_REPLACEMENT | str | `[REDACTED]` | MASKING_REPLACEMENT |  |
## 是否保留脱敏后长度（用于某些场景）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| MASKING_PRESERVE_LENGTH | bool | `false` | MASKING_PRESERVE_LENGTH |  |
## 脱敏统计文件路径

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| MASKING_STATS_PATH | str | `os.path.join(PROJECT_ROOT, "logs", "masking_stats.json")` |  |  |
| LOG_FILE_JSON | str | `LOG_FILE.replace(".log", "_json.log")` |  |  |
| LOG_FILE_JSON | str | `os.path.join(PROJECT_ROOT, "logs", "hermes.jsonl")` |  |  |
| LOG_FILE_JSON | str | `None` |  |  |
## 重试配置（新增）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| MAX_RETRIES | str | `int(os.getenv("MAX_RETRIES", 3))` | MAX_RETRIES |  |
| RETRY_DELAY | str | `float(os.getenv("RETRY_DELAY", 1.0))` | RETRY_DELAY |  |
## 记忆系统配置（新增）

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| USE_VECTOR_MEMORY | bool | `false` | USE_VECTOR_MEMORY |  |
| VECTOR_MODEL | str | `all-MiniLM-L6-v2` | VECTOR_MODEL |  |
## v4.0 进化功能配置

| 参数 | 类型 | 默认值 | 环境变量 | 说明 |
|------|------|--------|----------|------|
| ENABLE_EVOLUTION | bool | `false` | ENABLE_EVOLUTION |  |
| VERSION | str | `"5.3.0"` |  |  |
