#!/bin/bash

# IP Camera Viewer 启动脚本

echo "======================================"
echo "IP Camera Viewer - 局域网摄像头监控"
echo "======================================"

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 Python3"
    exit 1
fi

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 检查虚拟环境
if [ -d "venv" ]; then
    echo "[1] 激活虚拟环境..."
    source venv/bin/activate
else
    echo "[1] 警告: 未找到虚拟环境 (venv)，尝试使用系统 Python..."
    # 只有在没有虚拟环境时才尝试安装依赖到用户目录
    pip3 install -q flask opencv-python requests netifaces 2>/dev/null
fi

echo "[2] 启动服务..."
echo ""

# 启动应用
python3 main.py
