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

# 安装依赖
echo "[1] 检查依赖..."
pip3 install -q flask opencv-python requests netifaces 2>/dev/null || pip install -q flask opencv-python requests netifaces 2>/dev/null

echo "[2] 启动服务..."
echo ""

# 切换到脚本目录
cd "$(dirname "$0")"

# 启动应用
python3 main.py
