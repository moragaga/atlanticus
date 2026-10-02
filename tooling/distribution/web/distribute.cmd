@echo off
setlocal
uv run --python 3.14.2 --no-python-downloads --no-project --with packaging==25.0 python "%~dp0distribute.py" %*
exit /b %ERRORLEVEL%
