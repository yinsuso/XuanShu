# 🚀 快速启动指南

## 一键启动（推荐）

现在有了 **智能启动器**，你只需要运行：

```bash
# 两种等价方式
python launcher.py
# 或
python xuan_cli.py
```

启动器会自动：
1. ✅ 检查Python版本
2. ✅ 检查并自动安装依赖
3. ✅ 检测Ollama状态
4. ✅ 自动启动Ollama（如果需要）
5. ✅ 列出已安装的模型
6. ✅ 帮助你选择或下载模型
7. ✅ 更新配置
8. ✅ 启动你选择的界面

## 传统启动方式

### 命令行界面

```bash
# 使用新版SkillAgent v4.0（推荐）
python agent.py

# 或使用旧版Agent v3.1（保留兼容）
python agent_v3_1.py
```

### Web界面

```bash
python web_app.py
```

然后打开浏览器访问：`http://localhost:30000`

### 注意事项

- 目前推荐使用 `launcher.py` 或 `xuan_cli.py` 作为统一启动入口
- 直接运行 `agent.py` 或 `web_app.py` 也是有效的，但缺少自动环境检测

## 前置准备

### 1. 安装Ollama

如果还没有安装Ollama，请先访问：
- https://ollama.com/download

下载并安装适合你系统的版本。

### 2. 拉取模型（可选）

虽然启动器会帮你下载，但你也可以预先拉取：

```bash
# 推荐模型（代码能力强）
ollama pull qwen2.5-coder:7b

# 或更轻量的模型
ollama pull phi3:3.8b

# 或通用模型
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
```

## 配置说明

所有配置都在 `config.py` 文件中，你可以通过环境变量覆盖：

```bash
# 更改模型
set MODEL_NAME=phi3:3.8b  # Windows
export MODEL_NAME=phi3:3.8b  # Linux/Mac

# 启用向量记忆
set USE_VECTOR_MEMORY=true
```

## 使用技巧

### 在交互界面中

- 输入 `skills` - 查看所有可用技能
- 输入 `clear` - 清空对话记忆
- 输入 `exit` / `quit` - 退出

### 使用技能

Agent会根据你的需要自动调用技能，例如：

| 你说的话 | 可能调用的技能 |
|---------|--------------|
| "帮我列出当前目录" | list_dir |
| "读取config.py文件" | read_file |
| "搜索Python教程" | web_search |
| "计算100以内的素数和" | run_code |

## 故障排除

### Ollama无法启动

检查Ollama是否安装：
```bash
ollama --version
```

手动启动Ollama：
```bash
ollama serve
```

### 依赖安装失败

尝试手动安装：
```bash
pip install -r requirements.txt
```

### 模型下载慢

你可以手动下载：
```bash
ollama pull qwen2.5-coder:7b
```

### 端口被占用

Web界面默认使用8000端口，你可以修改config.py或设置：
```bash
set WEB_PORT=8080
```

## 下一步

- 📖 阅读 [SKILLS_README.md](./SKILLS_README.md) 了解技能系统
- 📖 查看 [README.md](./README.md) 了解完整项目说明
- 🛠️ 创建自己的技能！
