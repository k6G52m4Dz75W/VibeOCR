@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "PYTHON_EXE=python"
set "MODEL=mineru_precision"
set "SOURCE="

if "%~1"=="" (
    set "INPUT=%SOURCE%"
) else (
    set "INPUT=%~1"
)

if "%INPUT%"=="" (
    echo Usage: drag a folder or file onto %~nx0, or set SOURCE at top then double-click.
    echo Example: %~nx0 D:\Documents --model mineru_precision
    pause
    exit /b 1
)

if "%~2"=="--model" (
    if not "%~3"=="" (
        set "MODEL=%~3"
    )
)

echo ==========================================
echo VibeOCR Batch Processing
echo Input: %INPUT%
echo Model: %MODEL%
echo ==========================================
echo.

if not exist "%INPUT%" (
    echo Error: Not found - %INPUT%
    pause
    exit /b 1
)

set "IS_DIR=0"
if exist "%INPUT%\" set "IS_DIR=1"

if %IS_DIR%==1 (
    set "FILE_COUNT=0"
    for %%f in ("%INPUT%\*.pdf" "%INPUT%\*.jpg" "%INPUT%\*.jpeg" "%INPUT%\*.png" "%INPUT%\*.bmp" "%INPUT%\*.tiff" "%INPUT%\*.webp") do (
        set /a FILE_COUNT+=1
    )
    if !FILE_COUNT!==0 (
        echo No PDF or image files found in %INPUT%.
        pause
        exit /b 0
    )
    echo Found !FILE_COUNT! file(s), starting...
    echo.
    set "CURRENT=0"
    for %%f in ("%INPUT%\*.pdf" "%INPUT%\*.jpg" "%INPUT%\*.jpeg" "%INPUT%\*.png" "%INPUT%\*.bmp" "%INPUT%\*.tiff" "%INPUT%\*.webp") do (
        set /a CURRENT+=1
        echo [!CURRENT!/!FILE_COUNT!] Processing: %%~nxf
        "%PYTHON_EXE%" VibeOCR.py "%%f" --model %MODEL%
        if errorlevel 1 (
            echo     [WARN] Failed: %%~nxf
        ) else (
            echo     [OK] Done: %%~nxf
        )
        echo.
    )
) else (
    echo Processing single file: %INPUT%
    echo.
    "%PYTHON_EXE%" VibeOCR.py "%INPUT%" --model %MODEL%
    if errorlevel 1 (
        echo     [WARN] Failed: %INPUT%
    ) else (
        echo     [OK] Done: %INPUT%
    )
    echo.
)

echo ==========================================
echo All done!
echo ==========================================
pause
