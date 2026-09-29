@echo off
docker compose up -d >nul 2>&1
call .venv\Scripts\activate.bat
echo Server: http://127.0.0.1:8000
echo Admin:  http://127.0.0.1:8000/admin
python manage.py runserver
