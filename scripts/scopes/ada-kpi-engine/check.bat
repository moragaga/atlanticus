@echo off
setlocal
for %%I in ("%~dp0\..\..\..") do set "ROOT=%%~fI"
cd /d "%ROOT%\scopes\ada-kpi-engine"
uv run --python 3.14.2 --no-python-downloads python "%ROOT%\scripts\scopes\ada-kpi-engine\check.py" %*
exit /b %ERRORLEVEL%
