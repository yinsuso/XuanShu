import os
from typing import Optional

# =============================================================================
# 基础路径配置
# =============================================================================

# 项目根目录：项目的根路径，用于构建其他相对路径
# 使用多级 fallback 确保跨平台兼容性
_POTENTIAL_ROOTS = [
    os.path.dirname(os.path.abspath(__file__)),  # 当前文件所在目录
    os.getcwd(),  # 当前工作目录
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'),  # 父目录
]

# 选择第一个存在的目录作为 PROJECT_ROOT
for _root in _POTENTIAL_ROOTS:
    if os.path.isdir(_root):
        PROJECT_ROOT = _root
        break
else:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 调试：记录项目根目录
import sys
print(f"[CONFIG] 项目根目录: {PROJECT_ROOT}", file=sys.stderr)

# 允许操作的目录：Agent只能在这个目录及其子目录下进行文件操作，防止路径越权
ALLOWED_DIR = PROJECT_ROOT

# 内存数据库路径：用于存储对话历史和反思记录的SQLite数据库文件位置
MEMORY_DB_PATH = os.path.join(PROJECT_ROOT, "agent_memory.db")

# =============================================================================
# 端口统一管理
# =============================================================================

# Web服务端口（统一入口）
PORT_WEB = int(os.getenv("WEB_PORT", 30000))

# 集群管理端口（Manager监听）
PORT_CLUSTER_MANAGER = int(os.getenv("CLUSTER_MANAGER_PORT", 30001))

# 集群Worker API端口
PORT_CLUSTER_API = int(os.getenv("CLUSTER_API_PORT", 30002))

# =============================================================================
# Ollama 配置
# =============================================================================

# Ollama 服务地址：本地 Ollama 服务的基础 URL，默认为 localhost 的 11434 端口
# 可以通过环境变量 OLLAMA_BASE_URL 覆盖
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# 模型名称：使用的 Ollama 模型名称
# ⚠️ 重要：此处不再设置默认值！
# 系统启动时将自动读取 data/model_config.json 中的当前配置。
# 若环境变量 MODEL_NAME 存在，仅作为 fallback（极少使用），否则为 None。
MODEL_NAME = os.getenv("MODEL_NAME", None)

# =============================================================================
# 安全配置
# =============================================================================

# 最大代码执行次数：单次对话中允许执行代码的最大次数，防止无限循环执行
MAX_CODE_EXECUTIONS = 10

# 代码执行超时时间：单次代码执行的超时时间（秒），防止长时间阻塞
CODE_EXECUTION_TIMEOUT = 10

# =============================================================================
# Docker 沙箱配置（新增强）
# =============================================================================

# 是否启用 Docker 沙箱执行（若 False 则降级到 subprocess 模式）
SANDBOX_ENABLED = os.getenv("SANDBOX_ENABLED", "true").lower() == "true"

# 沙箱 Docker 镜像：使用轻量级 Python 镜像
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "python:3.10-slim")

# CPU 限制：0.0-1.0，表示 CPU 核心数的比例
SANDBOX_CPU_LIMIT = float(os.getenv("SANDBOX_CPU_LIMIT", 0.5))

# 内存限制：Docker 格式（如 "256m", "512m"）
SANDBOX_MEMORY_LIMIT = os.getenv("SANDBOX_MEMORY_LIMIT", "256m")

# 执行超时：秒
SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", 30))

# 网络模式："none"（无网络）、"host"（共享主机）、"bridge"（桥接）等
SANDBOX_NETWORK_MODE = os.getenv("SANDBOX_NETWORK_MODE", "none")

# 文件系统只读：只在 /tmp 可写
SANDBOX_READ_ONLY = os.getenv("SANDBOX_READ_ONLY", "true").lower() == "true"

# 宿主机临时目录：用于挂载到容器 /tmp
SANDBOX_TEMP_DIR = os.getenv("SANDBOX_TEMP_DIR", os.path.join(PROJECT_ROOT, "tmp"))

# Docker 安全选项：如 ["no-new-privileges", "apparmor:unconfined"]
SANDBOX_SECURITY_OPTIONS = os.getenv("SANDBOX_SECURITY_OPTIONS", "no-new-privileges").split(",") if os.getenv("SANDBOX_SECURITY_OPTIONS") else ["no-new-privileges"]

# =============================================================================
# 网络访问控制配置
# =============================================================================

# 是否启用网络访问控制
NETWORK_ENABLED = os.getenv("NETWORK_ENABLED", "true").lower() == "true"

# 默认操作：当不匹配任何规则时的行为
NETWORK_DEFAULT_ACTION = os.getenv("NETWORK_DEFAULT_ACTION", "deny")  # allow/deny

# 域名白名单（逗号分隔列表）
NETWORK_WHITELIST = os.getenv("NETWORK_WHITELIST", "api.openai.com,ollama.local,huggingface.co").split(",") if os.getenv("NETWORK_WHITELIST") else ["api.openai.com", "ollama.local", "huggingface.co"]

# 域名黑名单
NETWORK_BLOCKED_DOMAINS = os.getenv("NETWORK_BLOCKED_DOMAINS", "metadata.google.internal,169.254.169.254").split(",") if os.getenv("NETWORK_BLOCKED_DOMAINS") else ["metadata.google.internal", "169.254.169.254"]

# IP 黑名单
NETWORK_BLOCKED_IPS = os.getenv("NETWORK_BLOCKED_IPS", "169.254.169.254,100.100.100.200").split(",") if os.getenv("NETWORK_BLOCKED_IPS") else ["169.254.169.254", "100.100.100.200"]

# 过滤空字符串，避免无效配置
NETWORK_WHITELIST = [x for x in NETWORK_WHITELIST if x]
NETWORK_BLOCKED_DOMAINS = [x for x in NETWORK_BLOCKED_DOMAINS if x]
NETWORK_BLOCKED_IPS = [x for x in NETWORK_BLOCKED_IPS if x]

# =============================================================================
# 审批联动配置
# =============================================================================

# Web 审批服务地址（Agent 提交审批请求的目标）
WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:8000")

# 审批 API 共享令牌（用于 Agent ↔ Web 身份验证）
APPROVAL_API_TOKEN = os.getenv("APPROVAL_API_TOKEN", "change-me-to-secure-random")

# 审批等待超时（秒）
APPROVAL_TIMEOUT = int(os.getenv("APPROVAL_TIMEOUT", "60"))

# 审批状态轮询间隔（秒）
APPROVAL_POLL_INTERVAL = int(os.getenv("APPROVAL_POLL_INTERVAL", "2"))

# 审批数据存储路径（SQLite）
APPROVAL_DB_PATH = os.getenv("APPROVAL_DB_PATH", os.path.join(PROJECT_ROOT, "data", "approvals.db"))

# =============================================================================
# Agent 配置
# =============================================================================

# 最大历史长度：保留的对话历史消息数量，用于上下文管理
MAX_HISTORY_LENGTH = 20

# 是否启用记忆系统：控制是否使用SQLite数据库存储对话历史和反思
ENABLE_MEMORY = True

# =============================================================================
# Web界面配置（新增）
# =============================================================================

# Web服务主机：Web界面监听的主机地址
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")

# Web服务端口：Web界面监听的端口（统一使用PORT_WEB）
WEB_PORT = PORT_WEB

# 是否启用调试模式：控制Web应用是否以调试模式运行
WEB_DEBUG = os.getenv("WEB_DEBUG", "false").lower() == "true"

# =============================================================================
# 结构化日志配置（新增）
# =============================================================================

# 日志级别：控制日志输出的详细程度
# 可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# 日志格式："text"（传统格式）或 "json"（结构化JSON行）
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")

# 日志文件路径：日志文件的存储位置，None表示只输出到控制台
LOG_FILE = os.getenv("LOG_FILE", None)

# 日志轮转配置
LOG_ROTATION_DAYS = int(os.getenv("LOG_ROTATION_DAYS", 30))  # 保留天数
LOG_COMPRESS = os.getenv("LOG_COMPRESS", "true").lower() == "true"  # 是否压缩归档

# Trace ID 请求头名称：用于跨组件追踪
TRACE_ID_HEADER = os.getenv("TRACE_ID_HEADER", "X-Hermes-Trace")

# 异步写入配置
LOG_ASYNC_QUEUE_SIZE = int(os.getenv("LOG_ASYNC_QUEUE_SIZE", 1000))  # 队列容量
LOG_BATCH_SIZE = int(os.getenv("LOG_BATCH_SIZE", 100))  # 批量写入条数
LOG_FLUSH_INTERVAL = float(os.getenv("LOG_FLUSH_INTERVAL", 1.0))  # 刷盘间隔(秒)

# =============================================================================
# 敏感信息脱敏配置（新增）
# =============================================================================

# 是否启用脱敏
MASKING_ENABLED = os.getenv("MASKING_ENABLED", "true").lower() == "true"

# 脱敏正则模式列表（按优先级顺序）
MASKING_PATTERNS = [
    r"Bearer\s+[A-Za-z0-9_\-]+",  # Bearer tokens
    r"sk-[A-Za-z0-9]{48}",  # OpenAI keys
    r"ghp_[A-Za-z0-9]{36}",  # GitHub tokens
    r"AKIA[0-9A-Z]{16}",  # AWS Access Keys
    r"\$[A-Za-z_]\w*",  # 环境变量引用（$VAR 或 ${VAR} 的简化版）
        r"glpat-[0-9a-zA-Z_-]{20}",  # GitLab tokens
        r"eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{20,}",  # JWT tokens
        r"AIza[0-9A-Za-z_-]{35}",  # Google API Keys
        r"xoxb-[0-9]{12}-[0-9]{12}-[0-9A-Za-z]+",  # Slack Bot Tokens
        r"mongodb://[^:@]+:[^:@]*@[^:@]+",  # MongoDB connection strings
]

# 脱敏替换文本
MASKING_REPLACEMENT = os.getenv("MASKING_REPLACEMENT", "[REDACTED]")

# 是否保留脱敏后长度（用于某些场景）
MASKING_PRESERVE_LENGTH = os.getenv("MASKING_PRESERVE_LENGTH", "false").lower() == "true"

# 脱敏统计文件路径
MASKING_STATS_PATH = os.path.join(PROJECT_ROOT, "logs", "masking_stats.json")

# =============================================================================
# 日志文件路径（增强）
# =============================================================================

# 结构化日志文件路径（覆盖 LOG_FILE，若 LOG_FORMAT=json）
if LOG_FORMAT == "json":
    if LOG_FILE:
        LOG_FILE_JSON = LOG_FILE.replace(".log", "_json.log")
    else:
        LOG_FILE_JSON = os.path.join(PROJECT_ROOT, "logs", "hermes.jsonl")
else:
    LOG_FILE_JSON = None

# =============================================================================
# 重试配置（新增）
# =============================================================================

# 最大重试次数：Ollama请求失败时的最大重试次数
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

# 重试延迟（秒）：重试之间的等待时间，使用指数退避
RETRY_DELAY = float(os.getenv("RETRY_DELAY", 1.0))

# =============================================================================
# 记忆系统配置（新增）
# =============================================================================

# 是否启用向量搜索：需要安装chromadb和sentence-transformers
USE_VECTOR_MEMORY = os.getenv("USE_VECTOR_MEMORY", "false").lower() == "true"

# 向量模型名称：用于生成记忆嵌入的模型
VECTOR_MODEL = os.getenv("VECTOR_MODEL", "all-MiniLM-L6-v2")

# =============================================================================
# v4.0 进化功能配置
# =============================================================================

# 是否启用进化功能（复盘、技能生成等）
# - 启用时: 会在 data/traces/ 目录生成任务执行轨迹文件
# - 禁用时: 不会生成 traces 文件，只保留 data/conversations/ 的对话历史
ENABLE_EVOLUTION = os.getenv("ENABLE_EVOLUTION", "false").lower() == "true"

# =============================================================================
# 数据目录说明
# =============================================================================
#
# data/conversations/ - 用户对话历史（始终保留）
#   - 存储用户与 AI 的聊天记录
#   - 用于上下文记忆
#
# data/traces/ - 任务执行轨迹（仅在 ENABLE_EVOLUTION=true 时生成）
#   - 存储详细的任务执行过程
#   - 用于复盘分析和自动生成新技能
#
# data/reflections/ - 复盘记录（仅在 ENABLE_EVOLUTION=true 时生成）
#   - 存储任务复盘结果
#
# data/workflows/ - 工作流模板
#   - 预设的工作流模板
#
# =============================================================================

# 版本号（从VERSION文件读取）
def _read_version():
    version_file = os.path.join(PROJECT_ROOT, "VERSION")
    try:
        with open(version_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"

VERSION = _read_version()

# =============================================================================
# 集群协作配置（Phase 2 新增）
# =============================================================================

CLUSTER_ENABLED = os.getenv("CLUSTER_ENABLED", "false").lower() == "true"
CLUSTER_ROLE = os.getenv("CLUSTER_ROLE", "worker")
CLUSTER_MANAGER_HOST = os.getenv("CLUSTER_MANAGER_HOST", "127.0.0.1")
CLUSTER_MANAGER_PORT = PORT_CLUSTER_MANAGER
CLUSTER_NODE_ID = os.getenv("CLUSTER_NODE_ID", None)
CLUSTER_NODE_NICKNAME = os.getenv("CLUSTER_NODE_NICKNAME", "玄枢成员")
CLUSTER_WORKER_THREADS = int(os.getenv("CLUSTER_WORKER_THREADS", 1))
CLUSTER_API_TOKEN = os.getenv("CLUSTER_API_TOKEN", None)
# Worker 节点对外 API 端口（使用PORT_CLUSTER_API）
CLUSTER_API_PORT = PORT_CLUSTER_API

# =============================================================================
# Phase 3 智能调度配置（能力评估器 + 任务调度器）
# =============================================================================

# 能力评估器权重配置
CAPABILITY_WEIGHTS = {
    "model": 0.4,       # 模型基准分权重
    "hardware": 0.2,    # 硬件算力权重
    "load": 0.15,       # 实时负载权重
    "history": 0.15,    # 历史表现权重
    "network": 0.1      # 网络质量权重（预留）
}

# 能力评估器模型排行榜（可动态更新）
CAPABILITY_MODEL_RANKINGS = {
    "qwen2.5-coder:7b": 0.95,
    "qwen2.5:7b": 0.85,
    "llama3:8b": 0.80,
    "phi3:3.8b": 0.60,
    "mistral:7b": 0.70
}

# 调度器配置
SCHEDULER_STRATEGY = os.getenv("SCHEDULER_STRATEGY", "affinity")  # capability/load_balance/affinity/round_robin
SCHEDULER_MAX_TASKS_PER_NODE = int(os.getenv("SCHEDULER_MAX_TASKS_PER_NODE", "5"))
SCHEDULER_TASK_TIMEOUT = int(os.getenv("SCHEDULER_TASK_TIMEOUT", "300"))  # 秒

# Manager 监控配置
MANAGER_MONITOR_INTERVAL = int(os.getenv("MANAGER_MONITOR_INTERVAL", "5"))  # 监控间隔（秒）
MANAGER_MAX_RETRIES = int(os.getenv("MANAGER_MAX_RETRIES", "3"))  # 最大重试次数
