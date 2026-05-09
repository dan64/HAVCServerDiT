@echo off
:: =============================================================================
:: run_client_example.cmd  —  DiT Colorize RPC Client example launcher (Windows)
::
:: Usage:
::   run_client_example.cmd          -> uses fp4 config (RTX 50-Series / Blackwell)
::   run_client_example.cmd int4     -> uses int4 config (RTX 30 / 40-Series)
::   run_client_example.cmd fp4      -> same as no argument
::
:: The client will:
::   1. Connect to the running dit_rpc_server instance
::   2. Load the pipeline if not already loaded on the server
::   3. Colorize assets\santa_bw.png
::   4. Save the result as assets\santa_colorized.png
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

:: Directory containing dit_client_example.py
:: Leave empty to use the directory of this script
set CLIENT_DIR=

:: Server host and port — must match the running dit_rpc_server instance
set HOST=127.0.0.1
set PORT=8765

:: Text prompt sent to the colorization model
set PROMPT=Colorize this photo, natural skin tones, vibrant environment. Maintain consistency and details.

:: Maximum long side in pixels before inference (0 = keep original size)
set IMG_SIZE=0

:: Number of inference steps
set STEPS=2

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

set CLIENT_SCRIPT=%CLIENT_DIR%\dit_client_example.py
set CONFIG_PATH=%CLIENT_DIR%\%CONFIG_FILE%

if not exist "%CLIENT_SCRIPT%" (
    echo [ERROR] dit_client_example.py not found in: %CLIENT_DIR%
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
:: BUILD COMMAND AND LAUNCH
:: ---------------------------------------------------------------------------
set CMD="%PYTHON_EXE%" "%CLIENT_SCRIPT%" ^
    --host %HOST% ^
    --port %PORT% ^
    --pipeline-config "%CONFIG_PATH%" ^
    --prompt "%PROMPT%" ^
    --img-size %IMG_SIZE% ^
    --steps %STEPS%

echo ============================================================
echo  DiT Colorize RPC Client example
echo  Precision   : %PRECISION%
echo  Config      : %CONFIG_PATH%
echo  Server      : %HOST%:%PORT%
echo  Input       : %CLIENT_DIR%\assets\santa_bw.png
echo  Output      : %CLIENT_DIR%\assets\santa_colorized.png
echo ============================================================
echo.

%CMD%

echo.
if %errorlevel%==0 (
    echo [DONE] Colorization complete.
) else (
    echo [ERROR] Client exited with code %errorlevel%.
)
pause
