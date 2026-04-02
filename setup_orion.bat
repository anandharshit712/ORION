@echo off
echo ==========================================
echo ORION Setup Script
echo ==========================================

echo.
echo [1/4] Creating PostgreSQL user and database...
PGPASSWORD=postgres psql -U postgres -h localhost -c "CREATE USER \"Harshit\" WITH PASSWORD 'Harshit';" >> setup_log.txt 2>&1
PGPASSWORD=postgres psql -U postgres -h localhost -c "CREATE DATABASE orion OWNER \"Harshit\";" >> setup_log.txt 2>&1
PGPASSWORD=postgres psql -U postgres -h localhost -c "GRANT ALL PRIVILEGES ON DATABASE orion TO \"Harshit\";" >> setup_log.txt 2>&1
echo PostgreSQL step done. See setup_log.txt for details.

echo.
echo [2/4] Installing Python dependencies...
cd arep_implementation
pip install -e ".[api]" >> ..\setup_log.txt 2>&1
echo Python deps done.

echo.
echo [3/4] Installing npm dependencies...
cd ..\orion-frontend
npm install >> ..\setup_log.txt 2>&1
echo npm install done.

echo.
echo [4/4] Setup complete! 
echo.
echo To run the platform:
echo   Terminal 1 (API):      cd arep_implementation ^&^& uvicorn arep.api.app:app --reload
echo   Terminal 2 (Frontend): cd orion-frontend ^&^& npm run dev
echo.
echo Check setup_log.txt for detailed output.
pause
