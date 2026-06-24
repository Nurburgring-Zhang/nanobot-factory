@echo off
cd /d D:\minimax\nanobot-factory\nanobot-factory\backend
python -m py_compile server.py
echo server.py result: %errorlevel%
python -m py_compile airi_digital_human.py
echo airi_digital_human.py result: %errorlevel%
python -m py_compile diffuser_engine.py
echo diffuser_engine.py result: %errorlevel%
python -m py_compile omni_gen.py
echo omni_gen.py result: %errorlevel%
pause
