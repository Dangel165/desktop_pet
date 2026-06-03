@echo off
setlocal

cd /d "%~dp0"

if exist "%~dp0DesktopPet.exe" (
    start "" "%~dp0DesktopPet.exe"
    exit /b 0
)

if exist "%~dp0portable\DesktopPet.exe" (
    start "" "%~dp0portable\DesktopPet.exe"
    exit /b 0
)

echo [Desktop Pet] DesktopPet.exe was not found.
echo Run build_portable.bat once on a computer with Python installed.
echo Then copy the whole portable folder to the other computer.
echo.
pause
exit /b 1
