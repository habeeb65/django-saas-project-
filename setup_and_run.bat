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

REM Activate virtual environment if it exists, or create a new one
if exist venv (
    echo Activating existing virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo Creating new virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create virtual environment
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
)

REM Verify virtual environment is activated
python -c "import sys; print(sys.prefix)" | findstr /i "venv" >nul
if errorlevel 1 (
    echo Virtual environment not properly activated
    pause
    exit /b 1
)

REM Upgrade pip, setuptools and wheel for better dependency resolution
echo Upgrading pip, setuptools, and wheel...
python -m pip install --upgrade pip setuptools wheel

REM Install visualization dependencies first to avoid conflicts
echo Installing visualization dependencies...
python -m pip install --upgrade numpy==1.26.4
python -m pip install --upgrade scipy==1.12.0
python -m pip install --upgrade matplotlib==3.8.2

REM Install data processing dependencies
echo Installing data dependencies...
python -m pip install --upgrade pandas==2.0.3
python -m pip install --upgrade scikit-learn==1.3.0
python -m pip install --upgrade xlsxwriter==3.1.9
python -m pip install --upgrade openpyxl==3.1.2

REM Install remaining dependencies
echo Installing all other dependencies...
python -m pip install -r requirements.txt --no-deps

REM Install core dependencies
echo Installing core dependencies...
python -m pip install Django==5.1.7
python -m pip install django-tenants==3.8.0
python -m pip install django-multitenant==2.3.0
python -m pip install django-bootstrap5==23.3
python -m pip install psycopg2-binary==2.9.10
python -m pip install pillow==10.0.0

REM Verify key installations
echo Verifying key package installations...
python -c "import matplotlib; print('Matplotlib installed successfully: version', matplotlib.__version__)"
python -c "import pandas; print('Pandas installed successfully: version', pandas.__version__)"
python -c "import django; print('Django installed successfully: version', django.__version__)"

REM Make migrations and migrate
echo Running migrations...
python manage.py makemigrations
if errorlevel 1 (
    echo Warning: makemigrations failed but continuing
)

python manage.py migrate
if errorlevel 1 (
    echo Migration failed
    echo.
    echo The project may need additional setup. Check database settings in settings.py
    echo You can still try to run the server to see if it works partially
    echo.
    pause
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