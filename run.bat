@echo off
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat
echo Installing/checking dependencies...
pip install -r requirements.txt --quiet
echo.
echo Starting EventHub...
python app.py
pause