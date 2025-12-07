@echo off
setlocal ENABLEDELAYEDEXPANSION

rem Change to project root (this file lives in demo/)
cd /d "%~dp0.."

rem Create Python virtual environment if it does not exist
if not exist .venv (
  where py >nul 2>&1
  if %ERRORLEVEL% EQU 0 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
)

rem Select venv Python executable
set PYTHON=.venv\Scripts\python.exe
if not exist "%PYTHON%" (
  set PYTHON=python
)

rem Install Python requirements
"%PYTHON%" -m pip install --upgrade pip
"%PYTHON%" -m pip install -r requirements.txt

if exist on_the_porch\requirements.txt (
  "%PYTHON%" -m pip install -r on_the_porch\requirements.txt
)

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

endlocal
