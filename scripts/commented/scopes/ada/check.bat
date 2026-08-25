@echo off
setlocal EnableExtensions

for %%I in ("%~dp0..\..\..") do set "ROOT=%%~fI"
set "APP=%ROOT%\scopes\ada\web\application\ada-generic-application"

cd /d "%APP%" || exit /b 1

echo [bootstrap] Synchronizing locked ADA Generic Application environment
uv sync --locked || exit /b 1
uv run --locked python "%ROOT%\scripts\scopes\ada\check.py" %* || exit /b 1

exit /b 0
