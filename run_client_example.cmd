@echo off
:: =============================================================================
:: run_client_example.cmd   :   DiT Colorize RPC Client launcher (ComfyUI portable)
::
:: Connects to a running dit_rpc_server and colorizes assets\santa_bw.png.
:: The pipeline must already be loaded on the server.
::
:: Edit the USER CONFIGURATION block below before first use.
:: =============================================================================

:: ---------------------------------------------------------------------------
:: USER CONFIGURATION
:: ---------------------------------------------------------------------------

:: Path to python.exe
set PYTHON_EXE=%~dp0.venv\Scripts\python.exe

:: Directory containing dit_client_example.py
set CLIENT_DIR=

:: Server host and port
set HOST=127.0.0.1
set PORT=8765

:: Text prompt
set PROMPT=Colorize this photo, natural skin tones, vibrant environment. Maintain consistency and details.

:: Maximum long side (0 = keep original)
set IMG_SIZE=0

:: Inference steps (4 with LoRA, 20+ without)
set STEPS=2

:: Shared memory transport (same-host only)
set USE_SHM=1

:: ---------------------------------------------------------------------------
:: RESOLVE PATHS
:: ---------------------------------------------------------------------------
if "%CLIENT_DIR%"=="" set CLIENT_DIR=%~dp0
if "%CLIENT_DIR:~-1%"=="\" set CLIENT_DIR=%CLIENT_DIR:~0,-1%

set CLIENT_SCRIPT=%CLIENT_DIR%\dit_client_example.py

if not exist "%CLIENT_SCRIPT%" (
    echo [ERROR] dit_client_example.py not found in: %CLIENT_DIR%
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: LAUNCH
:: ---------------------------------------------------------------------------
echo ============================================================
echo  DiT Colorize RPC Client  :  example
echo  Server      : %HOST%:%PORT%
echo  Steps       : %STEPS%
echo  Input       : %CLIENT_DIR%\assets\santa_bw.png
echo  Output      : %CLIENT_DIR%\assets\santa_colorized.png
echo ============================================================
echo.

if "%USE_SHM%"=="1" (
    "%PYTHON_EXE%" "%CLIENT_SCRIPT%" --host %HOST% --port %PORT% --prompt "%PROMPT%" --img-size %IMG_SIZE% --steps %STEPS% --use-shm
) else (
    "%PYTHON_EXE%" "%CLIENT_SCRIPT%" --host %HOST% --port %PORT% --prompt "%PROMPT%" --img-size %IMG_SIZE% --steps %STEPS%
)

echo.
if %errorlevel%==0 (
    echo [DONE] Colorization complete.
) else (
    echo [ERROR] Client exited with code %errorlevel%.
)
pause
