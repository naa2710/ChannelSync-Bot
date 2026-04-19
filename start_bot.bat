@echo off
echo ===================================================
echo تنظيف النظام من أي عمليات عالقة للبوت...
echo ===================================================
taskkill /F /IM python.exe /T 2>nul
taskkill /F /IM python3.12.exe /T 2>nul
taskkill /F /IM py.exe /T 2>nul
echo.
echo ===================================================
echo جاري تشغيل البوت المزدوج الآن (Dashboard + UserBot)...
echo ===================================================
python run.py
pause
