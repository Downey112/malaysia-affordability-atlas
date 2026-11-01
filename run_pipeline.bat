@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo [1/5] Ingesting official DOSM datasets...
"%PYTHON%" scripts\01_ingest.py || exit /b 1

echo [2/5] Building SQL warehouse (staging, dimensions, facts, marts)...
"%PYTHON%" scripts\02_build_warehouse.py || exit /b 1

echo [3/5] Running shop-cluster bootstrap (1000 replicates)...
"%PYTHON%" scripts\03_bootstrap.py || exit /b 1

echo [4/5] Validating outputs...
"%PYTHON%" scripts\04_validate.py || exit /b 1

echo [5/5] Generating the Power BI project...
"%PYTHON%" scripts\05_build_report.py || exit /b 1

echo [COMPLETE] Tables ready in data\processed\ and the report in powerbi\
