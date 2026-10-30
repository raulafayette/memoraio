@echo off
powershell.exe -NoProfile -File "%~dp0Memoraio.ps1"
if errorlevel 1 pause
