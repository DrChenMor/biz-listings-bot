@echo off
rem Updates the two sites that only work from a home computer:
rem   1. commercialrealestate.com.au  -> "CRE listings" tab (no window)
rem   2. SEEK Business                -> "SEEK listings" tab (a browser window opens: let it run)
rem If another computer is updating the sheet, this waits its turn: try again later.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo This PC isn't set up yet: double-click "Set up this PC.bat" first.
  pause
  exit /b 1
)
echo == commercialrealestate.com.au
.venv\Scripts\python -m bizbot run --store sheet --source commercialrealestate --limit 150
echo.
echo == SEEK Business
.venv\Scripts\python -m bizbot seek --store sheet
echo.
echo Done. You can close this window.
pause
