@echo off
chcp 65001 >nul
setlocal

set "DIR=C:\Users\lenovo\WorkBuddy\2026-10-26-19-20-54\collector"
set "PY=C:\Users\lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

cd /d "%DIR%"
if not exist "%PY%" (
  echo [x] 找不到 python：%PY%
  pause
  exit /b 1
)

"%PY%" "%DIR%\launch_workbench.py" --stop
timeout /t 1 >nul
exit /b 0
