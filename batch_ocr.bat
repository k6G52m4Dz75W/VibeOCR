@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "PYTHON_EXE=python"

if "%~1"=="" (
    echo Usage: %~nx0 dir_path [--model model_name]
    echo Example: %~nx0 D:\Documents --model mineru_precision
    pause
    exit /b 1
)

set "TARGET_DIR=%~1"
set "MODEL=mineru_precision"

if "%~2"=="--model" (
    if not "%~3"=="" (
        set "MODEL=%~3"
    )
)

echo ==========================================
echo VibeOCR Batch Processing
echo Target: %TARGET_DIR%
echo Model: %MODEL%
echo ==========================================
echo.

if not exist "%TARGET_DIR%" (
    echo Error: Directory not found - %TARGET_DIR%
    pause
    exit /b 1
)

set "FILE_COUNT=0"
for %%f in ("%TARGET_DIR%\*.pdf" "%TARGET_DIR%\*.jpg" "%TARGET_DIR%\*.jpeg" "%TARGET_DIR%\*.png" "%TARGET_DIR%\*.bmp" "%TARGET_DIR%\*.tiff" "%TARGET_DIR%\*.webp") do (
    set /a FILE_COUNT+=1
)

if %FILE_COUNT%==0 (
    echo No PDF or image files found.
    pause
    exit /b 0
)

echo Found %FILE_COUNT% file(s), starting...
echo.

set "CURRENT=0"
for %%f in ("%TARGET_DIR%\*.pdf" "%TARGET_DIR%\*.jpg" "%TARGET_DIR%\*.jpeg" "%TARGET_DIR%\*.png" "%TARGET_DIR%\*.bmp" "%TARGET_DIR%\*.tiff" "%TARGET_DIR%\*.webp") do (
    set /a CURRENT+=1
    echo [%CURRENT%/%FILE_COUNT%] Processing: %%~nxf
    "%PYTHON_EXE%" VibeOCR.py "%%f" --model %MODEL%
    if errorlevel 1 (
        echo     [WARN] Failed: %%~nxf
    ) else (
        echo     [OK] Done: %%~nxf
    )
    echo.
)

echo ==========================================
echo All done! Processed %FILE_COUNT% file(s).
echo ==========================================
pause
