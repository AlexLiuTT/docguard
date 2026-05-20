#!/bin/bash

# 获取脚本所在目录的绝对路径
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=========================================="
echo "  启动 DocGuard - 原生脱敏工具"
echo "=========================================="

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "首次运行，正在创建虚拟环境并安装依赖，这可能需要几分钟时间..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

# 检查 input 文件夹
if [ ! -d "input" ]; then
    mkdir input
    echo "已创建 input 文件夹。请把待脱敏的 PDF 和 Word (.docx) 文件放入 input 文件夹中。"
    echo "放置好文件后，按回车键继续..."
    read -r
fi

# 运行主程序
python main.py

echo ""
echo "程序运行结束，按回车键关闭窗口..."
read -r
exit 0
