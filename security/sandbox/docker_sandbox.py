#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docker 沙箱执行环境

功能：
- 在隔离的 Docker 容器中执行 Python 代码
- 资源限制：CPU、内存、超时
- 网络隔离：默认无网络访问
- 文件系统只读（除 /tmp）
- 自动清理容器

设计原则：
- 安全性优先：no-new-privileges, read-only fs
- 性能优化：镜像缓存、容器池（预留）
- 向后兼容：支持降级到 subprocess 模式

Author: 破执 (Based on Four Phenomena Collaboration)
Date: 2026-05-03
"""

import os
import time
import tempfile
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from contextlib import contextmanager

# 尝试导入 docker 包，如果未安装则标记为不可用
try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

from config import (
    PROJECT_ROOT,
    SANDBOX_CPU_LIMIT,
    SANDBOX_MEMORY_LIMIT,
    SANDBOX_TIMEOUT,
    SANDBOX_IMAGE,
    SANDBOX_NETWORK_MODE,
    SANDBOX_READ_ONLY,
    SANDBOX_TEMP_DIR,
    SANDBOX_SECURITY_OPTIONS,
)
from logger import get_logger

logger = get_logger("security.sandbox")


class DockerSandbox:
    """
    Docker 容器沙箱执行器

    负责在隔离的 Docker 容器中执行代码，提供资源限制和安全策略。
    """

    def __init__(
        self,
        image: str = None,
        cpu_limit: float = None,
        memory_limit: str = None,
        timeout: int = None,
        network_mode: str = None,
        read_only: bool = None,
        temp_dir: str = None,
        security_options: list = None,
    ):
        """
        初始化 Docker 沙箱

        Args:
            image: Docker 镜像名称
            cpu_limit: CPU 限制 (0.0-1.0)
            memory_limit: 内存限制 Docker 格式 (如 "256m")
            timeout: 执行超时时间（秒）
            network_mode: 网络模式 ("none", "host", "bridge", 等)
            read_only: 文件系统是否只读
            temp_dir: 宿主机临时目录路径（用于挂载到容器 /tmp）
            security_options: Docker 安全选项列表
        """
        # 加载配置（使用 config 中的默认值）
        self.image = image or SANDBOX_IMAGE or "python:3.10-slim"
        self.cpu_limit = cpu_limit if cpu_limit is not None else (SANDBOX_CPU_LIMIT or 0.5)
        self.memory_limit = memory_limit or SANDBOX_MEMORY_LIMIT or "256m"
        self.timeout = timeout if timeout is not None else (SANDBOX_TIMEOUT or 30)
        self.network_mode = network_mode or SANDBOX_NETWORK_MODE or "none"
        self.read_only = read_only if read_only is not None else (SANDBOX_READ_ONLY if SANDBOX_READ_ONLY is not None else True)
        self.temp_dir = Path(temp_dir or SANDBOX_TEMP_DIR or tempfile.gettempdir())
        self.security_options = security_options or (SANDBOX_SECURITY_OPTIONS or ["no-new-privileges"])

        # 确保临时目录存在
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Docker 客户端
        self._client = None
        self._available = False
        self._init_docker()

        logger.info(
            "DockerSandbox 初始化完成",
            details={
                "image": self.image,
                "cpu_limit": self.cpu_limit,
                "memory_limit": self.memory_limit,
                "network_mode": self.network_mode,
                "read_only": self.read_only,
                "available": self._available,
            },
        )

    def _init_docker(self):
        """初始化 Docker 客户端连接"""
        if not DOCKER_AVAILABLE:
            logger.info("Docker Python 包未安装，沙箱将使用 subprocess 降级模式")
            self._available = False
            return

        try:
            self._client = docker.from_env()
            # 测试连接
            self._client.ping()
            self._available = True
            logger.info("Docker 守护进程连接成功")
        except Exception as e:
            # 在 Windows 等未安装 Docker 的环境，这是预期行为，使用 info 级别避免用户恐慌
            logger.info(
                "Docker 守护进程未运行或未安装，沙箱将使用 subprocess 降级模式",
                details={"error": str(e)},
            )
            self._available = False

    def is_available(self) -> bool:
        """检查沙箱是否可用"""
        return self._available and self._client is not None

    def execute(self, code: str, skill_name: str = None, args: Dict[str, Any] = None) -> str:
        """
        在 Docker 容器中执行 Python 代码 - 安全强制模式
        绝对禁止降级到宿主机 subprocess 模式，确保容器隔离安全。

        Args:
            code: 要执行的 Python 代码字符串
            skill_name: 调用技能名称（用于审计）
            args: 技能参数（可能包含敏感信息，需脱敏）

        Returns:
            执行结果（stdout/stderr）或错误信息

        安全策略：
        - Docker 不可用时：不提供任何执行方式，完全阻断
        - 绝对不降级到宿主机 subprocess，防止沙箱逃逸
        """
        if not self.is_available():
            logger.critical("沙箱隔离失效，代码执行完全阻断")
            raise RuntimeError("❌ 安全策略拒绝执行：Docker沙箱不可用，禁止宿主机直接执行")

        start_time = time.time()
        container = None

        try:
            # 准备代码执行文件
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", dir=self.temp_dir, delete=False
            ) as f:
                f.write(code)
                code_file = f.name

            # 配置容器资源限制
            cpu_quota = int(self.cpu_limit * 100000)  # Docker CPU 配额（微秒）
            mem_limit = self.memory_limit

            # 构建环境变量
            env = {
                "PYTHONUNBUFFERED": "1",  # 实时输出
                "PYTHONIOENCODING": "utf-8",
            }

            # 运行容器
            logger.info(
                "启动代码执行容器",
                details={
                    "skill": skill_name,
                    "image": self.image,
                    "cpu_quota": cpu_quota,
                    "memory": mem_limit,
                    "timeout": self.timeout,
                },
            )

            container = self._client.containers.run(
                image=self.image,
                command=["python", "-c", code],
                # 安全配置
                network_mode=self.network_mode,
                read_only=self.read_only,
                mem_limit=mem_limit,
                cpu_period=100000,
                cpu_quota=cpu_quota,
                # 只挂载临时目录，宿主机其他目录不可见
                volumes={str(self.temp_dir): {"bind": "/tmp", "mode": "rw"}},
                # 安全选项
                security_opt=self.security_options,
                # 工作目录
                working_dir="/tmp",
                # 环境变量
                environment=env,
                # 自动清理
                remove=True,
                # 超时控制（Docker API 级别）
                # 注意：Docker 本身没有直接超时，需在代码执行层面控制
                # 这里使用 client timeout 控制 API 调用
            )

            # 等待执行完成，带超时
            result = container.wait(timeout=self.timeout + 5)  # 额外缓冲

            # 获取日志
            logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")

            elapsed = time.time() - start_time

            exit_code = result.get("StatusCode", -1) if isinstance(result, dict) else result

            if exit_code == 0:
                logger.info(
                    "代码执行成功",
                    details={
                        "skill": skill_name,
                        "elapsed": round(elapsed, 2),
                        "output_length": len(logs),
                    },
                )
                # 限制输出长度
                if len(logs) > 4000:
                    logs = logs[:4000] + "\n... (输出过长，已截断)"
                return f"✅ 执行成功 (耗时 {elapsed:.2f}s):\n{logs}"
            else:
                logger.error(
                    "代码执行失败",
                    details={
                        "skill": skill_name,
                        "exit_code": exit_code,
                        "elapsed": round(elapsed, 2),
                    },
                )
                return f"❌ 执行失败 (退出码 {exit_code}, 耗时 {elapsed:.2f}s):\n{logs}"

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                "容器执行异常",
                details={"skill": skill_name, "error": str(e), "elapsed": round(elapsed, 2)},
                exc_info=True,
            )
            return f"❌ 执行异常：{str(e)}"

        finally:
            # 确保容器清理
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    @contextmanager
    def container_pool(self):
        """
        容器池上下文管理器（预留接口，未来实现）

        当前未实砚，仅提供占位接口。未来可以预热一组容器以减少启动开销。
        """
        yield self


# 全局沙箱实例（可选）
_default_sandbox = None


def get_default_sandbox() -> DockerSandbox:
    """获取默认沙箱实例（单例）"""
    global _default_sandbox
    if _default_sandbox is None:
        _default_sandbox = DockerSandbox()
    return _default_sandbox
