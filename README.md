# 🤖 玄枢 (XuanShu) v5.0

**一个具备自进化能力的本地AI智能体集群系统**

玄枢 (XuanShu) 不仅仅是一个对话界面，它是一个能够自我反思、自我升级并支持局域网协作的认知系统。它遵循“本地优先”原则，确保所有数据不出域，打造真正的私人数字大脑。

## 主要是针对用户：
- **1.本地不是大模型而开发的项目，通过局域网协作模式可以将多台1080、2080等显卡并联协作。**
- **2.有保密需要的设备在本地部署模型，防止泄露**
- **3.本地、无后门、开源、可自己进行优化升级**

## ✨ 核心特性

- **🧠 自进化认知**：内置 `EvolutionEngine`，能够从错误中学习并自动生成新的 Python 技能插件。
- **🌐 局域网协作**：支持一键创建/加入协作房间，实现多台设备间的 AI 协同工作。
- **💾 双轨记忆系统**：结合 SQLite (高性能潜意识) 与 Markdown (可编辑意识)，实现长期记忆的精准检索与人工引导。
- **🎨 三大视觉境界**：提供【原点·极简黑】、【空灵·禅意白】、【赛博·霓虹蓝】三套完整视觉方案，适配不同心境。
- **👁️ Web 资源直显**：完美支持模型生成的图片、音频、视频在 Web 端直接预览。

## 🚀 快速开始

### 环境要求
- Python 3.10+
- Ollama (本地模型运行环境)

### 安装部署
**Windows 用户：**
```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活虚拟环境
.\venv\Scripts\activate

# 3. 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 4. 启动项目
python launcher.py
```


**macOS 用户：**
```bash
chmod +x setup_mac.sh
./setup_mac.sh
source venv/bin/activate
python3 launcher.py
```

**Linux 用户：**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 launcher.py
```

## 🛠️ 技术栈
- **Backend**: FastAPI, SQLite (WAL), Python 3.10
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **LLM**: Ollama / OpenAI / DeepSeek / Moonshot (适配多种 Provider)


## AI声明：
本项目由 qwen3.5 、step-3.5-flash 与 gemma 4 模型提供技术辅助，部分代码由这两个代码编写并审核。


## 📜 开源协议
本项目采用 **Apache License 2.0** 协议开源。
