@echo off
setlocal EnableExtensions

REM ============================================================
REM Run GoogleSheets_Menu.py from anywhere (portable)
REM - Ensures working directory = this BAT's folder
REM - Uses embedded python if present, else py launcher, else python
REM - If Python is missing, asks Y/N to install Python via winget
REM - Passes through command-line args (%*)
REM ============================================================

set "APP_ROOT=%~dp0"
cd /d "%APP_ROOT%" || goto :bad_cd

set "SCRIPT=%APP_ROOT%GoogleSheets_Menu.py"
set "PYTHON_WINGET_ID=Python.Python.3.13"

call :run_python_if_available %*
if not "%RC%"=="9009" goto :done

echo.
echo ============================================================
echo Python was not found
echo ============================================================
echo Expected one of:
echo   - "%APP_ROOT%python\python.exe"
echo   - py launcher
echo   - python on PATH
echo.
echo This app needs Python before GoogleSheets_Menu.py can run.
echo.

where winget >nul 2>nul
if errorlevel 1 (
  echo ❌ winget was not found.
  echo Install "App Installer" / Windows Package Manager first,
  echo or install Python manually from python.org.
  set "RC=9009"
  goto :done
)

echo ✅ winget found.
echo.
echo Install Python automatically now?
echo This will run:
echo   winget install -e --id %PYTHON_WINGET_ID%
echo.
set /p INSTALL_PYTHON=Type Y to install Python, or anything else to cancel: 

if /I not "%INSTALL_PYTHON%"=="Y" (
  echo.
  echo ❌ Python install cancelled.
  set "RC=9009"
  goto :done
)

echo.
echo 📦 Installing Python with winget...
echo.

winget install -e --id %PYTHON_WINGET_ID% --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo.
  echo ❌ Python install failed.
  echo Try manually:
  echo   winget install -e --id %PYTHON_WINGET_ID%
  set "RC=9009"
  goto :done
)

echo.
echo ✅ Python install command completed.
echo Trying to start the app again...
echo.

call :run_python_if_available %*
if not "%RC%"=="9009" goto :done

echo.
echo ⚠️ Python may have installed successfully, but this Command Prompt
echo may not see the new PATH yet.
echo.
echo Close this window and reopen Run_GoogleSheets.bat.
set "RC=9009"
goto :done


:run_python_if_available
REM --- Prefer embedded portable python if bundled ---
if exist "%APP_ROOT%python\python.exe" (
  "%APP_ROOT%python\python.exe" -u "%SCRIPT%" %*
  set "RC=%ERRORLEVEL%"
  exit /b
)

REM --- Try common user install path for Python 3.13 ---
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" (
  "%LocalAppData%\Programs\Python\Python313\python.exe" -u "%SCRIPT%" %*
  set "RC=%ERRORLEVEL%"
  exit /b
)

REM --- Try common machine install path for Python 3.13 ---
if exist "%ProgramFiles%\Python313\python.exe" (
  "%ProgramFiles%\Python313\python.exe" -u "%SCRIPT%" %*
  set "RC=%ERRORLEVEL%"
  exit /b
)

REM --- Prefer Windows Python launcher if available ---
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -u "%SCRIPT%" %*
  set "RC=%ERRORLEVEL%"
  exit /b
)

REM --- Fallback to python on PATH ---
where python >nul 2>nul
if not errorlevel 1 (
  python -u "%SCRIPT%" %*
  set "RC=%ERRORLEVEL%"
  exit /b
)

set "RC=9009"
exit /b


:bad_cd
echo.
echo ❌ Failed to change directory to "%APP_ROOT%"
set "RC=1"

:done
echo.
echo Exit code: %RC%
echo Press any key to close...
pause >nul
endlocal & exit /b %RC%