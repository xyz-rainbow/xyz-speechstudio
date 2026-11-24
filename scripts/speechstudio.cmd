@echo off
setlocal
set "ROOT=%~dp0.."
if exist "%ROOT%\.venvs\core\Scripts\python.exe" (
  "%ROOT%\.venvs\core\Scripts\python.exe" -m backend.cli.main %*
  exit /b %ERRORLEVEL%
)
if exist "N:\.venvs\core\Scripts\python.exe" (
  "N:\.venvs\core\Scripts\python.exe" -m backend.cli.main %*
  exit /b %ERRORLEVEL%
)
echo Speech Studio Python environment not found under "%ROOT%\.venvs\core". 1>&2
exit /b 1
