import os
import json
import time
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from config import PROJECT_ROOT
from logger import logger

try:
    from .token_tracker import token_tracker
except ImportError:
    token_tracker = None

CONFIG_FILE = os.path.join(PROJECT_ROOT, "data", "model_config.json")
os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)


class ProviderType(Enum):
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"
    CUSTOM = "custom"


@dataclass
class ModelConfig:
    provider: ProviderType
    name: str
    model_name: str
    api_base: str
    api_key: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider.value,
            "name": self.name,
            "model_name": self.model_name,
            "api_base": self.api_base,
            "api_key": self.api_key
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelConfig':
        return cls(
            provider=ProviderType(data["provider"]),
            name=data["name"],
            model_name=data["model_name"],
            api_base=data["api_base"],
            api_key=data.get("api_key", "")
        )


PRESET_CONFIGS: List[Dict[str, Any]] = [
    {
        "name": "Ollama (本地)",
        "provider": "ollama",
        "model_name": "qwen3.5:9b",
        "api_base": "http://localhost:11434",
        "api_key": ""
    },
    {
        "name": "OpenAI (GPT-4)",
        "provider": "openai_compatible",
        "model_name": "gpt-4",
        "api_base": "https://api.openai.com/v1",
        "api_key": ""
    },
    {
        "name": "OpenAI (GPT-3.5)",
        "provider": "openai_compatible",
        "model_name": "gpt-3.5-turbo",
        "api_base": "https://api.openai.com/v1",
        "api_key": ""
    },
    {
        "name": "DeepSeek",
        "provider": "openai_compatible",
        "model_name": "deepseek-chat",
        "api_base": "https://api.deepseek.com/v1",
        "api_key": ""
    },
    {
        "name": "通义千问",
        "provider": "openai_compatible",
        "model_name": "qwen-plus",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": ""
    },
    {
        "name": "智谱AI",
        "provider": "openai_compatible",
        "model_name": "glm-4",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "api_key": ""
    }
]


class ModelConfigManager:
    def __init__(self):
        self.configs: List[ModelConfig] = []
        self.current_config: Optional[ModelConfig] = None
        self.load_configs()

    def load_configs(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.configs = [ModelConfig.from_dict(cfg) for cfg in data.get("configs", [])]
                    current_name = data.get("current", "")
                    for cfg in self.configs:
                        if cfg.name == current_name:
                            self.current_config = cfg
                            break
                logger.info(f"已加载 {len(self.configs)} 个模型配置")
            except Exception as e:
                logger.error(f"加载配置失败: {e}")
                self.configs = []

        if not self.configs:
            for preset in PRESET_CONFIGS:
                self.configs.append(ModelConfig.from_dict(preset))
            self.current_config = self.configs[0]
            self.save_configs()

    def save_configs(self):
        try:
            data = {
                "configs": [cfg.to_dict() for cfg in self.configs],
                "current": self.current_config.name if self.current_config else ""
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存 {len(self.configs)} 个模型配置")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def add_config(self, config: ModelConfig) -> bool:
        for cfg in self.configs:
            if cfg.name == config.name:
                logger.warning(f"配置名称已存在: {config.name}")
                return False
        self.configs.append(config)
        self.save_configs()
        return True

    def update_config(self, config: ModelConfig) -> bool:
        for i, cfg in enumerate(self.configs):
            if cfg.name == config.name:
                self.configs[i] = config
                if self.current_config and self.current_config.name == config.name:
                    self.current_config = config
                self.save_configs()
                return True
        return False

    def delete_config(self, name: str) -> bool:
        for i, cfg in enumerate(self.configs):
            if cfg.name == name:
                self.configs.pop(i)
                if self.current_config and self.current_config.name == name:
                    self.current_config = self.configs[0] if self.configs else None
                self.save_configs()
                return True
        return False

    def set_current(self, name: str) -> bool:
        for cfg in self.configs:
            if cfg.name == name:
                self.current_config = cfg
                self.save_configs()
                logger.info(f"已切换到模型: {name}")
                return True
        return False

    def get_config(self, name: str) -> Optional[ModelConfig]:
        for cfg in self.configs:
            if cfg.name == name:
                return cfg
        return None

    def list_configs(self) -> List[Dict[str, Any]]:
        """返回所有模型配置，不做任何过滤，确保用户添加的所有云端API配置都可见"""
        return [
            {
                "name": cfg.name,
                "provider": cfg.provider.value,
                "model": cfg.model_name,
                "has_api_key": bool(cfg.api_key),
                "is_current": self.current_config and self.current_config.name == cfg.name
            }
            for cfg in self.configs
        ]


def call_model(config: ModelConfig, prompt: str, system_prompt: str = "", temperature: float = 0.7, max_retries: int = 3) -> str:
    last_exception = None
    for attempt in range(max_retries):
        try:
            logger.info(f"模型调用尝试 {attempt + 1}/{max_retries}")
            if config.provider == ProviderType.OLLAMA:
                result = _call_ollama(config, prompt, system_prompt, temperature)
            else:
                result = _call_openai_compatible(config, prompt, system_prompt, temperature)
            
            if not result or not result.strip():
                logger.warning(f"模型返回空内容，第 {attempt + 1} 次尝试")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise Exception("模型连续多次返回空内容")
            
            logger.info(f"模型调用成功（第 {attempt + 1} 次尝试）")
            return result
            
        except Exception as e:
            last_exception = e
            logger.warning(f"模型调用失败，第 {attempt + 1} 次尝试", details={"error": str(e), "attempt": attempt + 1}, exc_info=True)
            if attempt < max_retries - 1:
                time.sleep(2)
    
    public_safe_msg = f"模型调用失败，已尝试 {max_retries} 次，请检查模型服务配置和网络连接后重试"
    logger.error(public_safe_msg, exc_info=True)
    raise Exception(public_safe_msg) from last_exception

async def call_model_async(config: ModelConfig, prompt: str, system_prompt: str = "", temperature: float = 0.7, max_retries: int = 3) -> str:
    """异步版本的模型调用 - 带完整重试机制"""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, call_model, config, prompt, system_prompt, temperature, max_retries)


def _call_ollama(config: ModelConfig, prompt: str, system_prompt: str, temperature: float) -> str:
    # Ollama 使用 /api/generate 端点（兼容旧版）
    chat_url = f"{config.api_base}/api/generate"
    
    # 合并 system_prompt 和 prompt
    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"
    
    payload = {
        "model": config.model_name,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "top_k": 40
        }
    }

    try:
        response = requests.post(chat_url, json=payload, timeout=300)
        response.raise_for_status()
        result = response.json()
        
        content = result.get("response", "")
        
        if token_tracker:
            if "usage" in result:
                usage = result["usage"]
                token_tracker.record_usage(
                    model_name=config.model_name,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    provider="ollama"
                )
            else:
                token_tracker.record_usage_estimation(
                    model_name=config.model_name,
                    prompt_text=full_prompt,
                    completion_text=content,
                    provider="ollama"
                )
        
        return content
    except Exception as e:
        logger.error(f"Ollama调用失败: {e}")
        raise


def _call_openai_compatible(config: ModelConfig, prompt: str, system_prompt: str, temperature: float) -> str:
    url = f"{config.api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json"
    }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": config.model_name,
        "messages": messages,
        "temperature": temperature,
        "stream": False
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=300)
        response.raise_for_status()
        result = response.json()
        
        content = result["choices"][0]["message"]["content"]
        
        full_prompt_text = ""
        for msg in messages:
            full_prompt_text += msg.get("content", "")
        
        if token_tracker:
            if "usage" in result:
                usage = result["usage"]
                token_tracker.record_usage(
                    model_name=config.model_name,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    provider=config.provider.value
                )
            else:
                token_tracker.record_usage_estimation(
                    model_name=config.model_name,
                    prompt_text=full_prompt_text,
                    completion_text=content,
                    provider=config.provider.value
                )
        
        return content
    except Exception as e:
        logger.error(f"OpenAI兼容API调用失败: {e}")
        raise


config_manager = ModelConfigManager()
