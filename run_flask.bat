@echo off
cd /d "C:\Cursor Project\TPS Link to Image Converter FB"

echo Activating virtualenv...
call ".venv\Scripts\activate.bat"

echo Starting Flask on http://127.0.0.1:5000 ...
python "fb-link-generator\app.py"

echo.
echo Flask stopped. Press any key to close this window.
pause >nul


