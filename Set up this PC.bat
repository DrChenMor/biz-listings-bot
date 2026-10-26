@echo off
rem One-time setup on a Windows PC: installs what the bots need, then connects to the Google Sheet.
cd /d "%~dp0"
echo Setting up the business bots on this PC. This takes about 5 minutes.
echo.
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul || goto nopython

echo 1/4 Making a private Python environment...
%PY% -m venv .venv || goto failed
echo 2/4 Installing the bots' helpers...
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -r requirements-local.txt || goto failed
echo 3/4 Installing the browser the SEEK check uses...
.venv\Scripts\python -m playwright install chromium || goto failed
echo 4/4 Connecting to the Google Sheet...
echo.
.venv\Scripts\python -m bizbot setup || goto failed
echo.
echo All set. From now on, double-click "Check SEEK and CRE.bat" to update the sheet.
pause
exit /b 0

:nopython
echo Python 3.11 or newer isn't installed yet. Opening the download page for you.
echo Install it, tick "Add python.exe to PATH" on the first screen, then double-click this file again.
start "" https://www.python.org/downloads/
pause
exit /b 1

:failed
echo.
echo Setup stopped because of the error above. Send Chen a photo of this window.
pause
exit /b 1
