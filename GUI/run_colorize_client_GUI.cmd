@echo off
D:
cd \PProjects\DiTServerRPC\GUI

set PYTHON="D:\PProjects\DiTServerGUI\.venv\scripts\python.exe"
set CLIENT=CMNET2_colorize_client_GUI.py

echo ============================================
echo  HAVC Colorize Launcher
echo  Dir: %CD%
echo ============================================

if not exist "%CLIENT%" (
    echo [ERRORE] File %CLIENT% non trovato in %CD%
    pause
    exit /b 1
)

:: --- Verifica Python ---
if not exist %PYTHON% (
    echo [ERRORE] Python non trovato: %PYTHON%
    pause
    exit /b 1
)

echo Avvio CMNET2 Colorize Client GUI...
%PYTHON% "%CLIENT%"

