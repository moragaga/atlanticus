@echo off
setlocal
uv run --python 3.14.2 --no-python-downloads --no-project python "%~dp0process.py" %*
exit /b %ERRORLEVEL%
