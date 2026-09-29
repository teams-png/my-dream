@echo off
echo ===================================================
echo  Multi-Business Accounting SaaS - First-time setup
echo ===================================================

where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Desktop kandilla. Install cheythu, open cheythu, veendum run cheyyuka.
    pause
    exit /b 1
)

echo.
echo [1/5] Postgres + Redis start cheyyunnu (docker compose)...
docker compose up -d

echo.
echo [2/5] Virtual environment undakkunnu...
python -m venv .venv

echo.
echo [3/5] Dependencies install cheyyunnu (oru 1-2 minute edukkum)...
call .venv\Scripts\activate.bat
pip install --upgrade pip >nul
pip install -r requirements\dev.txt

echo.
echo [4/5] Postgres start aakan 5 seconds wait cheyyunnu...
timeout /t 5 /nobreak >nul

echo.
echo [5/5] Migrations run cheyyunnu...
python manage.py migrate
python manage.py seed_platform

echo.
echo ===================================================
echo  Setup done! Superuser undakkan command:
echo    .venv\Scripts\activate ^&^& python manage.py createsuperuser
echo  Server start cheyyan: run.bat
echo ===================================================
pause
