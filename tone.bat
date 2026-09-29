@echo off
chcp 65001 >nul
set TONE_ROOT=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tone.ps1" %*
