@echo off
chcp 65001 >nul
title IP Camera Viewer (Docker)

echo ======================================
echo IP Camera Viewer - 局域网摄像头监控
echo ======================================

REM 检查Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Docker，请先安装 Docker Desktop
    pause
    exit /b 1
)

REM 切换到脚本目录
cd /d "%~dp0"

REM 尝试创建 cameras_db.json 以免挂载为目录
if not exist cameras_db.json (
    echo {} > cameras_db.json
)

echo [1] 启动 Docker 服务...
echo.

docker compose up -d --build
if errorlevel 1 (
    echo 尝试回退到 docker-compose...
    docker-compose up -d --build
)

echo.
echo ======================================
echo 服务已在 Docker 中启动！
echo 本地访问: http://localhost:8080
echo 停止服务: docker compose down
echo 查看日志: docker compose logs -f
echo ======================================

pause
