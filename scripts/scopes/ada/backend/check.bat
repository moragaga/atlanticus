@echo off
setlocal
for %%I in ("%~dp0\..\..\..\..") do set "ROOT=%%~fI"
cd /d "%ROOT%\scopes\ada\backend"
uv run --python 3.14.2 --no-python-downloads python "%ROOT%\scripts\scopes\ada\backend\check.py" %*
exit /b %ERRORLEVEL%
