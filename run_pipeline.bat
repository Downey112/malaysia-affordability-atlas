@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo [1/4] Ingesting official DOSM datasets...
"%PYTHON%" scripts\01_ingest.py || exit /b 1

echo [2/4] Building SQL warehouse (staging, dimensions, facts, marts)...
"%PYTHON%" scripts\02_build_warehouse.py || exit /b 1

echo [3/4] Running shop-cluster bootstrap (1000 replicates)...
"%PYTHON%" scripts\03_bootstrap.py || exit /b 1

echo [4/4] Validating outputs...
"%PYTHON%" scripts\04_validate.py || exit /b 1

echo [COMPLETE] Malaysia Affordability Atlas tables ready in data\processed\
