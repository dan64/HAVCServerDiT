@echo off
:: =============================================================================
:: run_client_pair_example.cmd   :   DiT Colorize RPC paired inference launcher
::
:: Colorizes assets\sample1_bw.jpg and assets\sample2_bw.jpg in a single
:: inference pass (faster, temporally consistent).
::
:: Edit the USER CONFIGURATION block below before first use.
:: =============================================================================

:: ---------------------------------------------------------------------------
:: USER CONFIGURATION
:: ---------------------------------------------------------------------------

:: Path to python.exe
set PYTHON_EXE=%~dp0.venv\Scripts\python.exe

:: Directory containing dit_client_pair_example.py
set CLIENT_DIR=

:: Server host and port
set HOST=127.0.0.1
set PORT=8765

:: Text prompt
set PROMPT=Colorize this photo, natural skin tones, vibrant environment. Maintain consistency and details.

:: Separator width in pixels between the two images in the merged input
set GAP_PX=8

:: Shared memory transport (same-host only)
set USE_SHM=1

:: ---------------------------------------------------------------------------
:: RESOLVE PATHS
:: ---------------------------------------------------------------------------
if "%CLIENT_DIR%"=="" set CLIENT_DIR=%~dp0
if "%CLIENT_DIR:~-1%"=="\" set CLIENT_DIR=%CLIENT_DIR:~0,-1%

set CLIENT_SCRIPT=%CLIENT_DIR%\dit_client_pair_example.py

if not exist "%CLIENT_SCRIPT%" (
    echo [ERROR] dit_client_pair_example.py not found in: %CLIENT_DIR%
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: LAUNCH
:: ---------------------------------------------------------------------------
echo ============================================================
echo  DiT Colorize RPC Client  :  paired inference
echo  Server      : %HOST%:%PORT%
echo  Input 1     : %CLIENT_DIR%\assets\sample1_bw.jpg
echo  Input 2     : %CLIENT_DIR%\assets\sample2_bw.jpg
echo  Output 1    : %CLIENT_DIR%\assets\sample1_colorized.jpg
echo  Output 2    : %CLIENT_DIR%\assets\sample2_colorized.jpg
echo ============================================================
echo.

if "%USE_SHM%"=="1" (
    "%PYTHON_EXE%" "%CLIENT_SCRIPT%" --host %HOST% --port %PORT% --prompt "%PROMPT%" --gap-px %GAP_PX% --use-shm
) else (
    "%PYTHON_EXE%" "%CLIENT_SCRIPT%" --host %HOST% --port %PORT% --prompt "%PROMPT%" --gap-px %GAP_PX%
)

echo.
if %errorlevel%==0 (
    echo [DONE] Paired colorization complete.
) else (
    echo [ERROR] Client exited with code %errorlevel%.
)
pause
