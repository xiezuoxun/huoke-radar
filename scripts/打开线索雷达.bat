@echo off
chcp 65001 >nul
setlocal

rem 注意：这个脚本会被复制到桌面使用，所以路径不能靠 %~dp0 推（那样会指向桌面）。
set "DIR=C:\Users\lenovo\WorkBuddy\2026-10-26-19-20-54\collector"
set "PY=C:\Users\lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

cd /d "%DIR%"
if not exist "%PY%" (
  echo [x] 找不到隔离环境的 python：
  echo     %PY%
  echo     请先运行 %DIR%\install.bat
  pause
  exit /b 1
)
if not exist "%DIR%\launch_workbench.py" (
  echo [x] 找不到 launch_workbench.py：
  echo     %DIR%
  pause
  exit /b 1
)

"%PY%" "%DIR%\launch_workbench.py" %*
exit /b %errorlevel%
