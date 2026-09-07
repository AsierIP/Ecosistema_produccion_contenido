@echo off
setlocal
if exist "%~dp0.runtime\dist\Upro\Upro.exe" (
    start "" "%~dp0.runtime\dist\Upro\Upro.exe" %*
    exit /b 0
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" /B pythonw.exe "%~dp0scripts\upro_launcher.py" --root "%~dp0." %*
    exit /b 0
)
echo No se encuentra el ejecutable Upro ni Python para Windows.
echo Instala Python 3.12 o posterior y sigue docs\UPRO-INICIO.md.
pause
exit /b 1
