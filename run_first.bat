@echo off
echo ===== StarMango Project Fix Script =====
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install critical missing dependencies
echo Installing missing dependencies...
python -m pip install django-filter==23.5
python -m pip install django-admin-tools==0.9.3
python -m pip install drf-yasg==1.21.7
python -m pip install djangorestframework-filters==1.0.0.dev0
python -m pip install django-debug-toolbar==4.3.0
python -m pip install django-extensions==3.2.3
python -m pip install channels==4.0.0
python -m pip install daphne==4.0.0
python -m pip install django-import-export==4.3.7
python -m pip install django-tenants==3.8.0
python -m pip install pip-review

REM Verify installations
echo.
echo Verifying installations...
python -c "import django_filters; print('django-filter installed successfully')"
python -c "import admin_tools; print('django-admin-tools installed successfully')"
python -c "import rest_framework; print('DRF installed successfully')"

echo.
echo ===== Installation Complete =====
echo.
echo Now run setup_and_run.bat to start your project
echo.
pause
