@echo off
chcp 65001 >nul
REM بناء ملف البرنامج التنفيذي على Windows 10
REM يتطلب تثبيت Python 3.11 أو أحدث من python.org (مع خيار Add to PATH)

if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt

python -m pytest -q
if errorlevel 1 (
    echo Tests failed - build stopped
    pause
    exit /b 1
)

pyinstaller --noconfirm --clean --windowed --name Ecole main.py
echo.
echo Build done: dist\Ecole\Ecole.exe
pause
