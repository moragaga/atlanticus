@echo off
setlocal
uv run --no-project python "%~dp0check.py" %*
exit /b %ERRORLEVEL%
