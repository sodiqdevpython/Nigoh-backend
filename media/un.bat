@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  Nigoh Agent - Uninstaller
::  Admin huquqi bilan ishga tushiring
:: ============================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [XATO] Iltimos, BAT faylni "Run as administrator" bilan ishga tushiring.
    pause
    exit /b 1
)

set SERVICE_NAME=WinSecHost
set INSTALL_DIR=C:\ProgramData\Nigoh

echo.
echo [1/3] Watchdog service to'xtatilmoqda va o'chirilmoqda...
sc query %SERVICE_NAME% >nul 2>&1
if %errorlevel% equ 0 (
    sc stop %SERVICE_NAME% >nul 2>&1
    timeout /t 3 /nobreak >nul
    sc delete %SERVICE_NAME% >nul 2>&1
    echo        Service o'chirildi.
) else (
    echo        Service topilmadi ^(allaqachon o'chirilgan bo'lishi mumkin^).
)

echo [2/3] Nigoh.exe jarayoni to'xtatilmoqda...
taskkill /f /im Nigoh.exe >nul 2>&1
taskkill /f /im WatchdogService.exe >nul 2>&1
timeout /t 1 /nobreak >nul
echo        Jarayonlar to'xtatildi.

echo [3/3] Fayllar o'chirilmoqda: %INSTALL_DIR%
if exist "%INSTALL_DIR%" (
    rd /s /q "%INSTALL_DIR%"
    echo        Fayllar o'chirildi.
) else (
    echo        Papka topilmadi ^(allaqachon o'chirilgan^).
)

echo.
echo ============================================================
echo  O'chirish muvaffaqiyatli tugadi!
echo ============================================================
echo.
pause
exit /b 0
