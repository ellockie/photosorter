@echo off
cd /d "%~dp0"
rem Use the Poetry venv's pytest; a bare "pytest"/"python -m pytest" may resolve
rem to a system-wide interpreter without the project's dependencies.
poetry run python -m pytest %*
PAUSE
