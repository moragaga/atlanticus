@echo off
setlocal
cd /d "%~dp0"
uv run --python 3.14.2 --no-python-downloads --no-sync python "%~dp0check.py" %*
exit /b %ERRORLEVEL%
