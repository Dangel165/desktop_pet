@echo off
setlocal

cd /d "%~dp0"

set "SCRIPT=%~dp0desktop_pet.py"
set "PYTHON_CMD="

where py.exe >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py"
    goto :run
)

where python.exe >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :run
)

for %%P in (
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%LocalAppData%\Programs\Python\Python310\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "%ProgramFiles%\Python310\python.exe"
    "%ProgramFiles(x86)%\Python313\python.exe"
    "%ProgramFiles(x86)%\Python312\python.exe"
    "%ProgramFiles(x86)%\Python311\python.exe"
    "%ProgramFiles(x86)%\Python310\python.exe"
) do (
    if exist %%~P (
        set "PYTHON_CMD=%%~P"
        goto :run
    )
)

echo [Desktop Pet] Python was not found.
echo Install Python from https://www.python.org/downloads/
echo.
pause
exit /b 1

:run
echo [Desktop Pet] Using Python: %PYTHON_CMD%
%PYTHON_CMD% -c "import PyQt5" >nul 2>nul
if errorlevel 1 (
    echo [Desktop Pet] PyQt5 is not installed for this Python.
    echo.
    echo Try this command:
    echo %PYTHON_CMD% -m pip install PyQt5
    echo.
    pause
    exit /b 1
)

if exist "%~dp0pet_error.log" del "%~dp0pet_error.log"
start "Desktop Pet" %PYTHON_CMD% "%SCRIPT%"
exit /b 0
