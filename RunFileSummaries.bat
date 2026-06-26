@echo off
setlocal EnableExtensions

REM ===== Portable root = folder where this BAT lives =====
set "ROOT=%~dp0"
cd /d "%ROOT%" || (echo [ERROR] Cannot cd to "%ROOT%" & exit /b 1)

REM ===== Run the script (only scans inside ROOT because FileSummaries.py uses its own folder as ROOT_FOLDER) =====
python "%ROOT%FileSummaries.py"
if errorlevel 1 (
  echo [ERROR] FileSummaries.py failed.
  exit /b 1
)

echo.
echo [OK] Done.
pause
endlocal
