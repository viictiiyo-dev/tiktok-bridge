@echo off
REM TikTok Bridge :41243. Patron P10 (propio cd/env/redirect).
cd /d "C:\Users\victo\Desktop\TIKTOK\src"
powershell -NoProfile -Command "if ((Test-Path server-tiktok.log) -and ((Get-Item server-tiktok.log).Length -gt 5MB)) { Move-Item server-tiktok.log server-tiktok.log.1 -Force }"
"C:\Program Files\Python311\python.exe" server_v1.py <NUL >> server-tiktok.log 2>&1
