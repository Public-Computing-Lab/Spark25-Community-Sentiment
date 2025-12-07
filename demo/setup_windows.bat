@echo off

rem Change to project root (this file lives in demo/)
cd /d "%~dp0.."

rem Create Python virtual environment for the demo if it does not exist
if not exist .venv_demo (
  python -m venv .venv_demo
)

rem Select venv Python executable
set PYTHON=.venv_demo\Scripts\python.exe
if not exist "%PYTHON%" (
  set PYTHON=python
)

rem Install Python requirements
"%PYTHON%" -m pip install --upgrade pip
"%PYTHON%" -m pip install -r requirements.txt

rem Unzip the ChromaDB/vector store if the archive exists
if exist demo\vectordb_new.zip (
  powershell -Command "Expand-Archive -Path 'demo/vectordb_new.zip' -DestinationPath '.' -Force" 
)

rem Start MySQL demo database via Docker Compose
where docker-compose >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  docker-compose -f demo\docker-compose.demo.yml up -d
) else (
  docker compose -f demo\docker-compose.demo.yml up -d
)

rem Activate the demo virtual environment
if exist ".venv_demo\Scripts\activate.bat" (
  call ".venv_demo\Scripts\activate.bat"
)
