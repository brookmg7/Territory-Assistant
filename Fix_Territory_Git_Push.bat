@echo off
setlocal EnableExtensions

REM ============================================================
REM Territory Assistant Git Push Fix
REM Purpose:
REM - Keep local files safe
REM - Remove failed local commits containing >100MB files
REM - Add correct .gitignore
REM - Recommit without the blocked large files
REM - Push to GitHub
REM ============================================================

set "PROJECT_DIR=C:\Users\brook\OneDrive\Desktop\Territory Assistant"
set "REMOTE_URL=https://github.com/brookmg7/Territory-Assistant.git"
set "BRANCH=main"

echo ============================================================
echo Territory Assistant Git Push Fix
echo ============================================================
echo Project : %PROJECT_DIR%
echo Remote  : %REMOTE_URL%
echo Branch  : %BRANCH%
echo ============================================================
echo.
echo SAFETY:
echo - This does NOT delete your local files.
echo - This does NOT use force push.
echo - This resets local Git commits back to origin/main only.
echo - Your working files stay on disk.
echo.
pause

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    echo ERROR: Could not open project folder.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Checking Git repository
echo ============================================================

if not exist ".git" (
    echo Git repo missing. Initializing safely...
    git init
    if errorlevel 1 goto fail
)

git branch -M %BRANCH%

git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo Adding origin remote...
    git remote add origin "%REMOTE_URL%"
    if errorlevel 1 goto fail
) else (
    echo Setting origin remote...
    git remote set-url origin "%REMOTE_URL%"
    if errorlevel 1 goto fail
)

echo.
echo ============================================================
echo Fetching GitHub state
echo ============================================================

git fetch origin
if errorlevel 1 goto fail

echo.
echo ============================================================
echo Resetting local Git commit history to origin/main
echo ============================================================
echo This keeps your working files on disk.
echo.

git rev-parse --verify origin/%BRANCH% >nul 2>&1
if errorlevel 1 (
    echo origin/%BRANCH% not found. Skipping reset.
) else (
    git reset --mixed origin/%BRANCH%
    if errorlevel 1 goto fail
)

echo.
echo ============================================================
echo Writing .gitignore
echo ============================================================

(
echo # ============================================================
echo # FileSave Generator standard generated-output ignores
echo # ============================================================
echo .idea/
echo .vscode/.ropeproject/
echo __pycache__/
echo **/__pycache__/
echo *.pyc
echo *.pyo
echo .venv/
echo venv/
echo env/
echo build/
echo dist/
echo *.egg-info/
echo node_modules/
echo logs/
echo Logs/
echo **/logs/
echo **/Logs/
echo debug_logs/
echo **/debug_logs/
echo *.log
echo *_log.txt
echo *_Log.txt
echo Log_output*.txt
echo system_master.txt
echo QX-8 Engine_Output/
echo **/QX-8 Engine_Output/
echo bucket_*/
echo **/bucket_*/
echo runtime_output/
echo **/runtime_output/
echo Live_Reports/
echo **/Live_Reports/
echo historical_ohlc/
echo **/historical_ohlc/
echo historical_replay_*.csv
echo historical_replay_*.jsonl
echo historical_replay_*.log
echo historical_replay_config.generated.json
echo historical_replay_manifest.json
echo historical_replay_event_rows.jsonl
echo historical_replay_symbol_rows.jsonl
echo mode10_a_grade_history/
echo mode10_sequential_batches/
echo managed_components/
echo sdkconfig.old
echo build*/
echo.
echo # ============================================================
echo # Territory Assistant large local database files
echo # Keep these local only. GitHub normal Git limit is 100MB/file.
echo # ============================================================
echo Street Database/linz_auckland_addresses.csv
echo Street Database/linz_auckland.sqlite
echo.
echo # Temporary Office lock files
echo ~$*
echo ~$*.xlsx
echo *.tmp
echo *.temp
) > .gitignore

if errorlevel 1 goto fail

echo .gitignore written.

echo.
echo ============================================================
echo Confirming large files are ignored
echo ============================================================

git check-ignore -v "Street Database/linz_auckland_addresses.csv"
git check-ignore -v "Street Database/linz_auckland.sqlite"

echo.
echo ============================================================
echo Staging files
echo ============================================================

git add -A
if errorlevel 1 goto fail

echo.
echo ============================================================
echo Git status preview
echo ============================================================

git status --short

echo.
echo ============================================================
echo Creating commit
echo ============================================================

git commit -m "Territory Assistant baseline without large local database files"
if errorlevel 1 (
    echo.
    echo No new commit may have been needed, or commit failed.
    echo Continuing to push existing commits if any...
)

echo.
echo ============================================================
echo Pushing to GitHub
echo ============================================================

git push -u origin %BRANCH% --progress
if errorlevel 1 goto fail

echo.
echo ============================================================
echo SUCCESS
echo Territory Assistant pushed to GitHub.
echo Large local database files stayed on your computer only.
echo ============================================================
pause
exit /b 0

:fail
echo.
echo ============================================================
echo FAILED
echo Something stopped the Git fix.
echo Your local files were NOT deleted.
echo ============================================================
git status --short
pause
exit /b 1