@echo off
:: =============================================================================
:: start_server.cmd  —  DiT Colorize RPC Server launcher (Windows)
::
:: Usage:
::   start_server.cmd          -> loads fp4 config  (RTX 50-Series / Blackwell)
::   start_server.cmd int4     -> loads int4 config (RTX 30 / 40-Series)
::   start_server.cmd fp4      -> same as no argument
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

:: Directory containing dit_rpc_server.py and dit_colorize_main.py
:: Leave empty to use the directory of this script
set SERVER_DIR=

:: Host and port
set HOST=127.0.0.1
set PORT=8765

:: Optional log file path (leave empty to log to console only)
:: Example: set LOGFILE=C:\Logs\dit_server.log
set LOGFILE=

:: ---------------------------------------------------------------------------
:: ARGUMENT PARSING — selects fp4 or int4 config
:: ---------------------------------------------------------------------------
set PRECISION=%~1
if /i "%PRECISION%"=="" set PRECISION=fp4
if /i "%PRECISION%"=="fp4"  set CONFIG_FILE=qwen_config_fp4.json
if /i "%PRECISION%"=="int4" set CONFIG_FILE=qwen_config_int4.json

if "%CONFIG_FILE%"=="" (
    echo [ERROR] Unknown precision argument: "%PRECISION%". Use "fp4" or "int4".
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: RESOLVE PATHS
:: ---------------------------------------------------------------------------
if "%SERVER_DIR%"=="" set SERVER_DIR=%~dp0
:: Remove trailing backslash if present
if "%SERVER_DIR:~-1%"=="\" set SERVER_DIR=%SERVER_DIR:~0,-1%

set SERVER_SCRIPT=%SERVER_DIR%\dit_rpc_server.py
set CONFIG_PATH=%SERVER_DIR%\%CONFIG_FILE%

if not exist "%SERVER_SCRIPT%" (
    echo [ERROR] dit_rpc_server.py not found in: %SERVER_DIR%
    echo         Set SERVER_DIR to the correct directory.
    pause
    exit /b 1
)

if not exist "%CONFIG_PATH%" (
    echo [ERROR] Config file not found: %CONFIG_PATH%
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: RESOLVE PYTHON EXECUTABLE
:: ---------------------------------------------------------------------------
if not "%PYTHON_EXE%"=="" goto :run

:: Try to activate conda environment
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

:: Fallback: use python from PATH
set PYTHON_EXE=python

:run
:: ---------------------------------------------------------------------------
:: BUILD COMMAND AND LAUNCH
:: ---------------------------------------------------------------------------
set CMD="%PYTHON_EXE%" "%SERVER_SCRIPT%" ^
    --host %HOST% ^
    --port %PORT% ^
    --module-dir "%SERVER_DIR%" ^
    --load-pipeline ^
    --pipeline-config "%CONFIG_PATH%"

if not "%LOGFILE%"=="" set CMD=%CMD% --logfile "%LOGFILE%"

echo ============================================================
echo  DiT Colorize RPC Server
echo  Precision   : %PRECISION%
echo  Config      : %CONFIG_PATH%
echo  Listening on: %HOST%:%PORT%
if not "%LOGFILE%"=="" echo  Log file    : %LOGFILE%
echo ============================================================
echo.

%CMD%

:: Keep the window open if the server exits with an error
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server exited with code %errorlevel%.
    pause
)
