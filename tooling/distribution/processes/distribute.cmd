@echo off
setlocal
uv run --no-project python "%~dp0distribute.py" %*
exit /b %ERRORLEVEL%
