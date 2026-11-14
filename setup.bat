@echo off
cd /d "%~dp0"
where py >nul 2>nul || (echo Python launcher "py" not found. Install Python from python.org & pause & exit /b 1)
where npm >nul 2>nul || (echo Node.js not found. Install it from nodejs.org & pause & exit /b 1)
if not exist venv\Scripts\activate.bat py -m venv venv
call venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
if not exist node_modules call npm install
call npm start
