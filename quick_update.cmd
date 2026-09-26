@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================
echo  HAVC Server DiT - Quick Update
echo ============================================
echo.
echo This script updates an existing installation to the latest version.
echo Prerequisites: .venv with CUDA 13.0 already created.
echo.

REM Step 1: Pull the latest code
echo [1/7] Pulling latest code...
call git pull
if errorlevel 1 (
    echo [ERROR] git pull failed. Make sure you are in the repository root and have internet access.
    pause
    exit /b 1
)
echo.

REM Step 2: Activate the virtual environment
echo [2/7] Activating virtual environment...
call .venv\Scripts\activate
if not defined VIRTUAL_ENV (
    echo [ERROR] Failed to activate virtual environment. Is .venv present?
    pause
    exit /b 1
)
echo Virtual environment active.
echo.

REM Step 3: Install / update GUI dependencies
echo [3/7] Installing/updating GUI dependencies...
if exist "GUI\requirements.txt" (
    pip install -r GUI\requirements.txt
    if errorlevel 1 (
        echo [WARNING] Some GUI packages could not be installed. You may need to update manually.
    )
) else (
    echo [INFO] GUI\requirements.txt not found. Skipping GUI dependencies.
)
echo.

REM Step 4: Pin comfy-kitchen / comfy-aimdo (required for qwen21-viggle)
echo [4/7] Pinning comfy-kitchen/comfy-aimdo to tested versions...
pip install comfy-kitchen==0.2.35
if errorlevel 1 (
    echo [WARNING] Failed to pin comfy-kitchen. qwen21-viggle may not work correctly.
)
pip install comfy-aimdo==0.5.5
if errorlevel 1 (
    echo [WARNING] Failed to pin comfy-aimdo. qwen21-viggle may not work correctly.
)
echo.

REM Step 5: Update vscmnet2
set VSCMNET2_FOUND=0
for %%f in (packages\vscmnet2*.whl) do (
    set VSCMNET2_FOUND=1
    echo [5/7] Updating vscmnet2 from %%~nxf...
    pip install "%%f"
    if errorlevel 1 (
        echo [WARNING] Failed to update vscmnet2.
    )
)
if !VSCMNET2_FOUND! equ 0 (
    echo [5/7] No vscmnet2 wheel found in packages/. Skipping.
)
echo.

REM Step 6: Re-apply the Nunchaku patch
echo [6/7] Re-applying Nunchaku patch...
if exist "patch_nunchaku.py" (
    python patch_nunchaku.py
    if errorlevel 1 (
        echo [WARNING] Nunchaku patch application failed. Check patch_nunchaku.py for errors.
    )
) else (
    echo [INFO] patch_nunchaku.py not found. Skipping patch.
)
echo.

REM Step 7: Verify installation
echo [7/7] Verifying installation...
echo.
echo --- PyTorch version ---
pip show torch
echo.
echo --- Nunchaku version ---
pip show nunchaku
echo.
echo --- comfy-kitchen version ---
pip show comfy-kitchen
echo.
echo --- comfy-aimdo version ---
pip show comfy-aimdo
echo.

echo ============================================
echo  Quick update complete!
echo ============================================
echo.
echo Expected versions:
echo   torch         : 2.10.0+cu130
echo   nunchaku      : 1.2.1+cu13.0torch2.10
echo   comfy-kitchen : 0.2.35
echo   comfy-aimdo   : 0.5.5
echo.
echo Notes:
echo   - Step 4 (comfy-kitchen/comfy-aimdo pin) is only required to use qwen21-viggle;
echo     the other three backends work with older versions of these two packages.
echo   - Steps 5-6 are only needed if packages/ or patch_nunchaku.py changed.
echo   - Run 'git log --oneline -5' to see what was updated in this pull.
echo.
pause
