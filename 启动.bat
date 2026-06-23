@echo off
chcp 65001 >nul 2>&1
title QQ 空间相册导出器
cd /d "%~dp0"

echo.
echo   ╔══════════════════════════════════════════╗
echo   ║     QQ 空间相册导出器 v1.2               ║
echo   ║     一键导出所有相册原图                  ║
echo   ╚══════════════════════════════════════════╝
echo.

:: ── 检查 Python ──
python --version >nul 2>&1
if errorlevel 1 (
    echo   [错误] 未检测到 Python，请先安装 Python 3.8+
    echo   下载地址: https://www.python.org/downloads/
    echo   安装时请勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

:: ── 检查并安装依赖 ──
echo   [1/2] 检查依赖...
pip show flask requests selenium webdriver-manager >nul 2>&1
if errorlevel 1 (
    echo   正在安装依赖 (flask requests selenium webdriver-manager)...
    pip install flask requests selenium webdriver-manager -q --disable-pip-version-check
    if errorlevel 1 (
        echo   [错误] 依赖安装失败，请检查网络连接后重试
        pause
        exit /b 1
    )
    echo   依赖安装完成
) else (
    echo   依赖已就绪
)

:: ── 启动 ──
echo.
echo   [2/2] 启动服务...
echo   浏览器将自动打开 http://localhost:5800
echo   关闭此窗口即可停止服务
echo.
start "" http://localhost:5800
python app.py

pause
