---
name: text_to_speech
description: 通过免费 TTS 接口将文字转换为语音文件（MP3 格式），支持 90+ 种语音选择。当用户要求"语音"、"读出来"、"转语音"或 Agent 需要将文字内容转为语音文件时使用。
category: media
requires_confirmation: false
version: "1.0"
author: 玄枢
tags: ["tts", "speech", "voice", "audio", "media", "mp3"]
parameters:
  - name: text
    type: string
    description: 要转换为语音的文本内容。纯文本格式，建议提前去除 HTML 标签，以 \n 为换行符。单次转换字符数上限 10,000 字，超出需分段生成。
    required: true
  - name: voice
    type: string
    description: 语音 ID，决定发音人。如 zh-CN-YunyangNeural（男声·阳光）。默认 zh-CN-YunyangNeural。
    required: false
    default: "zh-CN-YunyangNeural"
  - name: speed
    type: number
    description: 语速，范围 0.25-3.0。1.0 为正常语速，0.5 为半速，2.0 为双倍速。默认 0.9。
    required: false
    default: 0.9
  - name: pitch
    type: string
    description: 音调，范围 -50 到 +50。0 为原音调，负值降低音调，正值提高音调。默认 "0"。
    required: false
    default: "0"
  - name: style
    type: string
    description: 语音风格，影响情感表达。不同风格适用于不同场景，如 newscast 适合新闻，affectionate 适合亲切交流。
    required: false
    default: "general"
    enum: ["general", "assistant", "chat", "customerservice", "newscast", "affectionate", "calm", "cheerful", "gentle", "lyrical", "serious"]
  - name: output_file
    type: string
    description: 输出文件路径，默认使用系统临时目录自动生成。如需保存到特定位置，请提供绝对路径。
    required: false
    default: ""
---

## Core Capability
通过免费 TTS 接口将文字转换为语音文件（MP3 格式），支持 90+ 种语音选择。生成后以文件形式返回绝对路径，可直接播放或下载。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **语音播报**：用户要求"读出来"、"语音播报"、"转成语音"
- **内容转换**：将文章、新闻、故事转换为语音文件
- **辅助阅读**：为视力不便用户将文字内容转为语音
- **批量生成**：将多条文本批量转换为语音文件
- **多语言支持**：需要生成英文、日文等其他语言的语音（选择对应 voice ID）
- **风格定制**：需要特定风格的语音，如新闻播报、客服、抒情等

**判断标准**：当需要将文本内容转换为语音文件（MP3）时，使用此技能。

## Parameters

| Name       | Type   | Description                                           | Required | Default                |
| ---------- | ------ | ----------------------------------------------------- | -------- | ---------------------- |
| text       | string | 要转换为语音的文本内容                                | Yes      | -                      |
| voice      | string | 语音 ID，见下方语音列表                               | No       | zh-CN-YunyangNeural    |
| speed      | number | 语速，范围 0.25-3.0                                   | No       | 0.9                    |
| pitch      | string | 音调，范围 -50 到 +50                                 | No       | "0"                    |
| style      | string | 语音风格                                              | No       | general                |
| output_file| string | 输出文件路径                                          | No       | 系统临时目录           |

## TTS Interface Details（接口详情）

**接口地址：**
```
https://tts.wangwangit.com/v1/audio/speech
```

**请求方式：** POST，Content-Type: application/json

**请求体：**
```json
{
    "input": "要说的话",
    "voice": "zh-CN-YunjianNeural",
    "speed": 0.9,
    "pitch": "0",
    "style": "general"
}
```

**参数说明：**
- `input`（必填）：要转换的文本
- `voice`（必填）：语音 ID，见下方语音列表
- `speed`：速度，范围 0.25-3.0，默认 1.0
- `pitch`：音调，范围 -50 到 +50，默认 0
- `style`：语音风格，默认 `general`

## Style Guide（风格选择指南）

| 风格            | 适用场景                     | 示例用法           |
| --------------- | ---------------------------- | ------------------ |
| `general`       | 通用场景，默认选择           | 日常文本转换       |
| `assistant`     | 助手对话，专业且友好         | AI 助手回复语音    |
| `chat`          | 闲聊对话，轻松自然           | 社交应用语音消息   |
| `customerservice` | 客服场景，耐心专业         | 客服系统语音播报   |
| `newscast`      | 新闻播报，正式清晰           | 新闻文章语音       |
| `affectionate`  | 亲切交流，温暖柔和           | 亲子应用、关怀场景 |
| `calm`          | 平静舒缓，放松身心           | 冥想、助眠内容     |
| `cheerful`      | 欢快愉悦，积极向上           | 节日祝福、好消息   |
| `gentle`        | 温柔细腻，轻声细语           | 睡前故事、诗歌     |
| `lyrical`       | 抒情诗意，富有感情           | 散文、诗歌朗诵     |
| `serious`       | 严肃正式，庄重沉稳           | 公告、声明、法律文本 |

## Common Voice IDs（常用语音 ID）

### 中文（推荐）

| 语音ID | 名称 | 性别/风格 | 推荐场景 |
|--------|------|----------|----------|
| zh-CN-XiaoxiaoNeural | 晓晓 | 女声·温柔 | 通用、助手 |
| zh-CN-YunxiNeural | 云希 | 男声·清朗 | 通用、新闻 |
| zh-CN-YunyangNeural | 云扬 | 男声·阳光 | 通用、客服 |
| zh-CN-XiaoyiNeural | 晓伊 | 女声·甜美 | 社交、聊天 |
| zh-CN-YunjianNeural | 云健 | 男声·稳重 | 商务、正式 |
| zh-CN-XiaochenNeural | 晓辰 | 女声·知性 | 教育、知识 |
| zh-CN-XiaohanNeural | 晓涵 | 女声·优雅 | 文学、艺术 |
| zh-CN-XiaomoNeural | 晓墨 | 女声·文艺 | 诗歌、散文 |
| zh-CN-XiaoruiNeural | 晓睿 | 女声·智慧 | 科技、专业 |
| zh-CN-XiaoshuangNeural | 晓双 | 女声·活泼 | 儿童、娱乐 |
| zh-CN-XiaoxuanNeural | 晓萱 | 女声·清新 | 自然、生活 |
| zh-CN-YunfengNeural | 云枫 | 男声·磁性 | 广播、主持 |
| zh-CN-YunhaoNeural | 云皓 | 男声·豪迈 | 体育、游戏 |
| zh-CN-YunzeNeural | 云泽 | 男声·深沉 | 历史、纪录片 |

> 完整语音列表请参考：https://tts.wangwangit.com/

## Example Usage

### 场景1：简单文本转语音
```json
{
  "skill": "text_to_speech",
  "args": {
    "text": "你好，这是玄枢项目的语音测试。",
    "voice": "zh-CN-YunyangNeural",
    "speed": 0.9,
    "pitch": "0",
    "style": "general"
  }
}
```

### 场景2：新闻播报风格
```json
{
  "skill": "text_to_speech",
  "args": {
    "text": "今日科技新闻：人工智能技术取得重大突破，新型大语言模型在多项基准测试中创下新纪录。",
    "voice": "zh-CN-YunxiNeural",
    "speed": 1.0,
    "style": "newscast"
  }
}
```

### 场景3：指定输出路径
```json
{
  "skill": "text_to_speech",
  "args": {
    "text": "欢迎使用玄枢智能助手，我将竭诚为您服务。",
    "voice": "zh-CN-XiaoxiaoNeural",
    "style": "assistant",
    "output_file": "J:/xuanshuceshiban/audio/welcome.mp3"
  }
}
```

### 场景4：抒情风格朗读诗歌
```json
{
  "skill": "text_to_speech",
  "args": {
    "text": "春眠不觉晓，处处闻啼鸟。夜来风雨声，花落知多少。",
    "voice": "zh-CN-XiaomoNeural",
    "speed": 0.8,
    "pitch": "-5",
    "style": "lyrical"
  }
}
```

## Execution Signature
```python
def execute(text: str, voice: str = "zh-CN-YunyangNeural", speed: float = 0.9, pitch: str = "0", style: str = "general", output_file: str = "", **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
返回生成的语音文件绝对路径：

```
✅ 语音生成成功
文件路径: C:/Users/username/AppData/Local/Temp/tts_output_12345678.mp3
语音参数:
  - 文本长度: 24 字符
  - 语音: zh-CN-YunyangNeural
  - 语速: 0.9
  - 风格: general
```

### 错误返回
- 文本为空：`❌ 错误: 文本内容不能为空`
- 文本过长：`❌ 错误: 文本长度超过 10,000 字符限制，请分段生成`
- 网络错误：`❌ 错误: TTS 接口请求失败: [错误详情]`
- 语音 ID 无效：`❌ 错误: 无效的语音 ID: xxx`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **web_fetch → text_to_speech**：抓取网页文章 → 转换为语音朗读
2. **file_read → text_to_speech**：读取文本文件内容 → 转换为语音
3. **text_to_speech → file_write**：生成语音后，记录生成日志
4. **database_query → text_to_speech**：查询数据 → 将结果播报为语音

## Best Practices（最佳实践）

1. **文本预处理**：去除 HTML 标签、特殊符号，确保文本为纯文本格式
2. **分段生成**：文本超过 10,000 字时，按段落或章节分段生成，然后合并
3. **语速调整**：新闻类内容用 1.0；故事类用 0.8-0.9；快速播报用 1.2-1.5
4. **风格匹配**：根据内容类型选择合适的风格，提升听众体验
5. **音调微调**：女声可适当提高音调（+5 到 +10），男声保持默认或略降（-5 到 0）

## Safety Notes（安全提示）

- **内容审核**：转换前确保文本内容合法合规，不包含有害信息
- **版权注意**：转换受版权保护的内容时，确保已获得授权
- **隐私保护**：不要将包含个人隐私的文本转换为语音后分享给他人

## Notes
- 接口免费，无 API 密钥
- 单次转换字符数上限 10,000 字，超出需分段生成
- 支持任意音频文件格式（MP3/WAV/OGG/AMR等）
- 需要设置合理的 headers 保证调用成功
- 内容为纯文本格式，请提前去除 html 标签，以 \n 为换行符
- 生成后返回文件绝对路径
- 文件保存到系统临时目录下，使用绝对路径
- 参考地址：https://tts.wangwangit.com/
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
