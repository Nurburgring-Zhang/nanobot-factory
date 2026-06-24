@echo off
echo [INFO] Creating virtual environment...
python -m venv venv_aigc

echo [INFO] Activating virtual environment...
call "venv_aigc\Scripts\activate.bat"

echo [INFO] Installing dependencies...
pip install -r requirements_windows.txt

echo [INFO] Setup complete.
pause