@echo off
setlocal

cd /d "%~dp0"
set "PYTHON_CMD="

where py.exe >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py"

if not defined PYTHON_CMD (
    where python.exe >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo [Build] Python was not found.
    echo Install Python only on the computer used for building.
    pause
    exit /b 1
)

echo [Build] Checking build tools...
%PYTHON_CMD% -c "import PyInstaller, PyQt5, pkg_resources" >nul 2>nul
if errorlevel 1 (
    echo [Build] Installing or repairing PyInstaller tools...
    %PYTHON_CMD% -m pip install --upgrade "setuptools<81" pyinstaller PyQt5
    if errorlevel 1 (
        echo [Build] Could not install build tools.
        pause
        exit /b 1
    )
)

echo [Build] Creating portable EXE...
%PYTHON_CMD% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name DesktopPet ^
    --distpath portable ^
    --workpath build\pyinstaller ^
    --specpath build ^
    desktop_pet.py

if errorlevel 1 (
    echo [Build] EXE build failed.
    pause
    exit /b 1
)

copy /y "run_portable.bat" "portable\run_portable.bat" >nul
if exist "README.md" copy /y "README.md" "portable\README.md" >nul

echo.
echo [Build] Done.
echo Copy the whole portable folder to another Windows computer.
echo Then double-click run_portable.bat.
pause
exit /b 0
