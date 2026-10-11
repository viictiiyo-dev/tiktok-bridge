@echo off
REM MCP TikTok Bridge Streamable HTTP :41245. Patron P10.
cd /d "C:\Users\victo\Desktop\TIKTOK\src"
powershell -NoProfile -Command "if ((Test-Path mcp-tiktok.log) -and ((Get-Item mcp-tiktok.log).Length -gt 5MB)) { Move-Item mcp-tiktok.log mcp-tiktok.log.1 -Force }"
"C:\Program Files\Python311\python.exe" mcp_server.py --http --port 41245 <NUL >> mcp-tiktok.log 2>&1
