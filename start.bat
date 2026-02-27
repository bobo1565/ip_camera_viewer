@echo off
chcp 65001 >nul
title IP Camera Viewer

echo ======================================
echo IP Camera Viewer - 局域网摄像头监控
echo ======================================

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python
    pause
    exit /b 1
)

echo [1] 检查依赖...
pip install -q flask opencv-python requests netifaces 2>nul

echo [2] 启动服务...
echo.

REM 切换到脚本目录
cd /d "%~dp0"

REM 启动应用
python main.py

pause
