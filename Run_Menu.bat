@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM Portable launcher for NWS Tools
REM - Works from any location / shortcut
REM - Forces working directory to this folder
REM - Sets PROJ_LIB + PYTHONPATH relative to this folder
REM ============================================================

REM Folder this BAT lives in (trailing backslash)
set "APPROOT=%~dp0"
cd /d "%APPROOT%"

REM Make local imports work when running .py
set "PYTHONPATH=%APPROOT%"

REM ---- Set PROJ_LIB if proj.db exists in common portable layouts ----
set "PROJ_LIB="

if exist "%APPROOT%Street Database\share\proj\proj.db" (
  set "PROJ_LIB=%APPROOT%Street Database\share\proj"
) else if exist "%APPROOT%Street Database\proj\proj.db" (
  set "PROJ_LIB=%APPROOT%Street Database\proj"
) else if exist "%APPROOT%Street Database\bin\proj.db" (
  set "PROJ_LIB=%APPROOT%Street Database\bin"
)

if not "%PROJ_LIB%"=="" (
  echo [OK] PROJ_LIB set to: "%PROJ_LIB%"
) else (
  echo [WARN] proj.db not found in portable folders. PROJ_LIB not set.
)

echo [INFO] APPROOT: "%APPROOT%"
echo [INFO] CWD: "%CD%"
echo.

REM ---- Prefer EXE if present ----
if exist "%APPROOT%NWS_Tools.exe" (
  echo [RUN] Launching EXE: NWS_Tools.exe
  "%APPROOT%NWS_Tools.exe"
  set "RC=%ERRORLEVEL%"
  echo.
  echo [EXIT] EXE returned code: !RC!
  echo.
  pause
  exit /b !RC!
)

REM ---- Fallback: run Menu.py with Python if EXE not present ----
if exist "%APPROOT%Menu.py" (
  echo [RUN] EXE not found. Running Python: Menu.py
  py -3 "%APPROOT%Menu.py"
  set "RC=%ERRORLEVEL%"
  echo.
  echo [EXIT] Python returned code: !RC!
  echo.
  pause
  exit /b !RC!
)

echo [ERROR] Neither NWS_Tools.exe nor Menu.py found in:
echo        "%APPROOT%"
echo.
pause
exit /b 1
