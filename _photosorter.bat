@echo off
setlocal
cd /d "%~dp0"

rem Ensure Poetry is available.
where poetry >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Poetry is not on PATH.
    exit /b 1
)

rem Self-heal if Poetry switched to a new env after Python updates.
rem Validate core runtime deps before launch.
call poetry run python -c "import colorama, dateutil.parser, pandas, exiftool" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Poetry environment is missing dependencies. Running install...
    call poetry install --no-interaction
    if errorlevel 1 (
        echo [ERROR] poetry install failed.
        exit /b 1
    )
)

call poetry run python "src\main.py"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Done
) else (
    echo [ERROR] Photosorter exited with code %EXIT_CODE%.
)
echo.
exit /b %EXIT_CODE%

