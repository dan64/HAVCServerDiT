@echo off
setlocal enabledelayedexpansion
REM Ensure we run from the repository root (all paths below are relative)
cd /d "%~dp0"

echo.
echo ============================================
echo  HAVC Server DiT - Quick Update
echo ============================================
echo.
echo This script updates an existing installation to the latest version.
echo Prerequisites: .venv with CUDA 13.0 already created.
echo.

REM Step 1: Pull the latest code
echo [1/6] Pulling latest code...
call git pull
if errorlevel 1 (
    echo [ERROR] git pull failed. Make sure you are in the repository root and have internet access.
    echo         If you have local changes or untracked files in the way, run 'git status' first and commit or stash them.
    pause
    exit /b 1
)
echo.

REM Step 2: Activate the virtual environment
echo [2/6] Activating virtual environment...
call .venv\Scripts\activate
if not defined VIRTUAL_ENV (
    echo [ERROR] Failed to activate virtual environment. Is .venv present?
    pause
    exit /b 1
)
echo Virtual environment active.
echo.

REM Step 3: Install / update GUI dependencies
echo [3/6] Installing/updating GUI dependencies...
if exist "GUI\requirements.txt" (
    python -m pip install -r GUI\requirements.txt
    if errorlevel 1 (
        echo [WARNING] Some GUI packages could not be installed. You may need to update manually.
    )
) else (
    echo [INFO] GUI\requirements.txt not found. Skipping GUI dependencies.
)
echo.

REM Step 4: Update vscmnet2
set VSCMNET2_FOUND=0
for %%f in (packages\vscmnet2*.whl) do (
    set VSCMNET2_FOUND=1
    echo [4/6] Updating vscmnet2 from %%~nxf...
    python -m pip install "%%f"
    if errorlevel 1 (
        echo [WARNING] Failed to update vscmnet2.
    )
)
if !VSCMNET2_FOUND! equ 0 (
    echo [4/6] No vscmnet2 wheel found in packages/. Skipping.
)
echo.

REM Step 5: Check and re-apply the Nunchaku patch (only if needed)
echo [5/6] Checking Nunchaku patch status...
if exist "patch_nunchaku.py" (
    python patch_nunchaku.py --check > "%TEMP%\nunchaku_patch_check.txt"
    type "%TEMP%\nunchaku_patch_check.txt" 2>nul
    findstr /c:"already patched" "%TEMP%\nunchaku_patch_check.txt" >nul
    if errorlevel 1 (
        echo.
        echo [INFO] Nunchaku patch not applied yet  :  applying...
        python patch_nunchaku.py
        if errorlevel 1 (
            echo [WARNING] Nunchaku patch application failed. Check patch_nunchaku.py for errors.
        )
    ) else (
        echo.
        echo [INFO] Nunchaku patch already applied  :  nothing to do.
    )
    del "%TEMP%\nunchaku_patch_check.txt" >nul 2>&1
) else (
    echo [INFO] patch_nunchaku.py not found. Skipping patch.
)
echo.

REM Step 6: Verify installation
echo [6/6] Verifying installation...
echo.
echo --- PyTorch version ---
python -m pip show torch
echo.
echo --- Nunchaku version ---
python -m pip show nunchaku
echo.

echo ============================================
echo  Quick update complete!
echo ============================================
echo.
echo Expected versions:
echo   torch      : 2.10.0+cu130
echo   nunchaku   : 1.2.1+cu13.0torch2.10
echo.
echo Notes:
echo   - Step 5 checks whether the Nunchaku patch is already applied before re-applying it.
echo   - Step 4 is only needed if packages/ changed.
echo   - Run 'git log --oneline -5' to see what was updated in this pull.
echo.
pause
