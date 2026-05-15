---
name: file_open
description: 使用系统默认程序打开文件，模拟双击打开的效果。支持文档、图片、视频、网页等各种文件类型。当需要用系统默认程序打开文件、预览文档、播放媒体或启动应用程序时调用此技能。
category: io
requires_confirmation: True
version: "1.0"
author: 破执
tags: ["file", "open", "launch", "default-app", "preview"]
parameters:
  - name: "path"
    type: "string"
    description: "要打开的文件路径（绝对路径或相对项目根目录的路径）"
    required: true
  - name: "application"
    type: "string"
    description: "指定用哪个程序打开（可选）。如未指定则使用系统默认程序"
    required: false
    default: ""
  - name: "wait"
    type: "boolean"
    description: "是否等待程序关闭后再返回（默认 False）"
    required: false
    default: false
---

## Core Capability
使用系统默认关联程序打开指定文件，效果等同于用户在文件管理器中双击该文件。支持 Windows、Linux、macOS 三平台，可打开文档、图片、视频、音频、网页、可执行文件等各种类型。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **预览文档**：打开 PDF、Word、Excel、PPT 等文档查看
- **查看图片**：打开图片文件进行预览
- **播放媒体**：打开视频或音频文件播放
- **打开网页**：用浏览器打开本地 HTML 文件
- **启动应用**：打开可执行文件或应用程序
- **查看日志**：用文本编辑器打开日志文件
- **打开项目**：用 IDE 打开项目文件或目录

**判断标准**：当需要"打开"某个文件让用户查看或编辑时，使用此技能。

## Parameters

| Name        | Type    | Description                                           | Required | Default |
| ----------- | ------- | ----------------------------------------------------- | -------- | ------- |
| path        | string  | 要打开的文件路径                                      | Yes      | -       |
| application | string  | 指定程序名称（可选）                                  | No       | ""      |
| wait        | boolean | 是否等待程序关闭后返回                                | No       | false   |

## Supported Platforms

| 平台    | 打开方式     | 说明                          |
| ------- | ------------ | ----------------------------- |
| Windows | `start` 命令 | 调用系统默认关联程序          |
| Linux   | `xdg-open`   | 使用 xdg-utils 打开           |
| macOS   | `open`       | 使用 open 命令                |

## Example Usage

### 场景1：打开 PDF 文档
```json
{
  "skill": "file_open",
  "args": {
    "path": "./docs/说明书.pdf"
  }
}
```

### 场景2：用指定编辑器打开代码文件
```json
{
  "skill": "file_open",
  "args": {
    "path": "./src/main.py",
    "application": "notepad.exe"
  }
}
```

### 场景3：打开图片预览
```json
{
  "skill": "file_open",
  "args": {
    "path": "/home/user/screenshots/error.png"
  }
}
```

### 场景4：打开视频文件
```json
{
  "skill": "file_open",
  "args": {
    "path": "./videos/demo.mp4"
  }
}
```

### 场景5：用 VS Code 打开项目
```json
{
  "skill": "file_open",
  "args": {
    "path": "./my-project",
    "application": "code"
  }
}
```

### 场景6：等待程序关闭（适合需要确认的情况）
```json
{
  "skill": "file_open",
  "args": {
    "path": "./config.ini",
    "application": "notepad",
    "wait": true
  }
}
```

## Execution Signature
```python
def execute(path: str, application: str = "", wait: bool = False, **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
```
✅ 已使用默认程序打开: 说明书.pdf
```
或
```
✅ 已使用 notepad.exe 打开: main.py
```

### 错误返回
- 路径不存在：`❌ 路径不存在: /path/to/file`
- 程序未找到：`❌ 未找到程序: xxx。请确认程序已安装`
- 打开失败：`❌ 打开文件失败: [错误信息]`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **file_list → file_open**：先列出文件，再打开目标文件
2. **file_write → file_open**：生成文件后用默认程序打开查看
3. **shell_exec → file_open**：查找文件后打开

## Best Practices（最佳实践）

1. **优先使用默认程序**：不指定 application，让系统决定最合适的程序
2. **相对路径**：可以使用相对于项目根目录的路径
3. **等待模式**：仅在需要用户操作后再继续时使用 wait=true
4. **目录打开**：传入目录路径可以用文件管理器打开该目录

## Safety Notes（安全提示）

- **确认机制**：该技能默认需要用户确认后执行
- **路径验证**：会自动验证路径是否存在
- **程序安全**：指定程序时，确保程序来源可信
- **资源占用**：打开大文件或程序可能消耗较多系统资源

## Notes
- 支持打开文件和目录（文件夹）
- Windows 使用 `start` 命令，Linux 使用 `xdg-open`，macOS 使用 `open`
- 该技能接受额外参数通过 `**kwargs`；未知参数会被安全忽略
- 打开操作是异步的（wait=false 时），不会阻塞 Agent 执行
