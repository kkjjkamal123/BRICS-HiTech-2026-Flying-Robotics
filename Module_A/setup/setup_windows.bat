@echo off
REM ============================================================================
REM  BRICS Mission Studio - install the AI environment on Windows, OFFLINE.
REM  Uses offline\python_win\python-3.11.9-amd64.exe and offline\wheels_win\*.whl
REM  Double-click it (or the button in the app: Help -> Install AI environment).
REM ============================================================================
setlocal
cd /d "%~dp0\.."
set "ROOT=%cd%"
echo Toolkit: %ROOT%

if exist "%ROOT%\.venv_win\Scripts\python.exe" goto packages

if exist "%ROOT%\python_win\python.exe" goto makevenv
echo [1/3] Unpacking Python 3.11 (offline, no installer needed) ...
if exist "%ROOT%\python_tmp" rmdir /s /q "%ROOT%\python_tmp"
mkdir "%ROOT%\python_tmp"
REM  a) tar.exe is built into Windows 10 (1803+) and Windows 11
tar -xf "%ROOT%\offline\python_win\python.3.11.9.nupkg" -C "%ROOT%\python_tmp" >nul 2>nul
REM  b) PowerShell fallback
if not exist "%ROOT%\python_tmp\tools\python.exe" powershell -NoProfile -ExecutionPolicy Bypass -Command "Copy-Item -LiteralPath '%ROOT%\offline\python_win\python.3.11.9.nupkg' -Destination \"$env:TEMP\brics_py.zip\" -Force; Expand-Archive -LiteralPath \"$env:TEMP\brics_py.zip\" -DestinationPath '%ROOT%\python_tmp' -Force" >nul 2>nul
if exist "%ROOT%\python_tmp\tools\python.exe" move "%ROOT%\python_tmp\tools" "%ROOT%\python_win" >nul
if exist "%ROOT%\python_tmp" rmdir /s /q "%ROOT%\python_tmp"
if exist "%ROOT%\python_win\python.exe" goto makevenv
REM  c) last resort: official installer (per-user, silent)
echo     unpack failed - using the Python installer ...
"%ROOT%\offline\python_win\python-3.11.9-amd64.exe" /quiet InstallAllUsers=0 PrependPath=0 Include_test=0 Include_launcher=0 Shortcuts=0 AssociateFiles=0 TargetDir="%ROOT%\python_win"
if not exist "%ROOT%\python_win\python.exe" (
  echo ERROR: could not install Python. Run offline\python_win\python-3.11.9-amd64.exe yourself,
  echo        choose "Customize installation" and install to %ROOT%\python_win, then run this file again.
  pause
  exit /b 1
)

:makevenv
echo [2/3] Creating environment .venv_win ...
"%ROOT%\python_win\python.exe" -m venv "%ROOT%\.venv_win"

:packages
echo [3/3] Installing AI packages from offline\wheels_win (no internet needed, 3-6 min) ...
where nvidia-smi >nul 2>nul
if not errorlevel 1 if exist "%ROOT%\offline\wheels_win_cuda\torch-*.whl" (
  echo     NVIDIA GPU found - installing the GPU version of PyTorch (much faster training) ...
  "%ROOT%\.venv_win\Scripts\python.exe" -m pip install --no-index --find-links "%ROOT%\offline\wheels_win_cuda" --find-links "%ROOT%\offline\wheels_win" torch torchvision
)
"%ROOT%\.venv_win\Scripts\python.exe" -m pip install --no-index --find-links "%ROOT%\offline\wheels_win" -r "%ROOT%\setup\requirements_laptop.txt"
if not exist "%APPDATA%\Ultralytics" mkdir "%APPDATA%\Ultralytics"
copy /Y "%ROOT%\weights\Arial*.ttf" "%APPDATA%\Ultralytics\" >nul 2>nul
"%ROOT%\.venv_win\Scripts\python.exe" -c "import ultralytics, torch, cv2, onnxruntime, pptx, yaml; print('OK - ultralytics', ultralytics.__version__, '| torch', torch.__version__, '| GPU (CUDA):', torch.cuda.is_available())"
if errorlevel 1 (
  echo ERROR: something is missing - see messages above.
) else (
  echo.
  echo DONE. Start "BRICS Mission Studio.exe" in the toolkit folder.
)
pause
