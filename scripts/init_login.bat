@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

echo ==========================================================
echo  Huoke Radar - first-time login (run ONCE)
echo ==========================================================
echo.
echo  This opens a real browser window. In that window:
echo    1) log in to Douyin and Xiaohongshu
echo    2) if a slider captcha pops up, drag it manually
echo    3) come back here and press Enter
echo.
echo  Your login state is saved to .\browser_data\ and reused
echo  by every later run (including the daily headless task).
echo.
pause

REM ---------- pick python: prefer isolated venv (that is where playwright lives) ----------
set "PY="
set "ISOVENV=C:\Users\lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if exist "%ISOVENV%" (
    set "PY=%ISOVENV%"
) else (
    set "PY=python"
)

"%PY%" -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [!] playwright is not available for: %PY%
    echo     Run install.bat first, then run this again.
    pause
    exit /b 1
)

"%PY%" init_session.py
if errorlevel 1 (
  echo.
  echo [!] Some platforms are not ready. Run init_login.bat again.
)
echo.
pause
