@echo off
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%" || exit /b 1
set "SPEECH_PYTHON="
if exist "%ROOT%\runtime\envs\core\Scripts\python.exe" set "SPEECH_PYTHON=%ROOT%\runtime\envs\core\Scripts\python.exe"
if not defined SPEECH_PYTHON if exist "%ROOT%\.venvs\core\Scripts\python.exe" set "SPEECH_PYTHON=%ROOT%\.venvs\core\Scripts\python.exe"
if exist "%ROOT%\runtime\python\python.exe" set "SPEECH_PYTHON=%ROOT%\runtime\python\python.exe"
if not defined SPEECH_PYTHON goto missing
"%SPEECH_PYTHON%" -m backend.cli.main %*
set "SPEECH_EXIT=%ERRORLEVEL%"
popd
exit /b %SPEECH_EXIT%
:missing
echo Speech Studio Python environment not found under "%ROOT%\runtime\envs\core". 1>&2
popd
exit /b 1
