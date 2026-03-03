@echo off
REM RHS Monitor — Windows launch script
REM Activates the rhs-app conda environment and launches the app.

cd /d "%~dp0"

set ENV_NAME=rhs-app
set ENV_FILE=environment.yml
set HASH_FILE=.env_hash

REM Check if env exists
conda env list | findstr /b "%ENV_NAME% " >nul 2>nul
if errorlevel 1 (
    echo ERROR: '%ENV_NAME%' environment not found. Run setup.bat first.
    pause
    exit /b 1
)

REM Check if environment.yml has changed
if exist %HASH_FILE% (
    certutil -hashfile %ENV_FILE% SHA256 | findstr /v ":" > %HASH_FILE%.tmp
    fc /b %HASH_FILE% %HASH_FILE%.tmp >nul 2>nul
    if errorlevel 1 (
        del %HASH_FILE%.tmp
        echo Dependencies changed. Re-run setup.bat first.
        pause
        exit /b 1
    )
    del %HASH_FILE%.tmp
)

echo Launching RHS Monitor...
call conda activate %ENV_NAME%
python -m src.main %*
pause
