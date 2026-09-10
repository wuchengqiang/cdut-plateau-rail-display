@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0runtime\slider-screen-service.exe" (
  echo Missing runtime\slider-screen-service.exe. Extract the complete app folder first.
  pause
  exit /b 2
)
"%~dp0runtime\slider-screen-service.exe" --standalone
set "APP_EXIT_CODE=%errorlevel%"
if not "%APP_EXIT_CODE%"=="0" pause
exit /b %APP_EXIT_CODE%
