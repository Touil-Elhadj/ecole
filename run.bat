@echo off
REM تشغيل البرنامج مباشرة من الكود (للتجربة دون بناء)
if not exist venv (
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)
python main.py
