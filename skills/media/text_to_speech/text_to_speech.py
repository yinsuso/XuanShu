"""
文字转语音技能。
通过免费TTS接口将文字转换为语音文件（MP3格式），支持90+种语音选择。
Author: 玄枢
Date: 2026-05-14
"""

import os
import tempfile
import requests
from pathlib import Path

from logger import logger

# 技能元数据
SKILL_NAME = "text_to_speech"
SKILL_DESCRIPTION = "通过免费TTS接口将文字转换为语音文件（MP3格式），支持90+种语音选择。"
SKILL_TRIGGER = "当用户要求'语音'、'读出来'、'转语音'或需要将文字内容转为语音文件时使用。"
SKILL_CATEGORY = "media"
SKILL_REQUIRES_CONFIRMATION = False
SKILL_PARAMETERS = [
    {
        "name": "text",
        "type": "string",
        "description": "要转换为语音的文本内容（纯文本，建议提前去除HTML标签）"
    },
    {
        "name": "voice",
        "type": "string",
        "description": "语音ID，如 zh-CN-YunyangNeural。默认 zh-CN-YunyangNeural",
        "default": "zh-CN-YunyangNeural"
    },
    {
        "name": "speed",
        "type": "number",
        "description": "语速，范围 0.25-3.0，默认 0.9",
        "default": 0.9
    },
    {
        "name": "pitch",
        "type": "string",
        "description": "音调，范围 -50 到 +50，默认 '0'",
        "default": "0"
    },
    {
        "name": "style",
        "type": "string",
        "description": "语音风格",
        "default": "general",
        "enum": ["general", "assistant", "chat", "customerservice", "newscast", "affectionate", "calm", "cheerful", "gentle", "lyrical", "serious"]
    },
    {
        "name": "output_file",
        "type": "string",
        "description": "输出文件路径，默认使用系统临时目录生成",
        "default": ""
    }
]


def _get_temp_path() -> str:
    """获取跨平台临时文件路径。"""
    temp_dir = tempfile.gettempdir()
    return os.path.join(temp_dir, "tts_output.mp3")


def _generate_filename(text: str, voice: str) -> str:
    """根据文本和语音生成文件名。"""
    import hashlib
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    voice_name = voice.replace("-", "_")
    return f"tts_{voice_name}_{text_hash}.mp3"


def execute(
    text: str,
    voice: str = "zh-CN-YunyangNeural",
    speed: float = 0.9,
    pitch: str = "0",
    style: str = "general",
    output_file: str = "",
    **kwargs
) -> str:
    """
    执行文字转语音操作。

    Args:
        text: 要转换为语音的文本内容
        voice: 语音ID
        speed: 语速
        pitch: 音调
        style: 语音风格
        output_file: 输出文件路径，为空则使用临时目录
        **kwargs: 兼容额外参数

    Returns:
        生成的音频文件绝对路径，或错误信息
    """
    if not text or not text.strip():
        return "错误: text 参数不能为空"

    # 确定输出路径
    if output_file:
        output_path = os.path.abspath(output_file)
    else:
        temp_dir = tempfile.gettempdir()
        filename = _generate_filename(text, voice)
        output_path = os.path.join(temp_dir, filename)

    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    tts_url = "https://tts.wangwangit.com/v1/audio/speech"

    payload = {
        "input": text,
        "voice": voice,
        "speed": speed,
        "pitch": pitch,
        "style": style
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        logger.info(f"TTS请求: voice={voice}, speed={speed}, style={style}, text长度={len(text)}")
        response = requests.post(
            tts_url,
            json=payload,
            headers=headers,
            timeout=300
        )
        response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

        file_size = os.path.getsize(output_path)
        logger.info(f"TTS生成成功: {output_path}, 大小={file_size} bytes")

        return output_path

    except requests.exceptions.Timeout:
        logger.error("TTS请求超时")
        return "错误: TTS请求超时，请稍后重试"
    except requests.exceptions.RequestException as e:
        logger.error(f"TTS请求失败: {e}")
        return f"错误: TTS请求失败 - {str(e)}"
    except Exception as e:
        logger.error(f"TTS生成失败: {e}")
        return f"错误: TTS生成失败 - {str(e)}"
