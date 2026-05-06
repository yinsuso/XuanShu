@echo off
echo === 玄枢智能体一键部署脚本 ===
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误：未检测到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)
pip install -r requirements.txt
echo 正在启动玄枢智能体...
python xuan_cli.py
pause