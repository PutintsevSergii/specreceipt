@echo off
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\python.ps1" "%~dp0harness" %*
exit /b %errorlevel%
