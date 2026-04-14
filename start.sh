#!/bin/bash

# IP Camera Viewer 启动脚本

echo "======================================"
echo "IP Camera Viewer - 局域网摄像头监控 (Docker)"
echo "======================================"

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "错误: 未找到 Docker，请先安装 Docker"
    exit 1
fi

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 尝试创建 cameras_db.json 以免挂载为目录
if [ ! -f "cameras_db.json" ]; then
    echo "{}" > cameras_db.json
fi

# 清理 macOS 下因为在外部存储介质上可能产生的 ._ 缓存文件导致 Docker 构建失败的问题
find . -name "._*" -type f -delete 2>/dev/null

echo "[1] 启动 Docker 服务..."
echo ""

# 使用 docker ps 获取是否运行中
if docker compose &> /dev/null; then
    docker compose up -d --build
else
    docker-compose up -d --build
fi

echo ""
echo "======================================"
echo "服务已在 Docker 中启动！"
echo "本地访问: http://localhost:8080"
echo "停止服务: docker compose down"
echo "查看日志: docker compose logs -f"
echo "======================================"

