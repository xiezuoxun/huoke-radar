@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

echo ==========================================
echo  Huoke Radar - install dependencies
echo ==========================================
echo.

REM ---------- pick python: prefer isolated venv, fallback to PATH ----------
set "PY="
set "ISOVENV=C:\Users\lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if exist "%ISOVENV%" (
    set "PY=%ISOVENV%"
    echo [python] using isolated venv: %ISOVENV%
) else (
    set "PY=python"
    echo [python] using PATH python
)
echo.

"%PY%" --version
if errorlevel 1 goto nopython
echo.

REM ---------- guard: NEVER let pip upgrade itself (it deletes pip and hangs on Windows) ----------
echo [0/2] pip health check ...
"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo     pip is broken or missing - repairing with ensurepip ...
    "%PY%" -m ensurepip --default-pip
    if errorlevel 1 goto fail
)
"%PY%" -m pip --version
echo.

echo [1/2] installing requirements ...
"%PY%" -m pip install -r requirements.txt --disable-pip-version-check --no-input
if errorlevel 1 (
    echo.
    echo     Retrying with Tsinghua mirror ...
    "%PY%" -m pip install -r requirements.txt --disable-pip-version-check --no-input -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 goto fail
)

echo.
echo [2/2] verifying playwright ...
"%PY%" -c "import playwright; from playwright._repo_version import version; print('playwright OK', version)"
if errorlevel 1 goto fail

echo.
echo ==========================================
echo  Done.
echo.
echo  Next step - log in once (opens a real browser):
echo    init_login.bat
echo.
echo  Then run a real collection:
echo    "%PY%" huoke_collector.py --mode browser --keyword YOUR_KEYWORD --platform douyin xhs
echo.
echo  Note: this project reuses your local Chrome (CDP / channel=chrome),
echo        so you do NOT need "playwright install chromium".
echo  Note: never run "pip install --upgrade pip" inside this venv -
echo        pip deletes itself first and the install hangs on Windows.
echo ==========================================
pause
exit /b 0

:nopython
echo.
echo [X] Python not found. Install Python 3.10+ and tick "Add to PATH".
pause
exit /b 1

:fail
echo.
echo [X] Install failed. Check network, then retry:
echo     "%PY%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.
echo     If pip itself is broken, repair it with:
echo     "%PY%" -m ensurepip --default-pip
pause
exit /b 1
