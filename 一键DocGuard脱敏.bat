@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo   启动 DocGuard - 原生脱敏工具 (Windows版)
echo ==========================================

IF NOT EXIST ".venv\" (
    echo [系统] 首次运行，正在创建虚拟环境并安装依赖，这可能需要几分钟时间...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) ELSE (
    call .venv\Scripts\activate.bat
)

IF NOT EXIST "input\" (
    mkdir input
    echo [提示] 已自动创建 input 文件夹。
    echo [提示] 请把待脱敏的 Word/PDF/Excel/PPT 文件放入 input 文件夹中。
    echo [提示] 放置好文件后，按任意键继续...
    pause
)

python main.py

echo.
echo 程序运行结束，按任意键关闭窗口...
pause
