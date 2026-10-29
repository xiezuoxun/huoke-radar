@echo off
chcp 65001 >nul
title 线索雷达 - 自检
rem 用绝对路径，不依赖 %~dp0：这个 bat 复制到桌面也能直接用
cd /d "C:\Users\lenovo\WorkBuddy\2026-10-26-19-20-54\collector"
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

"%PY%" selfcheck.py
echo.
pause
