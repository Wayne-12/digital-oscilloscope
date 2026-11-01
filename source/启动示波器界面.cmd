@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
if exist ".venv-ui\Scripts\python.exe" (
    ".venv-ui\Scripts\python.exe" "PC\ui\launch_scope.py" --hardware --baud 921600 --port COM12 %*
) else (
    python "PC\ui\launch_scope.py" --hardware --baud 921600 --port COM12 %*
)
set "scope_exit=%errorlevel%"
popd
if not "%scope_exit%"=="0" pause
exit /b %scope_exit%
