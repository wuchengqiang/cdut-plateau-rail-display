@echo off
setlocal
cd /d "%~dp0"
"%~dp0runtime\青藏高原科考滑轨屏服务.exe" --no-browser
exit /b %errorlevel%
