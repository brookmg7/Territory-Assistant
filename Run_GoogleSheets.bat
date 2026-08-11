@echo off
setlocal EnableExtensions

REM ============================================================
REM Run_GoogleSheets.bat
REM Territory Assistant - Google Sheets Launcher
REM ============================================================
REM Simple launcher:
REM - Keeps the window open.
REM - Finds Python.
REM - Offers to install Python 3.13 if missing.
REM - Starts GoogleSheets_Menu.py.
REM - Main setup/logging is handled by GoogleSheets_Menu.py.
REM ============================================================

REM Keep the window open when double-clicked
if /I not "%TA_KEEP_OPEN%"=="1" (
    set "TA_KEEP_OPEN=1"
    start "Territory Assistant - Google Sheets" cmd /k ""%~f0" %*"
    exit /b
)

chcp 65001 >nul 2>nul

set "APP_ROOT=%~dp0"
set "SCRIPT=%APP_ROOT%GoogleSheets_Menu.py"
set "LOG_DIR=%APP_ROOT%Log"
set "SUPPORT_LOG=%LOG_DIR%\Run_GoogleSheets_support_log.txt"
set "PYTHON_WINGET_ID=Python.Python.3.13"
set "RC=0"

set "PY_FOUND=0"
set "PY_EXE="
set "PY_ARGS="
set "PY_LABEL="

if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%" >nul 2>nul
)

if not exist "%LOG_DIR%" (
    echo ERROR: Could not create Log folder.
    echo Try moving the folder somewhere simple, for example:
    echo Desktop\Territory-Assistant
    echo.
    echo Press any key to close...
    pause >nul
    endlocal & exit /b 1
)

> "%SUPPORT_LOG%" echo Territory Assistant - Google Sheets Support Log
>> "%SUPPORT_LOG%" echo Started: %DATE% %TIME%
>> "%SUPPORT_LOG%" echo APP_ROOT: %APP_ROOT%
>> "%SUPPORT_LOG%" echo SCRIPT: %SCRIPT%
>> "%SUPPORT_LOG%" echo.

set "GS_RUN_FROM_BAT=1"
set "GS_SUPPORT_LOG=%SUPPORT_LOG%"
set "GS_LOG_LEVEL=DEBUG"
set "GS_AUTOWRAP_FLOWS=1"
set "GS_LOG_APPEND=0"

echo.
echo ============================================================
echo Territory Assistant - Google Sheets Launcher
echo ============================================================
echo This window will stay open so errors are visible.
echo.
echo Support log:
echo   %SUPPORT_LOG%
echo ============================================================
echo.

cd /d "%APP_ROOT%" || goto :bad_cd

if not exist "%SCRIPT%" (
    echo ERROR: GoogleSheets_Menu.py was not found.
    echo.
    echo Expected:
    echo   "%SCRIPT%"
    echo.
    echo Make sure the ZIP file was extracted first.
    echo Do not run from inside the ZIP file.
    echo.
    set "RC=2"
    goto :done
)

call :find_python

if "%PY_FOUND%"=="1" (
    call :run_app %*

    REM Code 75 means Python installed packages and requested restart.
    if "%RC%"=="75" (
        echo.
        echo Packages were installed. Restarting the app...
        echo.
        call :run_app %*
    )

    goto :done
)

echo.
echo ============================================================
echo Python was not found
echo ============================================================
echo This app needs Python before it can run.
echo.
echo Recommended version:
echo   Python 3.13 64-bit
echo.
echo Simple manual install:
echo   https://www.python.org/downloads/windows/
echo.
echo During installation, tick:
echo   Add python.exe to PATH
echo.

where winget >nul 2>nul
if errorlevel 1 (
    echo winget was not found.
    echo.
    echo Please install Python 3.13 manually, restart the computer,
    echo then run this file again.
    echo.
    set "RC=9009"
    goto :done
)

echo winget was found.
echo.
echo Install Python 3.13 automatically now?
echo.
set /p INSTALL_PYTHON=Type Y to install Python, or anything else to cancel: 

if /I not "%INSTALL_PYTHON%"=="Y" (
    echo.
    echo Python install cancelled.
    set "RC=9009"
    goto :done
)

echo.
echo Installing Python 3.13 with winget...
echo Please wait.
echo.

winget install -e --id %PYTHON_WINGET_ID% --accept-package-agreements --accept-source-agreements
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo Python install failed.
    echo.
    echo Please install Python 3.13 manually from:
    echo https://www.python.org/downloads/windows/
    echo.
    set "RC=9009"
    goto :done
)

echo.
echo Python install command completed.
echo.

call :find_python

if "%PY_FOUND%"=="1" (
    call :run_app %*
    goto :done
)

echo Python may have installed, but this window cannot see it yet.
echo.
echo Please restart the computer and run this file again.
set "RC=9009"
goto :done


:find_python
set "PY_FOUND=0"
set "PY_EXE="
set "PY_ARGS="
set "PY_LABEL="

echo Looking for Python...

if exist "%APP_ROOT%python\python.exe" (
    set "PY_FOUND=1"
    set "PY_EXE=%APP_ROOT%python\python.exe"
    set "PY_ARGS="
    set "PY_LABEL=embedded portable Python"
    goto :find_python_done
)

if exist "%LocalAppData%\Programs\Python\Python313\python.exe" (
    set "PY_FOUND=1"
    set "PY_EXE=%LocalAppData%\Programs\Python\Python313\python.exe"
    set "PY_ARGS="
    set "PY_LABEL=user Python 3.13"
    goto :find_python_done
)

if exist "%ProgramFiles%\Python313\python.exe" (
    set "PY_FOUND=1"
    set "PY_EXE=%ProgramFiles%\Python313\python.exe"
    set "PY_ARGS="
    set "PY_LABEL=machine Python 3.13"
    goto :find_python_done
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3.13 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PY_FOUND=1"
        set "PY_EXE=py"
        set "PY_ARGS=-3.13"
        set "PY_LABEL=py launcher Python 3.13"
        goto :find_python_done
    )
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PY_FOUND=1"
        set "PY_EXE=py"
        set "PY_ARGS=-3"
        set "PY_LABEL=py launcher Python 3"
        goto :find_python_done
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PY_FOUND=1"
        set "PY_EXE=python"
        set "PY_ARGS="
        set "PY_LABEL=python on PATH"
        goto :find_python_done
    )
)

:find_python_done
if "%PY_FOUND%"=="1" (
    echo Using Python: %PY_LABEL%
    >> "%SUPPORT_LOG%" echo [%DATE% %TIME%] Using Python: %PY_LABEL%
    >> "%SUPPORT_LOG%" echo [%DATE% %TIME%] PY_EXE=%PY_EXE%
    >> "%SUPPORT_LOG%" echo [%DATE% %TIME%] PY_ARGS=%PY_ARGS%
) else (
    >> "%SUPPORT_LOG%" echo [%DATE% %TIME%] Python was not found.
)
exit /b


:run_app
echo.
echo Starting Territory Assistant...
echo.
>> "%SUPPORT_LOG%" echo [%DATE% %TIME%] Starting GoogleSheets_Menu.py
>> "%SUPPORT_LOG%" echo [%DATE% %TIME%] Command: %PY_EXE% %PY_ARGS% -u %SCRIPT% %*

"%PY_EXE%" %PY_ARGS% -u "%SCRIPT%" %*
set "RC=%ERRORLEVEL%"

>> "%SUPPORT_LOG%" echo [%DATE% %TIME%] GoogleSheets_Menu.py exited with code: %RC%
exit /b


:bad_cd
echo ERROR: Could not open the app folder:
echo   "%APP_ROOT%"
echo.
set "RC=1"
goto :done


:done
echo.
echo ============================================================
echo Finished
echo ============================================================
echo Exit code: %RC%
echo.
if "%RC%"=="0" (
    echo The app closed normally.
) else (
    echo Something stopped the app.
    echo.
    echo For support, send the whole Log folder.
    echo Important files:
    echo   Log\Run_GoogleSheets_support_log.txt
    echo   Log\GoogleSheets_All.txt
)
echo ============================================================
echo.
echo Press any key to close this window...
pause >nul

endlocal & exit /b %RC%