@echo off
rem Wrapper fino para el gate comentado de deployment.
setlocal
set "ROOT=%~dp0\..\..\.."
uv run --python 3.14.2 --no-python-downloads --no-project --with ruff==0.15.22 --with pytest==9.1.1 python "%ROOT%\scripts\commented\deployment\check.py" %*
exit /b %errorlevel%
