@echo off
:: =============================================================================
:: patch_nunchaku.cmd  —  Nunchaku compatibility patch launcher (Windows)
::
:: Usage:
::   patch_nunchaku.cmd              -> apply the patch
::   patch_nunchaku.cmd --check      -> check patch status without modifying files
::   patch_nunchaku.cmd --revert     -> revert to original using the .bak backup
::
:: Edit the USER CONFIGURATION block below before first use.
:: =============================================================================

:: ---------------------------------------------------------------------------
:: USER CONFIGURATION — adjust these variables to match your setup
:: ---------------------------------------------------------------------------

:: Conda environment name (used when PYTHON_EXE is not set)
set CONDA_ENV=dit-colorize

:: Explicit path to python.exe — leave empty to use the conda environment above
:: Example: set PYTHON_EXE=C:\Users\YourName\.conda\envs\dit-colorize\python.exe
set PYTHON_EXE=

:: Directory containing patch_nunchaku.py
:: Leave empty to use the directory of this script
set SCRIPT_DIR=

:: ---------------------------------------------------------------------------
:: ARGUMENT PASSTHROUGH
:: ---------------------------------------------------------------------------
set ACTION=%~1

:: ---------------------------------------------------------------------------
:: RESOLVE PATHS
:: ---------------------------------------------------------------------------
if "%SCRIPT_DIR%"=="" set SCRIPT_DIR=%~dp0
if "%SCRIPT_DIR:~-1%"=="\" set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

set PATCH_SCRIPT=%SCRIPT_DIR%\patch_nunchaku.py

if not exist "%PATCH_SCRIPT%" (
    echo [ERROR] patch_nunchaku.py not found in: %SCRIPT_DIR%
    echo         Set SCRIPT_DIR to the correct directory.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: RESOLVE PYTHON EXECUTABLE
:: ---------------------------------------------------------------------------
if not "%PYTHON_EXE%"=="" goto :run

where conda >nul 2>&1
if %errorlevel%==0 (
    echo [INFO] Activating conda environment: %CONDA_ENV%
    call conda activate %CONDA_ENV% 2>nul
    if %errorlevel%==0 (
        set PYTHON_EXE=python
        goto :run
    )
    echo [WARN] conda activate failed — trying base python
)

set PYTHON_EXE=python

:run
:: ---------------------------------------------------------------------------
:: RUN
:: ---------------------------------------------------------------------------
echo ============================================================
echo  Nunchaku Compatibility Patch
if "%ACTION%"=="--check"  echo  Mode: check status only
if "%ACTION%"=="--revert" echo  Mode: revert to original
if "%ACTION%"==""         echo  Mode: apply patch
echo ============================================================
echo.

"%PYTHON_EXE%" "%PATCH_SCRIPT%" %ACTION%

echo.
if %errorlevel%==0 (
    if "%ACTION%"==""         echo [DONE] Patch applied successfully.
    if "%ACTION%"=="--check"  echo [DONE] Check complete.
    if "%ACTION%"=="--revert" echo [DONE] Reverted successfully.
) else (
    echo [ERROR] Script exited with code %errorlevel%.
)
pause
