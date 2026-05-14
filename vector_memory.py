"""
向量记忆系统 (Vector Memory System) - 三级降级架构
=====================================================
第1级: 向量模式 (ChromaDB + sentence-transformers) - 语义搜索
第2级: SQLite 关键词匹配 (memory_core) - 精确匹配
第3级: 纯 JSON 文件存储 - 零依赖运行

- 自动检测各级依赖可用性，无缝降级
- 支持 Windows/Linux/Mac 全平台，包括无 sqlite3 的环境
"""

import os
import re
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from config import PROJECT_ROOT, USE_VECTOR_MEMORY, VECTOR_MODEL
from logger import logger

# =============================================================================
# 依赖检测
# =============================================================================

# 检测向量库可用性
_VECTOR_AVAILABLE = False
_chroma_client = None
_embedding_func = None

if USE_VECTOR_MEMORY:
    try:
        import chromadb
        from chromadb.config import Settings
        from sentence_transformers import SentenceTransformer
        _VECTOR_AVAILABLE = True
        logger.info("✅ 向量记忆依赖可用 (chromadb + sentence-transformers)")
    except ImportError as e:
        logger.warning(f"⚠️ 向量记忆依赖不可用: {e}，将尝试降级到 SQLite 或 JSON 模式")

# 检测 SQLite 可用性（用于第2级降级）
_SQLITE_AVAILABLE = False
try:
    import sqlite3
    _SQLITE_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ sqlite3 模块不可用，向量记忆将使用纯 JSON 文件降级方案")


# =============================================================================
# 第3级: 纯 JSON 文件存储 (零依赖)
# =============================================================================

class JsonMemoryStore:
    """
    纯 JSON 文件存储 - 零外部依赖
    当 sqlite3 和 chromadb 都不可用时使用
    """

    def __init__(self, store_dir: Optional[str] = None):
        self.store_dir = store_dir or os.path.join(PROJECT_ROOT, "data", "vector_memory_json")
        os.makedirs(self.store_dir, exist_ok=True)

        self._memory_path = os.path.join(self.store_dir, "memories.json")
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """确保存储文件存在"""
        if not os.path.exists(self._memory_path):
            self._save_all([])

    def _load_all(self) -> List[Dict[str, Any]]:
        """加载所有记忆"""
        try:
            with open(self._memory_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
        except Exception as e:
            logger.error(f"加载 JSON 记忆失败: {e}")
            return []

    def _save_all(self, memories: List[Dict[str, Any]]):
        """保存所有记忆"""
        try:
            with open(self._memory_path, 'w', encoding='utf-8') as f:
                json.dump(memories, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存 JSON 记忆失败: {e}")

    def add(self, memory_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        """添加记忆"""
        try:
            memories = self._load_all()
            memories.append({
                "id": memory_id,
                "content": content,
                "metadata": metadata,
                "timestamp": datetime.now().isoformat()
            })
            self._save_all(memories)
            return True
        except Exception as e:
            logger.error(f"JSON 存储添加记忆失败: {e}")
            return False

    def get_all(self) -> List[Dict[str, Any]]:
        """获取所有记忆"""
        return self._load_all()

    def delete(self, memory_id: str) -> bool:
        """删除指定记忆"""
        try:
            memories = self._load_all()
            memories = [m for m in memories if m.get("id") != memory_id]
            self._save_all(memories)
            return True
        except Exception as e:
            logger.error(f"JSON 存储删除记忆失败: {e}")
            return False

    def clear(self) -> bool:
        """清空所有记忆"""
        try:
            self._save_all([])
            return True
        except Exception as e:
            logger.error(f"JSON 存储清空记忆失败: {e}")
            return False

    def count(self) -> int:
        """获取记忆数量"""
        return len(self._load_all())


# =============================================================================
# 向量记忆主类
# =============================================================================

class VectorMemory:
    """
    向量记忆管理器 - 三级降级架构

    降级链:
        向量模式 (ChromaDB) → SQLite 关键词匹配 → 纯 JSON 文件存储

    每种模式都提供:
        - add_memory: 添加记忆
        - search_memory: 搜索记忆
        - delete_memory: 删除记忆
        - clear_all_memory: 清空记忆
        - get_stats: 获取统计
    """

    _instance = None

    # 模式常量
    MODE_VECTOR = "vector"
    MODE_SQLITE = "sqlite"
    MODE_JSON = "json"

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(VectorMemory, cls).__new__(cls)
        return cls._instance

    def __init__(self, collection_name: str = "agent_memory"):
        if hasattr(self, 'initialized'):
            return

        self.collection_name = collection_name
        self._mode = None
        self._json_store = None
        self._fallback_db = None

        # 尝试初始化第1级: 向量模式
        if _VECTOR_AVAILABLE and USE_VECTOR_MEMORY:
            try:
                self._init_vector_mode()
                self._mode = self.MODE_VECTOR
                logger.info(f"✅ 向量记忆已启用 (模式: {self._mode}, 模型: {VECTOR_MODEL})")
                self.initialized = True
                return
            except Exception as e:
                logger.warning(f"⚠️ 向量模式初始化失败: {e}，尝试降级到 SQLite")

        # 尝试初始化第2级: SQLite 关键词匹配
        if _SQLITE_AVAILABLE:
            try:
                self._init_sqlite_fallback_mode()
                self._mode = self.MODE_SQLITE
                logger.info(f"📂 向量记忆已降级 (模式: {self._mode}, SQLite 关键词匹配)")
                self.initialized = True
                return
            except Exception as e:
                logger.warning(f"⚠️ SQLite 降级模式初始化失败: {e}，尝试降级到 JSON")

        # 初始化第3级: 纯 JSON 文件存储 (零依赖)
        try:
            self._init_json_fallback_mode()
            self._mode = self.MODE_JSON
            logger.info(f"📄 向量记忆已降级 (模式: {self._mode}, 纯 JSON 文件存储)")
        except Exception as e:
            logger.error(f"❌ 所有记忆模式初始化失败: {e}")
            raise RuntimeError(f"无法初始化任何记忆存储模式: {e}")

        self.initialized = True

    # =========================================================================
    # 各级初始化方法
    # =========================================================================

    def _init_vector_mode(self):
        """初始化第1级: ChromaDB 向量存储"""
        global _chroma_client, _embedding_func

        persist_dir = os.path.join(PROJECT_ROOT, "data", "chroma_db")
        os.makedirs(persist_dir, exist_ok=True)

        if _chroma_client is None:
            _chroma_client = chromadb.Client(
                Settings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=persist_dir,
                    anonymized_telemetry=False
                )
            )

        if _embedding_func is None:
            _embedding_func = SentenceTransformer(VECTOR_MODEL)

        self.collection = _chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def _init_sqlite_fallback_mode(self):
        """初始化第2级: SQLite 关键词匹配降级"""
        from memory_core import memory_core
        self._fallback_db = memory_core
        self._memory_cache: List[Dict[str, Any]] = []
        self._load_sqlite_cache()

    def _init_json_fallback_mode(self):
        """初始化第3级: 纯 JSON 文件存储降级"""
        self._json_store = JsonMemoryStore()
        self._memory_cache: List[Dict[str, Any]] = []
        self._load_json_cache()

    # =========================================================================
    # 缓存加载
    # =========================================================================

    def _load_sqlite_cache(self):
        """从 SQLite 加载记忆到缓存"""
        try:
            history = self._fallback_db.get_conversation_history("current", limit=1000)
            for item in history:
                self._memory_cache.append({
                    "id": f"hist_{item.get('timestamp', '')}",
                    "content": item.get("content", ""),
                    "role": item.get("role", ""),
                    "timestamp": item.get("timestamp", ""),
                    "metadata": {"source": "conversation", "role": item.get("role", "")}
                })
        except Exception as e:
            logger.warning(f"加载 SQLite 缓存失败: {e}")

    def _load_json_cache(self):
        """从 JSON 文件加载记忆到缓存"""
        try:
            memories = self._json_store.get_all()
            for mem in memories:
                self._memory_cache.append({
                    "id": mem.get("id", ""),
                    "content": mem.get("content", ""),
                    "timestamp": mem.get("timestamp", ""),
                    "metadata": mem.get("metadata", {})
                })
        except Exception as e:
            logger.warning(f"加载 JSON 缓存失败: {e}")

    # =========================================================================
    # 核心 API
    # =========================================================================

    def add_memory(self, content: str, metadata: Optional[Dict[str, Any]] = None,
                   memory_id: Optional[str] = None) -> bool:
        """
        添加记忆 - 根据当前模式自动选择存储方式

        Args:
            content: 记忆内容
            metadata: 额外元数据
            memory_id: 可选的记忆ID

        Returns:
            是否成功
        """
        if not content or not content.strip():
            return False

        metadata = metadata or {}
        memory_id = memory_id or f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        try:
            if self._mode == self.MODE_VECTOR:
                return self._add_vector(content, metadata, memory_id)
            elif self._mode == self.MODE_SQLITE:
                return self._add_sqlite(content, metadata, memory_id)
            else:
                return self._add_json(content, metadata, memory_id)
        except Exception as e:
            logger.error(f"添加记忆失败 [模式={self._mode}]: {e}")
            return False

    def _add_vector(self, content: str, metadata: Dict[str, Any], memory_id: str) -> bool:
        """向量模式添加"""
        embedding = _embedding_func.encode(content).tolist()
        self.collection.add(
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
            ids=[memory_id]
        )
        if hasattr(_chroma_client, 'persist'):
            _chroma_client.persist()
        return True

    def _add_sqlite(self, content: str, metadata: Dict[str, Any], memory_id: str) -> bool:
        """SQLite 降级模式添加"""
        self._memory_cache.append({
            "id": memory_id,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata
        })
        role = metadata.get("role", "system")
        self._fallback_db.add_conversation("current", role, content)
        return True

    def _add_json(self, content: str, metadata: Dict[str, Any], memory_id: str) -> bool:
        """JSON 降级模式添加"""
        self._memory_cache.append({
            "id": memory_id,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata
        })
        return self._json_store.add(memory_id, content, metadata)

    def search_memory(self, query: str, top_k: int = 5,
                      filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        搜索相关记忆 - 根据当前模式自动选择搜索方式

        Args:
            query: 查询文本
            top_k: 返回结果数量
            filter_metadata: 元数据过滤条件（仅向量模式支持）

        Returns:
            相关记忆列表，每项包含 content, score, metadata
        """
        if not query or not query.strip():
            return []

        try:
            if self._mode == self.MODE_VECTOR:
                return self._search_vector(query, top_k, filter_metadata)
            else:
                return self._search_keyword(query, top_k)
        except Exception as e:
            logger.error(f"搜索记忆失败 [模式={self._mode}]: {e}")
            return []

    def _search_vector(self, query: str, top_k: int,
                       filter_metadata: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """向量模式搜索"""
        query_embedding = _embedding_func.encode(query).tolist()
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, 50),
            where=filter_metadata
        )

        memories = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                score = results["distances"][0][i] if results.get("distances") else 0.0
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                memories.append({
                    "content": doc,
                    "score": 1.0 - score,
                    "metadata": meta
                })
        return memories

    def _search_keyword(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """关键词匹配搜索（SQLite 和 JSON 模式共用）"""
        if not self._memory_cache:
            return []

        query_words = set(re.findall(r'\b\w+\b', query.lower()))
        if not query_words:
            return []

        scored_memories = []
        for mem in self._memory_cache:
            content = mem.get("content", "").lower()
            content_words = set(re.findall(r'\b\w+\b', content))

            intersection = query_words & content_words
            union = query_words | content_words
            score = len(intersection) / len(union) if union else 0

            for word in query_words:
                if word in content:
                    score += 0.1

            if score > 0:
                scored_memories.append({
                    "content": mem["content"],
                    "score": min(score, 1.0),
                    "metadata": mem.get("metadata", {})
                })

        scored_memories.sort(key=lambda x: x["score"], reverse=True)
        return scored_memories[:top_k]

    def delete_memory(self, memory_id: str) -> bool:
        """删除指定记忆"""
        try:
            if self._mode == self.MODE_VECTOR:
                self.collection.delete(ids=[memory_id])
            else:
                self._memory_cache = [m for m in self._memory_cache if m.get("id") != memory_id]
                if self._mode == self.MODE_JSON and self._json_store:
                    self._json_store.delete(memory_id)
            return True
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            return False

    def clear_all_memory(self) -> bool:
        """清空所有记忆"""
        try:
            if self._mode == self.MODE_VECTOR:
                _chroma_client.delete_collection(self.collection_name)
                self.collection = _chroma_client.create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
            else:
                self._memory_cache.clear()
                if self._mode == self.MODE_JSON and self._json_store:
                    self._json_store.clear()
            return True
        except Exception as e:
            logger.error(f"清空记忆失败: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆系统统计信息"""
        stats = {
            "mode": self._mode,
            "collection_name": self.collection_name
        }

        try:
            if self._mode == self.MODE_VECTOR:
                stats["total_memories"] = self.collection.count()
                stats["model"] = VECTOR_MODEL
                stats["backend"] = "chromadb"
            elif self._mode == self.MODE_SQLITE:
                stats["total_memories"] = len(self._memory_cache)
                stats["model"] = "keyword_matching"
                stats["backend"] = "sqlite"
            else:
                stats["total_memories"] = self._json_store.count() if self._json_store else 0
                stats["model"] = "keyword_matching"
                stats["backend"] = "json_file"
        except Exception as e:
            stats["error"] = str(e)

        return stats

    def get_mode(self) -> str:
        """获取当前运行模式"""
        return self._mode or "unknown"


# =============================================================================
# 全局实例和便捷函数
# =============================================================================

# 全局向量记忆实例
vector_memory = VectorMemory()


def get_vector_memory() -> VectorMemory:
    """获取向量记忆实例"""
    return vector_memory


def add_memory(content: str, metadata: Optional[Dict[str, Any]] = None,
               memory_id: Optional[str] = None) -> bool:
    """添加记忆（便捷函数）"""
    return vector_memory.add_memory(content, metadata, memory_id)


def search_memory(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """搜索记忆（便捷函数）"""
    return vector_memory.search_memory(query, top_k)


def get_memory_stats() -> Dict[str, Any]:
    """获取记忆统计（便捷函数）"""
    return vector_memory.get_stats()
