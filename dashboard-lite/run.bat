@echo off
setlocal
cd /d "%~dp0"
echo.
echo  Regime Engine dashboard  ^|  http://127.0.0.1:8765/
echo  MT5 API ^(from parent folder^): python ..\dashboard_api\server.py -^> http://127.0.0.1:8766/
echo  Press Ctrl+C to stop.
echo.
python -m http.server 8765
