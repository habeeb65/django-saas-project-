@echo off
echo ===== StarMango Setup and Run Script =====
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Remove old venv and create fresh
if exist venv (
    echo Removing old virtual environment...
    rmdir /s /q venv
)

echo Creating new virtual environment...
python -m venv venv
if errorlevel 1 (
    echo Failed to create virtual environment
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

REM Verify virtual environment is activated
python -c "import sys; print(sys.prefix)" | findstr /i "venv" >nul
if errorlevel 1 (
    echo Virtual environment not properly activated
    pause
    exit /b 1
)

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install all dependencies
echo Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies
    pause
    exit /b 1
)

REM Verify key installations
echo.
echo Verifying key package installations...
python -c "import django; print('Django:', django.__version__)"
python -c "import import_export; print('django-import-export: OK')"
python -c "import diff_match_patch; print('diff-match-patch: OK')"

REM Make migrations and migrate
echo.
echo Running migrations...
python manage.py makemigrations
python manage.py migrate
if errorlevel 1 (
    echo Migration failed - check database settings
    pause
    exit /b 1
)

REM Create a superuser if needed
echo.
echo Would you like to create a superuser? (Y/N)
set /p create_admin=
if /i "%create_admin%"=="Y" (
    python manage.py createsuperuser
)

REM Start server
echo.
echo ===== Setup Complete =====
echo.
echo Starting Django server...
python manage.py runserver

pause