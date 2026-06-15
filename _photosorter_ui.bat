@echo off
setlocal
cd /d "%~dp0"

rem Single call: starts the dashboard server, opens the web UI in the browser,
rem and serves until you click "Stop server" in the dashboard (or press Ctrl+C).
rem Re-running while a server is already up just reopens the existing dashboard.

rem Ensure Poetry is available.
where poetry >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Poetry is not on PATH.
    exit /b 1
)

rem Self-heal if Poetry switched to a new env after Python updates.
rem Validate core runtime deps before launch.
call poetry run python -c "import colorama, dateutil.parser, pandas, exiftool, fastapi, uvicorn, websockets" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Poetry environment is missing dependencies. Running install...
    call poetry install --no-interaction
    if errorlevel 1 (
        echo [ERROR] poetry install failed.
        exit /b 1
    )
)

call poetry run python "src\main.py" --ui
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Server stopped.
) else (
    echo [ERROR] Dashboard exited with code %EXIT_CODE%.
)
echo.
exit /b %EXIT_CODE%
