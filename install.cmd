@echo off
:: =============================================================================
:: install.cmd : DiT Colorize RPC Server : environment installer (Windows)
::
:: Installs all required Python packages into the currently active virtual
:: environment (or the conda environment specified below).
::
:: Recommended usage:
::   1. Create and activate a venv first:
::        python -m venv .venv
::        .venv\Scripts\activate
::   2. Then run this script:
::        install.cmd
::
:: Edit the USER CONFIGURATION block below only if you are NOT using a venv
:: and want to target a specific conda environment instead.
:: =============================================================================

:: ---------------------------------------------------------------------------
:: USER CONFIGURATION : leave CONDA_ENV empty if you are using a plain venv
:: ---------------------------------------------------------------------------

:: Conda environment name : used only when PYTHON_EXE is not set and no venv
:: is active. Leave empty to rely on the currently active environment.
set CONDA_ENV=

:: Explicit path to python.exe : leave empty for auto-detection
:: Example: set PYTHON_EXE=C:\Users\YourName\.venv\Scripts\python.exe
set PYTHON_EXE=

:: Directory containing install.cmd, patch_nunchaku.py and the packages\ folder
:: Leave empty to use the directory of this script
set INSTALL_DIR=

:: ---------------------------------------------------------------------------
:: RESOLVE PATHS
:: ---------------------------------------------------------------------------
if "%INSTALL_DIR%"=="" set INSTALL_DIR=%~dp0
if "%INSTALL_DIR:~-1%"=="\" set INSTALL_DIR=%INSTALL_DIR:~0,-1%

set PATCH_SCRIPT=%INSTALL_DIR%\patch_nunchaku.py
set DIFFUSERS_WHEEL=%INSTALL_DIR%\packages\diffusers-0.37.0.dev0-py3-none-any.whl

if not exist "%PATCH_SCRIPT%" (
    echo [ERROR] patch_nunchaku.py not found in: %INSTALL_DIR%
    pause & exit /b 1
)
if not exist "%DIFFUSERS_WHEEL%" (
    echo [ERROR] diffusers wheel not found: %DIFFUSERS_WHEEL%
    pause & exit /b 1
)

:: ---------------------------------------------------------------------------
:: RESOLVE PYTHON EXECUTABLE
:: ---------------------------------------------------------------------------
if not "%PYTHON_EXE%"=="" goto :run

:: If a venv is active, use it directly
if defined VIRTUAL_ENV (
    set PYTHON_EXE=%VIRTUAL_ENV%\Scripts\python.exe
    goto :run
)

:: Try conda environment if specified
if not "%CONDA_ENV%"=="" (
    where conda >nul 2>&1
    if %errorlevel%==0 (
        echo [INFO] Activating conda environment: %CONDA_ENV%
        call conda activate %CONDA_ENV% 2>nul
        if %errorlevel%==0 (
            set PYTHON_EXE=python
            goto :run
        )
        echo [WARN] conda activate failed : falling back to base python
    )
)

set PYTHON_EXE=python

:run
:: ---------------------------------------------------------------------------
:: BANNER
:: ---------------------------------------------------------------------------
echo ============================================================
echo  DiT Colorize RPC Server : Environment Installer
echo  Python : %PYTHON_EXE%
echo  Dir    : %INSTALL_DIR%
echo ============================================================
echo.

:: ---------------------------------------------------------------------------
:: STEP 1 — PyTorch 2.10 + CUDA 13.0
:: ---------------------------------------------------------------------------
echo [1/6] Installing PyTorch 2.10 + CUDA 13.0 ...
"%PYTHON_EXE%" -m pip install ^
    torch==2.10.0+cu130 ^
    torchvision==0.25.0+cu130 ^
    torchaudio==2.10.0+cu130 ^
    --index-url https://download.pytorch.org/whl/cu130
if %errorlevel% neq 0 ( echo [ERROR] PyTorch install failed. & pause & exit /b 1 )
echo.

:: ---------------------------------------------------------------------------
:: STEP 2 — Nunchaku
:: ---------------------------------------------------------------------------
echo [2/6] Installing Nunchaku 1.2.1 ...
:: Nunchaku pulls torch>=2.0 via accelerate; the next step re-pins 2.10
"%PYTHON_EXE%" -m pip install ^
    https://github.com/nunchaku-ai/nunchaku/releases/download/v1.2.1/nunchaku-1.2.1+cu13.0torch2.10-cp312-cp312-win_amd64.whl
if %errorlevel% neq 0 ( echo [ERROR] Nunchaku install failed. & pause & exit /b 1 )
echo.

:: ---------------------------------------------------------------------------
:: STEP 2b — Re-pin PyTorch 2.10 (nunchaku may have upgraded it to 2.12)
:: ---------------------------------------------------------------------------
echo [2b/6] Re-pinning PyTorch 2.10 ...
"%PYTHON_EXE%" -m pip install ^
    torch==2.10.0+cu130 ^
    torchvision==0.25.0+cu130 ^
    torchaudio==2.10.0+cu130 ^
    --index-url https://download.pytorch.org/whl/cu130 ^
    --force-reinstall
if %errorlevel% neq 0 ( echo [ERROR] PyTorch re-pin failed. & pause & exit /b 1 )
echo.

:: ---------------------------------------------------------------------------
:: STEP 3 — Patch Nunchaku
:: ---------------------------------------------------------------------------
echo [3/6] Applying Nunchaku compatibility patch ...
"%PYTHON_EXE%" "%PATCH_SCRIPT%"
if %errorlevel% neq 0 ( echo [ERROR] Nunchaku patch failed. & pause & exit /b 1 )
echo.

:: ---------------------------------------------------------------------------
:: STEP 4 — Diffusers (local wheel)
:: ---------------------------------------------------------------------------
echo [4/6] Installing Diffusers 0.37.0.dev0 (local wheel) ...
"%PYTHON_EXE%" -m pip install "%DIFFUSERS_WHEEL%"
if %errorlevel% neq 0 ( echo [ERROR] Diffusers install failed. & pause & exit /b 1 )
echo.

:: ---------------------------------------------------------------------------
:: STEP 5 — Remaining dependencies
:: ---------------------------------------------------------------------------
echo [5/6] Installing remaining dependencies ...
"%PYTHON_EXE%" -m pip install ^
    transformers==4.57.6 ^
    accelerate==1.12.0 ^
    "huggingface_hub>=0.26.0" ^
    "Pillow>=10.0.0" ^
    scipy ^
    av ^
    torchsde ^
    gguf ^
    comfy-aimdo==0.4.7 ^
    comfy-kitchen
if %errorlevel% neq 0 ( echo [ERROR] Dependency install failed. & pause & exit /b 1 )
echo.

:: ---------------------------------------------------------------------------
:: DONE
:: ---------------------------------------------------------------------------
echo ============================================================
echo  Installation complete.
echo  Activate the environment and start the server with:
echo    start_server.cmd
echo ============================================================
pause