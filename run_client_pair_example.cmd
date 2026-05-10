@echo off
:: =============================================================================
:: run_client_pair_example.cmd  —  DiT Colorize RPC paired inference launcher
::
:: Usage:
::   run_client_pair_example.cmd          -> fp4 config (RTX 50-Series / Blackwell)
::   run_client_pair_example.cmd int4     -> int4 config (RTX 30 / 40-Series)
::
:: Colorizes assets\sample1_bw.jpg and assets\sample2_bw.jpg in a single
:: inference pass and saves the results as:
::   assets\sample1_colorized.jpg
::   assets\sample2_colorized.jpg
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

:: Directory containing dit_client_pair_example.py
:: Leave empty to use the directory of this script
set CLIENT_DIR=

:: Server host and port — must match the running dit_rpc_server instance
set HOST=127.0.0.1
set PORT=8765

:: Text prompt sent to the colorization model
set PROMPT=Colorize this photo, natural skin tones, vibrant environment. Maintain consistency and details.

:: Separator width in pixels between the two images in the merged input
set GAP_PX=8

:: Use shared memory transport instead of PNG bytes (same-host only, lower latency)
:: Set to 1 to enable, 0 to use standard RPC
set USE_SHM=0

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
if "%CLIENT_DIR%"=="" set CLIENT_DIR=%~dp0
if "%CLIENT_DIR:~-1%"=="\" set CLIENT_DIR=%CLIENT_DIR:~0,-1%

set CLIENT_SCRIPT=%CLIENT_DIR%\dit_client_pair_example.py
set CONFIG_PATH=%CLIENT_DIR%\%CONFIG_FILE%

if not exist "%CLIENT_SCRIPT%" (
    echo [ERROR] dit_client_pair_example.py not found in: %CLIENT_DIR%
    echo         Set CLIENT_DIR to the correct directory.
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
:: LAUNCH
:: ---------------------------------------------------------------------------
echo ============================================================
echo  DiT Colorize RPC Client — paired inference example
echo  Precision   : %PRECISION%
echo  Config      : %CONFIG_PATH%
echo  Transport   : %USE_SHM% (0=RPC 1=shared memory)
echo  Server      : %HOST%:%PORT%
echo  Input 1     : %CLIENT_DIR%\assets\sample1_bw.jpg
echo  Input 2     : %CLIENT_DIR%\assets\sample2_bw.jpg
echo  Output 1    : %CLIENT_DIR%\assets\sample1_colorized.jpg
echo  Output 2    : %CLIENT_DIR%\assets\sample2_colorized.jpg
echo ============================================================
echo.

if "%USE_SHM%"=="1" (
    "%PYTHON_EXE%" "%CLIENT_SCRIPT%" --host %HOST% --port %PORT% --pipeline-config "%CONFIG_PATH%" --prompt "%PROMPT%" --gap-px %GAP_PX% --use-shm
) else (
    "%PYTHON_EXE%" "%CLIENT_SCRIPT%" --host %HOST% --port %PORT% --pipeline-config "%CONFIG_PATH%" --prompt "%PROMPT%" --gap-px %GAP_PX%
)

echo.
if %errorlevel%==0 (
    echo [DONE] Paired colorization complete.
) else (
    echo [ERROR] Client exited with code %errorlevel%.
)
pause
