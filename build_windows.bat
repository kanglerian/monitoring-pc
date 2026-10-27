@echo off
echo === Mempersiapkan Build LabMonitoringAgent.exe ===
pip install pyinstaller psutil requests

echo === Mem-build file .exe ===
pyinstaller --onefile --noconsole --name LabMonitoringAgent agent.py

echo.
echo Selesai! File installer siap digunakan di: dist\LabMonitoringAgent.exe
pause
