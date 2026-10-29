@echo off
setlocal enabledelayedexpansion
title Line Radar - Start

rem ===========================================================
rem  KEEP THIS FILE 100 PERCENT ASCII.
rem  Chinese chars in a .bat get mangled by cmd GBK codepage
rem  and silently break every command after them.
rem ===========================================================

set "DIR=C:\Users\lenovo\WorkBuddy\2026-10-26-19-20-54\collector"
set "PY=C:\Users\lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
set "no_proxy=127.0.0.1,localhost"
set "NO_PROXY=127.0.0.1,localhost"

echo.
echo   Line Radar - starting...
echo.

if not exist "%DIR%\launch_workbench.py" goto NO_DIR
if not exist "%PY%" goto NO_PY

cd /d "%DIR%"

rem launch_workbench.py does everything:
rem   - reuses the running agent if port 8765 is already up
rem   - otherwise starts it
rem   - opens http://127.0.0.1:8765/app (same-origin page, no CORS/PNA block)
"%PY%" "launch_workbench.py"
set "RC=!errorlevel!"
if not "!RC!"=="0" goto FAIL
goto END

:NO_DIR
echo   [x] Program folder not found:
echo       %DIR%
echo.
pause
goto END

:NO_PY
echo   [x] Python runtime not found:
echo       %PY%
echo       Run install.bat inside that folder first.
echo.
pause
goto END

:FAIL
echo.
echo   [x] Start failed. Check log:
echo       %DIR%\debug\agent.log
echo.
pause
goto END

:END
exit /b 0
