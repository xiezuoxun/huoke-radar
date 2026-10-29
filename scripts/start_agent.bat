@echo off
chcp 65001 >nul
title 线索雷达 - 本地采集服务
rem 用绝对路径，不依赖 %~dp0：这个 bat 复制到桌面也能直接用
cd /d "C:\Users\lenovo\WorkBuddy\2026-10-26-19-20-54\collector"

rem 本机回环地址不能走代理：公司网络 / VPN / 抓包工具常会设 http_proxy，
rem 那会让页面访问 127.0.0.1 被代理拦下（表现就是"连接不上"）。
set "no_proxy=127.0.0.1,localhost"
set "NO_PROXY=127.0.0.1,localhost"

set "PY=C:\Users\lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" (
  echo [x] 找不到隔离环境的 python：
  echo     %PY%
  echo     请先运行 install.bat
  pause
  exit /b 1
)

echo.
echo  正在启动本地采集服务，启动后不要关这个窗口。
echo  保持运行 = 工作台的「开始采集」按钮可用
echo  关掉窗口 = 按钮失效（页面会提示未连接）
echo.

"%PY%" agent_server.py --port 8765
echo.
echo 服务已退出。
pause
