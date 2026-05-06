#!/bin/bash
echo "=== 玄枢智能体一键部署脚本 ==="
# 检测 Python
if ! command -v python &> /dev/null; then
    echo "错误：未检测到 Python，请先安装 Python 3.9+"
    exit 1
fi
echo "正在安装依赖..."
pip install -r requirements.txt
echo "正在启动玄枢智能体..."
python xuan_cli.py