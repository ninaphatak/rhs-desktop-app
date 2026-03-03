@echo off
REM RHS Monitor — Windows setup script
REM Creates (or updates) the rhs-app conda environment from environment.yml

cd /d "%~dp0"

set ENV_NAME=rhs-app
set ENV_FILE=environment.yml
set HASH_FILE=.env_hash

echo === RHS Monitor Setup ===

REM Check conda is available
where conda >nul 2>nul
if errorlevel 1 (
    echo ERROR: conda not found. Install Miniconda or Anaconda first.
    echo   https://docs.anaconda.com/miniconda/
    pause
    exit /b 1
)

REM Check if env exists
conda env list | findstr /b "%ENV_NAME% " >nul 2>nul
if errorlevel 1 (
    echo Creating '%ENV_NAME%' environment...
    conda env create -f %ENV_FILE%
) else (
    echo Updating existing '%ENV_NAME%' environment...
    conda env update -n %ENV_NAME% -f %ENV_FILE% --prune
)

REM Write hash
certutil -hashfile %ENV_FILE% SHA256 | findstr /v ":" > %HASH_FILE%

echo.
echo Setup complete. Run the app with:
echo   run.bat
pause
