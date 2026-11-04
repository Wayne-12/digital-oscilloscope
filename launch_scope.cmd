@echo off
setlocal
pushd "%~dp0"
set "scope_python=python"
if exist ".venv\Scripts\python.exe" set "scope_python=%~dp0.venv\Scripts\python.exe"
if exist "..\..\.venv-ui\Scripts\python.exe" set "scope_python=%~dp0..\..\.venv-ui\Scripts\python.exe"
"%scope_python%" "src\pc\ui\launch_scope.py" --hardware --baud 921600 --port COM12 %*
set "scope_exit=%errorlevel%"
popd
if not "%scope_exit%"=="0" pause
exit /b %scope_exit%
