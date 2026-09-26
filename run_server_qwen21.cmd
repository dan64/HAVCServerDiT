@echo off
:: =============================================================================
:: run_server_qwen21.cmd   :   HAVC DiT Server launcher for qwen21-viggle
::
:: Usage:
::   run_server_qwen21.cmd    -> loads Qwen-Image-2.1 + Viggle-Turbo LoRA config
::
:: Single-config backend (config\qwen21_viggle.json) - no quant/precision
:: argument, unlike start_server.cmd.
::
:: Edit the USER CONFIGURATION block below before first use.
:: =============================================================================

:: ---------------------------------------------------------------------------
:: USER CONFIGURATION  :  adjust these variables to match your setup
:: ---------------------------------------------------------------------------

:: Conda environment name (used when PYTHON_EXE is not set)
set CONDA_ENV=dit-colorize

:: Explicit path to python.exe  :  leave empty to use the conda environment above
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
:: BACKEND / CONFIG  :  fixed, single config (no argument needed)
:: ---------------------------------------------------------------------------
set CONFIG_FILE=config\qwen21_viggle.json
set BACKEND=Qwen-Image-2.1 + Viggle-Turbo LoRA

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

:: 1) Local .venv alongside the script
if exist "%SERVER_DIR%\.venv\Scripts\python.exe" (
    set PYTHON_EXE=%SERVER_DIR%\.venv\Scripts\python.exe
    goto :run
)

:: 2) Try to activate conda environment
where conda >nul 2>&1
if %errorlevel%==0 (
    echo [INFO] Activating conda environment: %CONDA_ENV%
    call conda activate %CONDA_ENV% 2>nul
    if %errorlevel%==0 (
        set PYTHON_EXE=python
        goto :run
    )
    echo [WARN] conda activate failed  :  trying base python
)

:: 3) Fallback: use python from PATH
set PYTHON_EXE=python

:run
:: ---------------------------------------------------------------------------
:: Default log file if not specified by the user
:: ---------------------------------------------------------------------------
if "%LOGFILE%"=="" set LOGFILE=%SERVER_DIR%\dit_server.log

:: ---------------------------------------------------------------------------
:: BUILD COMMAND AND LAUNCH
:: ---------------------------------------------------------------------------
set CMD="%PYTHON_EXE%" "%SERVER_SCRIPT%"
set CMD=%CMD% --host %HOST%
set CMD=%CMD% --port %PORT%
set CMD=%CMD% --module-dir "%SERVER_DIR%"
set CMD=%CMD% --load-pipeline
set CMD=%CMD% --pipeline-config "%CONFIG_PATH%"
set CMD=%CMD% --logfile "%LOGFILE%"

echo ============================================================
echo  HAVC DiT Server
echo  Backend     : %BACKEND%
echo  Config      : %CONFIG_PATH%
echo  Listening on: %HOST%:%PORT%
echo  Log file    : %LOGFILE%
echo ============================================================
echo.

%CMD%

:: Keep the window open if the server exits with an error
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server exited with code %errorlevel%.
    pause
)
