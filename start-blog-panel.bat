@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

where python >nul 2>&1
if errorlevel 1 (
  echo Python не найден. Установите Python 3 и добавьте его в PATH.
  pause
  exit /b 1
)

echo Установка зависимостей панели блога...
python -m pip install -r "tools\blog_dashboard\requirements.txt" -q
if errorlevel 1 (
  echo Ошибка pip install.
  pause
  exit /b 1
)

echo.
echo Панель: http://127.0.0.1:8765
echo Закройте это окно, чтобы остановить сервер.
echo.

python "tools\blog_dashboard\server.py"
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" pause
exit /b %EC%
