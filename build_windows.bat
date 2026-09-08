@echo off
setlocal
cd /d %~dp0

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python launcher not found. This script is for developers/build machines only.
  exit /b 1
)

if not exist .venv (
  py -3.12 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-build.txt
pytest -q
if errorlevel 1 exit /b 1
pyinstaller --noconfirm --clean XiaozhiDesktopAssistant.spec
if errorlevel 1 exit /b 1

echo.
echo Portable EXE created: dist\XiaozhiDesktopAssistant.exe
where ISCC >nul 2>nul
if not errorlevel 1 (
  ISCC installer\XiaozhiAssistant.iss
  echo Installer created under dist\installer
) else (
  echo Inno Setup not found; skipped installer build.
)
endlocal
