@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Система сдачи работ
cd /d "%~dp0"

echo ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
echo           Система сдачи работ
echo ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
echo.

:: -------------------------------------------------------------------
:: 1. ПРОВЕРКА И УСТАНОВКА PYTHON 3.14.5
:: -------------------------------------------------------------------
echo [1/5] Проверка наличия Python...

python --version >nul 2>&1
if errorlevel 1 (
    echo Python не найден. Начинаю автоматическую установку Python 3.14.5...
    echo Скачивание Python 3.14.5...
    curl -o python_installer.exe https://www.python.org/ftp/python/3.14.5/python-3.14.5-amd64.exe
    echo Установка Python...
    start /wait python_installer.exe InstallAllUsers=1 PrependPath=1 Include_test=0 SimpleInstall=1
    del python_installer.exe
    echo Python 3.14.5 успешно установлен!
) else (
    echo Python уже установлен.
)

:: -------------------------------------------------------------------
:: 2. ПОИСК СВОБОДНОГО ПОРТА
:: -------------------------------------------------------------------
echo.
echo [2/5] Поиск свободного порта...

set PORT=5000
:findport
netstat -ano | findstr ":%PORT% " >nul
if not errorlevel 1 (
    set /a PORT+=1
    goto findport
)
echo Найден свободный порт: %PORT%

:: -------------------------------------------------------------------
:: 3. ПОДГОТОВКА ВИРТУАЛЬНОГО ОКРУЖЕНИЯ
:: -------------------------------------------------------------------
echo.
echo [3/5] Подготовка виртуального окружения...

if not exist "venv" (
    echo Создание виртуального окружения...
    python -m venv venv
) else (
    echo Виртуальное окружение уже существует.
)

call venv\Scripts\activate.bat

:: -------------------------------------------------------------------
:: 4. УСТАНОВКА ЗАВИСИМОСТЕЙ
:: -------------------------------------------------------------------
echo.
echo [4/5] Проверка и установка зависимостей...

if not exist "requirements.txt" (
    echo Создание requirements.txt...
    echo flask > requirements.txt
    echo markupsafe >> requirements.txt
)

python -m pip install --upgrade pip
pip install -r requirements.txt

:: -------------------------------------------------------------------
:: 5. ЗАПУСК СЕРВЕРА С ВЫБРАННЫМ ПОРТОМ
:: -------------------------------------------------------------------
echo.
echo [5/5] Запуск сервера на порту %PORT%...
echo.

start /b python app.py --port=%PORT%

timeout /t 3 /nobreak >nul

:: Получаем IP-адрес компьютера
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr "IPv4"') do (
    set IP=%%a
    set IP=!IP:~1!
)

echo.
echo ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
echo      СЕРВЕР ЗАПУЩЕН НА ПОРТУ %PORT%!
echo ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
echo.
echo Для этого компьютера:
echo   http://localhost:%PORT%
echo   http://127.0.0.1:%PORT%
echo.
echo Для других компьютеров в сети:
echo   http://!IP!:%PORT%
echo.
echo Открытие браузера...
start http://localhost:%PORT%

echo.
echo Чтобы остановить сервер, закрой это окно.
echo.
pause