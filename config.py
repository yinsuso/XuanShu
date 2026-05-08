     1|import os
     2|from typing import Optional
     3|
     4|# =============================================================================
     5|# 基础路径配置
     6|# =============================================================================
     7|
     8|# 项目根目录：项目的根路径，用于构建其他相对路径
     9|# 使用多级 fallback 确保跨平台兼容性
    10|_POTENTIAL_ROOTS = [
    11|    os.path.dirname(os.path.abspath(__file__)),  # 当前文件所在目录
    12|    os.getcwd(),  # 当前工作目录
    13|    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'),  # 父目录
    14|]
    15|
    16|# 选择第一个存在的目录作为 PROJECT_ROOT
    17|for _root in _POTENTIAL_ROOTS:
    18|    if os.path.isdir(_root):
    19|        PROJECT_ROOT = _root
    20|        break
    21|else:
    22|    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    23|
    24|# 调试：记录项目根目录
    25|import sys
    26|print(f"[CONFIG] 项目根目录: {PROJECT_ROOT}", file=sys.stderr)
    27|
    28|# 允许操作的目录：Agent只能在这个目录及其子目录下进行文件操作，防止路径越权
    29|ALLOWED_DIR = PROJECT_ROOT
    30|
    31|# 内存数据库路径：用于存储对话历史和反思记录的SQLite数据库文件位置
    32|MEMORY_DB_PATH = os.path.join(PROJECT_ROOT, "agent_memory.db")
    33|
    34|# =============================================================================
    35|# 端口统一管理
    36|# =============================================================================
    37|
    38|# Web服务端口（统一入口）
    39|PORT_WEB = int(os.getenv("WEB_PORT", 30000))
    40|
    41|# 集群管理端口（Manager监听）
    42|PORT_CLUSTER_MANAGER = int(os.getenv("CLUSTER_MANAGER_PORT", 30001))
    43|
    44|# 集群Worker API端口
    45|PORT_CLUSTER_API = int(os.getenv("CLUSTER_API_PORT", 30002))
    46|
    47|# =============================================================================
    48|# Ollama 配置
    49|# =============================================================================
    50|
    51|# Ollama 服务地址：本地 Ollama 服务的基础 URL，默认为 localhost 的 11434 端口
    52|# 可以通过环境变量 OLLAMA_BASE_URL 覆盖
    53|OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    54|
    55|# 模型名称：使用的 Ollama 模型名称
    56|# ⚠️ 重要：此处不再设置默认值！
    57|# 系统启动时将自动读取 data/model_config.json 中的当前配置。
    58|# 若环境变量 MODEL_NAME 存在，仅作为 fallback（极少使用），否则为 None。
    59|MODEL_NAME = os.getenv("MODEL_NAME", None)
    60|
    61|# =============================================================================
    62|# 安全配置
    63|# =============================================================================
    64|
    65|# 最大代码执行次数：单次对话中允许执行代码的最大次数，防止无限循环执行
    66|MAX_CODE_EXECUTIONS = 10
    67|
    68|# 代码执行超时时间：单次代码执行的超时时间（秒），防止长时间阻塞
    69|CODE_EXECUTION_TIMEOUT = 10
    70|
    71|# =============================================================================
    72|# Docker 沙箱配置（新增强）
    73|# =============================================================================
    74|
    75|# 是否启用 Docker 沙箱执行（若 False 则降级到 subprocess 模式）
    76|SANDBOX_ENABLED = os.getenv("SANDBOX_ENABLED", "true").lower() == "true"
    77|
    78|# 沙箱 Docker 镜像：使用轻量级 Python 镜像
    79|SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "python:3.10-slim")
    80|
    81|# CPU 限制：0.0-1.0，表示 CPU 核心数的比例
    82|SANDBOX_CPU_LIMIT = float(os.getenv("SANDBOX_CPU_LIMIT", 0.5))
    83|
    84|# 内存限制：Docker 格式（如 "256m", "512m"）
    85|SANDBOX_MEMORY_LIMIT = os.getenv("SANDBOX_MEMORY_LIMIT", "256m")
    86|
    87|# 执行超时：秒
    88|SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", 30))
    89|
    90|# 网络模式："none"（无网络）、"host"（共享主机）、"bridge"（桥接）等
    91|SANDBOX_NETWORK_MODE = os.getenv("SANDBOX_NETWORK_MODE", "none")
    92|
    93|# 文件系统只读：只在 /tmp 可写
    94|SANDBOX_READ_ONLY = os.getenv("SANDBOX_READ_ONLY", "true").lower() == "true"
    95|
    96|# 宿主机临时目录：用于挂载到容器 /tmp
    97|SANDBOX_TEMP_DIR = os.getenv("SANDBOX_TEMP_DIR", os.path.join(PROJECT_ROOT, "tmp"))
    98|
    99|# Docker 安全选项：如 ["no-new-privileges", "apparmor:unconfined"]
   100|SANDBOX_SECURITY_OPTIONS = os.getenv("SANDBOX_SECURITY_OPTIONS", "no-new-privileges").split(",") if os.getenv("SANDBOX_SECURITY_OPTIONS") else ["no-new-privileges"]
   101|
   102|# =============================================================================
   103|# 网络访问控制配置
   104|# =============================================================================
   105|
   106|# 是否启用网络访问控制
   107|NETWORK_ENABLED = os.getenv("NETWORK_ENABLED", "true").lower() == "true"
   108|
   109|# 默认操作：当不匹配任何规则时的行为
   110|NETWORK_DEFAULT_ACTION = os.getenv("NETWORK_DEFAULT_ACTION", "deny")  # allow/deny
   111|
   112|# 域名白名单（逗号分隔列表）
   113|NETWORK_WHITELIST = os.getenv("NETWORK_WHITELIST", "api.openai.com,ollama.local,huggingface.co").split(",") if os.getenv("NETWORK_WHITELIST") else ["api.openai.com", "ollama.local", "huggingface.co"]
   114|
   115|# 域名黑名单
   116|NETWORK_BLOCKED_DOMAINS = os.getenv("NETWORK_BLOCKED_DOMAINS", "metadata.google.internal,169.254.169.254").split(",") if os.getenv("NETWORK_BLOCKED_DOMAINS") else ["metadata.google.internal", "169.254.169.254"]
   117|
   118|# IP 黑名单
   119|NETWORK_BLOCKED_IPS = os.getenv("NETWORK_BLOCKED_IPS", "169.254.169.254,100.100.100.200").split(",") if os.getenv("NETWORK_BLOCKED_IPS") else ["169.254.169.254", "100.100.100.200"]
   120|
   121|# 过滤空字符串，避免无效配置
   122|NETWORK_WHITELIST = [x for x in NETWORK_WHITELIST if x]
   123|NETWORK_BLOCKED_DOMAINS = [x for x in NETWORK_BLOCKED_DOMAINS if x]
   124|NETWORK_BLOCKED_IPS = [x for x in NETWORK_BLOCKED_IPS if x]
   125|
   126|# =============================================================================
   127|# 审批联动配置
   128|# =============================================================================
   129|
   130|# Web 审批服务地址（Agent 提交审批请求的目标）
   131|WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:8000")
   132|
   133|# 审批 API 共享令牌（用于 Agent ↔ Web 身份验证）
   134|APPROVAL_API_TOKEN = os.getenv("APPROVAL_API_TOKEN", "change-me-to-secure-random")
   135|
   136|# 审批等待超时（秒）
   137|APPROVAL_TIMEOUT = int(os.getenv("APPROVAL_TIMEOUT", "60"))
   138|
   139|# 审批状态轮询间隔（秒）
   140|APPROVAL_POLL_INTERVAL = int(os.getenv("APPROVAL_POLL_INTERVAL", "2"))
   141|
   142|# 审批数据存储路径（SQLite）
   143|APPROVAL_DB_PATH = os.getenv("APPROVAL_DB_PATH", os.path.join(PROJECT_ROOT, "data", "approvals.db"))
   144|
   145|# =============================================================================
   146|# Agent 配置
   147|# =============================================================================
   148|
   149|# 最大历史长度：保留的对话历史消息数量，用于上下文管理
   150|MAX_HISTORY_LENGTH = 20
   151|
   152|# 是否启用记忆系统：控制是否使用SQLite数据库存储对话历史和反思
   153|ENABLE_MEMORY = True
   154|
   155|# =============================================================================
   156|# Web界面配置（新增）
   157|# =============================================================================
   158|
   159|# Web服务主机：Web界面监听的主机地址
   160|WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
   161|
   162|# Web服务端口：Web界面监听的端口（统一使用PORT_WEB）
   163|WEB_PORT = PORT_WEB
   164|
   165|# 是否启用调试模式：控制Web应用是否以调试模式运行
   166|WEB_DEBUG = os.getenv("WEB_DEBUG", "false").lower() == "true"
   167|
   168|# =============================================================================
   169|# 结构化日志配置（新增）
   170|# =============================================================================
   171|
   172|# 日志级别：控制日志输出的详细程度
   173|# 可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL
   174|LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
   175|
   176|# 日志格式："text"（传统格式）或 "json"（结构化JSON行）
   177|LOG_FORMAT = os.getenv("LOG_FORMAT", "text")
   178|
   179|# 日志文件路径：日志文件的存储位置，None表示只输出到控制台
   180|LOG_FILE = os.getenv("LOG_FILE", None)
   181|
   182|# 日志轮转配置
   183|LOG_ROTATION_DAYS = int(os.getenv("LOG_ROTATION_DAYS", 30))  # 保留天数
   184|LOG_COMPRESS = os.getenv("LOG_COMPRESS", "true").lower() == "true"  # 是否压缩归档
   185|
   186|# Trace ID 请求头名称：用于跨组件追踪
   187|TRACE_ID_HEADER = os.getenv("TRACE_ID_HEADER", "X-Hermes-Trace")
   188|
   189|# 异步写入配置
   190|LOG_ASYNC_QUEUE_SIZE = int(os.getenv("LOG_ASYNC_QUEUE_SIZE", 1000))  # 队列容量
   191|LOG_BATCH_SIZE = int(os.getenv("LOG_BATCH_SIZE", 100))  # 批量写入条数
   192|LOG_FLUSH_INTERVAL = float(os.getenv("LOG_FLUSH_INTERVAL", 1.0))  # 刷盘间隔(秒)
   193|
   194|# =============================================================================
   195|# 敏感信息脱敏配置（新增）
   196|# =============================================================================
   197|
   198|# 是否启用脱敏
   199|MASKING_ENABLED = os.getenv("MASKING_ENABLED", "true").lower() == "true"
   200|
   201|# 脱敏正则模式列表（按优先级顺序）
   202|MASKING_PATTERNS = [
   203|    r"Bearer\s+[A-Za-z0-9_\-]+",  # Bearer tokens
   204|    r"sk-[A-Za-z0-9]{48}",  # OpenAI keys
   205|    r"ghp_[A-Za-z0-9]{36}",  # GitHub tokens
   206|    r"AKIA[0-9A-Z]{16}",  # AWS Access Keys
   207|    r"\$[A-Za-z_]\w*",  # 环境变量引用（$VAR 或 ${VAR} 的简化版）
   208|        r"glpat-[0-9a-zA-Z_-]{20}",  # GitLab tokens
   209|        r"eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{20,}",  # JWT tokens
   210|        r"AIza[0-9A-Za-z_-]{35}",  # Google API Keys
   211|        r"xoxb-[0-9]{12}-[0-9]{12}-[0-9A-Za-z]+",  # Slack Bot Tokens
   212|        r"mongodb://[^:@]+:[^:@]*@[^:@]+",  # MongoDB connection strings
   213|]
   214|
   215|# 脱敏替换文本
   216|MASKING_REPLACEMENT = os.getenv("MASKING_REPLACEMENT", "[REDACTED]")
   217|
   218|# 是否保留脱敏后长度（用于某些场景）
   219|MASKING_PRESERVE_LENGTH = os.getenv("MASKING_PRESERVE_LENGTH", "false").lower() == "true"
   220|
   221|# 脱敏统计文件路径
   222|MASKING_STATS_PATH = os.path.join(PROJECT_ROOT, "logs", "masking_stats.json")
   223|
   224|# =============================================================================
   225|# 日志文件路径（增强）
   226|# =============================================================================
   227|
   228|# 结构化日志文件路径（覆盖 LOG_FILE，若 LOG_FORMAT=json）
   229|if LOG_FORMAT == "json":
   230|    if LOG_FILE:
   231|        LOG_FILE_JSON = LOG_FILE.replace(".log", "_json.log")
   232|    else:
   date_str = datetime.datetime.now().strftime("%Y%m%d")
   LOG_FILE_JSON = os.path.join(PROJECT_ROOT, "logs", f"{date_str}.jsonl")
   234|else:
   235|    LOG_FILE_JSON = None
   236|
   237|# =============================================================================
   238|# 重试配置（新增）
   239|# =============================================================================
   240|
   241|# 最大重试次数：Ollama请求失败时的最大重试次数
   242|MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
   243|
   244|# 重试延迟（秒）：重试之间的等待时间，使用指数退避
   245|RETRY_DELAY = float(os.getenv("RETRY_DELAY", 1.0))
   246|
   247|# =============================================================================
   248|# 记忆系统配置（新增）
   249|# =============================================================================
   250|
   251|# 是否启用向量搜索：需要安装chromadb和sentence-transformers
   252|USE_VECTOR_MEMORY = os.getenv("USE_VECTOR_MEMORY", "false").lower() == "true"
   253|
   254|# 向量模型名称：用于生成记忆嵌入的模型
   255|VECTOR_MODEL = os.getenv("VECTOR_MODEL", "all-MiniLM-L6-v2")
   256|
   257|# =============================================================================
   258|# v4.0 进化功能配置
   259|# =============================================================================
   260|
   261|# 是否启用进化功能（复盘、技能生成等）
   262|# - 启用时: 会在 data/traces/ 目录生成任务执行轨迹文件
   263|# - 禁用时: 不会生成 traces 文件，只保留 data/conversations/ 的对话历史
   264|ENABLE_EVOLUTION = os.getenv("ENABLE_EVOLUTION", "false").lower() == "true"
   265|
   266|# =============================================================================
   267|# 数据目录说明
   268|# =============================================================================
   269|#
   270|# data/conversations/ - 用户对话历史（始终保留）
   271|#   - 存储用户与 AI 的聊天记录
   272|#   - 用于上下文记忆
   273|#
   274|# data/traces/ - 任务执行轨迹（仅在 ENABLE_EVOLUTION=true 时生成）
   275|#   - 存储详细的任务执行过程
   276|#   - 用于复盘分析和自动生成新技能
   277|#
   278|# data/reflections/ - 复盘记录（仅在 ENABLE_EVOLUTION=true 时生成）
   279|#   - 存储任务复盘结果
   280|#
   281|# data/workflows/ - 工作流模板
   282|#   - 预设的工作流模板
   283|#
   284|# =============================================================================
   285|
   286|
   287|# =============================================================================
   288|# 系统上下文文件配置（每次对话开始时自动读取）
   289|# =============================================================================
   290|# 列表中的文件会在每次对话开始时读取，其内容会被注入到系统提示词中，
   291|# 增强模型对项目背景的理解。用户可根据需要自定义文件列表
   292|# （绝对路径或相对项目根目录的路径）。
   293|SYSTEM_CONTEXT_FILES = [
   294|    "MEMORY.md",   # 用户长期记忆和偏好
   295|    "SOUL.md",     # 项目核心灵魂文档
   296|]
   297|# 版本号（从VERSION文件读取）
   298|def _read_version():
   299|    version_file = os.path.join(PROJECT_ROOT, "VERSION")
   300|    try:
   301|        with open(version_file, 'r', encoding='utf-8') as f:
   302|            return f.read().strip()
   303|    except Exception:
   304|        return "0.0.0"
   305|
   306|VERSION = _read_version()
   307|
   308|# =============================================================================
   309|# 集群协作配置（Phase 2 新增）
   310|# =============================================================================
   311|
   312|CLUSTER_ENABLED = os.getenv("CLUSTER_ENABLED", "false").lower() == "true"
   313|CLUSTER_ROLE = os.getenv("CLUSTER_ROLE", "worker")
   314|CLUSTER_MANAGER_HOST = os.getenv("CLUSTER_MANAGER_HOST", "127.0.0.1")
   315|CLUSTER_MANAGER_PORT = PORT_CLUSTER_MANAGER
   316|CLUSTER_NODE_ID = os.getenv("CLUSTER_NODE_ID", None)
   317|CLUSTER_NODE_NICKNAME = os.getenv("CLUSTER_NODE_NICKNAME", "玄枢成员")
   318|CLUSTER_WORKER_THREADS = int(os.getenv("CLUSTER_WORKER_THREADS", 1))
   319|CLUSTER_API_TOKEN = os.getenv("CLUSTER_API_TOKEN", None)
   320|# Worker 节点对外 API 端口（使用PORT_CLUSTER_API）
   321|CLUSTER_API_PORT = PORT_CLUSTER_API
   322|
   323|# =============================================================================
   324|# Phase 3 智能调度配置（能力评估器 + 任务调度器）
   325|# =============================================================================
   326|
   327|# 能力评估器权重配置
   328|CAPABILITY_WEIGHTS = {
   329|    "model": 0.4,       # 模型基准分权重
   330|    "hardware": 0.2,    # 硬件算力权重
   331|    "load": 0.15,       # 实时负载权重
   332|    "history": 0.15,    # 历史表现权重
   333|    "network": 0.1      # 网络质量权重（预留）
   334|}
   335|
   336|# 能力评估器模型排行榜（可动态更新）
   337|CAPABILITY_MODEL_RANKINGS = {
   338|    "qwen2.5-coder:7b": 0.95,
   339|    "qwen2.5:7b": 0.85,
   340|    "llama3:8b": 0.80,
   341|    "phi3:3.8b": 0.60,
   342|    "mistral:7b": 0.70
   343|}
   344|
   345|# 调度器配置
   346|SCHEDULER_STRATEGY = os.getenv("SCHEDULER_STRATEGY", "affinity")  # capability/load_balance/affinity/round_robin
   347|SCHEDULER_MAX_TASKS_PER_NODE = int(os.getenv("SCHEDULER_MAX_TASKS_PER_NODE", "5"))
   348|SCHEDULER_TASK_TIMEOUT = int(os.getenv("SCHEDULER_TASK_TIMEOUT", "300"))  # 秒
   349|
   350|# Manager 监控配置
   351|MANAGER_MONITOR_INTERVAL = int(os.getenv("MANAGER_MONITOR_INTERVAL", "5"))  # 监控间隔（秒）
   352|MANAGER_MAX_RETRIES = int(os.getenv("MANAGER_MAX_RETRIES", "3"))  # 最大重试次数
   353|