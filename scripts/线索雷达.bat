@echo off
chcp 65001 >nul
title 线索雷达 - 启动
setlocal

rem ============================================================
rem  线索雷达 · 一键启动（起服务 + 开工作台）
rem  本文件会被杀软/清理工具误删，collector 目录里有备份副本
rem ============================================================

set "DIR=C:\Users\lenovo\WorkBuddy\2026-10-26-19-20-54\collector"
set "PY=C:\Users\lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
set "no_proxy=127.0.0.1,localhost"
set "NO_PROXY=127.0.0.1,localhost"

echo.
echo   线索雷达 · 正在启动...
echo.

if not exist "%DIR%\launch_workbench.py" (
  echo   [x] 找不到程序目录：
  echo       %DIR%
  echo       文件夹可能被移动或删除了。
  pause
  exit /b 1
)

if not exist "%PY%" (
  echo   [x] 找不到 python 运行环境：
  echo       %PY%
  echo       请双击 %DIR%\install.bat 重装
  pause
  exit /b 1
)

cd /d "%DIR%"

rem 服务已在跑就直接开页面，不重复启动
"%PY%" -c "import socket,sys; s=socket.socket(); s.settimeout(0.6); sys.exit(0) if s.connect_ex(('127.0.0.1',8765))==0 else sys.exit(1)"
if %errorlevel%==0 (
  echo   [i] 采集服务已在运行，直接打开工作台。
  start "" "https://www.workbuddy.cn/space/d/8Ga6KQowmacfSimrnvZHUh"
  timeout /t 2 >nul
  exit /b 0
)

"%PY%" "launch_workbench.py"
if %errorlevel% neq 0 (
  echo.
  echo   [x] 启动失败，上面是报错信息。
  echo       日志：%DIR%\debug\agent.log
  echo.
  pause
)
exit /b 0
