@echo off
setlocal
cd /d "%~dp0"
set "APP_EXE="
for %%F in ("%~dp0runtime\*.exe") do if exist "%%~fF" set "APP_EXE=%%~fF"
if not defined APP_EXE exit /b 2
"%APP_EXE%" --no-browser
exit /b %errorlevel%
