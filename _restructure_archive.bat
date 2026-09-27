@echo off
setlocal
cd /d "%~dp0"

rem Restructure an existing photo archive: canonicalise names, reunite
rem companions, group every "__TO_SPLIT__" folder in the GUI, canonicalise
rem again, mark the groups, then check and fix compliance with
rem ARCHIVE_STANDARD.md. Motion photos whose video has not been extracted
rem into "__VIDEOS_EXTRACTED" are listed (and extracted under --apply) by
rem steps 2 and 4, and reported as X16 by step 7.
rem
rem Nothing is changed without --apply. With no arguments this is a dry run
rem over the configured archive root's current year. "--year ALL" runs every
rem year the root holds, oldest first, one run each.
rem
rem   _restructure_archive.bat
rem   _restructure_archive.bat --apply
rem   _restructure_archive.bat --year ALL
rem   _restructure_archive.bat "d:\__PHOTOS_BACKUP" --year 2024 --apply
rem   _restructure_archive.bat "d:\__PHOTOS_BACKUP" --year ALL --apply
rem   _restructure_archive.bat "\\NAS\PhotoBackup" --year 2024 --apply
rem   _restructure_archive.bat --list-to-split
rem
rem See tools\restructure_archive.py --help for the rest.

rem The tool is stdlib-only by design - a maintenance tool has to run when the
rem project's environment does not. Poetry's interpreter is preferred when it
rem is there, so a run uses the same Python as the pipeline; a bare "python"
rem is a perfectly good fallback.
set "PY=python"
where poetry >nul 2>&1
if not errorlevel 1 set "PY=poetry run python"

%PY% "tools\restructure_archive.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Nothing left to do.
) else if "%EXIT_CODE%"=="1" (
    echo Finished - changes are still pending, or a step reported failures.
) else (
    echo [ERROR] Restructure stopped with code %EXIT_CODE%.
)
echo.
PAUSE
exit /b %EXIT_CODE%
