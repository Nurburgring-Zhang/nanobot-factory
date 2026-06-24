@echo off
echo [INFO] Activating virtual environment...
call "venv_aigc\Scripts\activate.bat"

echo [INFO] Starting main application...
python main.py

echo [INFO] Program finished.
pause