REM Espejo pedagógico: ejecuta el mismo gate en Windows.
@echo off
setlocal
for %%I in ("%~dp0\..\..\..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
uv run --python 3.14.2 --project scopes\ada\backend --frozen python scripts\scopes\ada\backend\check.py %*
exit /b %ERRORLEVEL%
