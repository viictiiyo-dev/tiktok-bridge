# Cuadro de interacciones TIKTOK BRIDGE. Una vez:
# powershell -ExecutionPolicy Bypass -File "C:\Users\victo\Desktop\TIKTOK\ver_interacciones.ps1"
# En vivo (se refresca cada 5 s, Ctrl+C para salir):
# powershell -ExecutionPolicy Bypass -File "C:\Users\victo\Desktop\TIKTOK\ver_interacciones.ps1" -Live
param([switch]$Live)
$base = 'C:\Users\victo\Desktop\TIKTOK'
if ($Live) {
  while ($true) {
    Clear-Host
    & $MyInvocation.MyCommand.Path
    Write-Output ''
    Write-Output ('Actualizado: {0} (Ctrl+C para salir)' -f (Get-Date -Format 'HH:mm:ss'))
    Start-Sleep -Seconds 5
  }
  exit
}
Write-Output '=== TIKTOK BRIDGE: interacciones ==='
try {
  $h = Invoke-RestMethod 'http://127.0.0.1:41243/health' -TimeoutSec 8
  Write-Output ("Servicio: {0} v{1}" -f $h.status, $h.version)
} catch { Write-Output 'Servicio: CAIDO (puerto 41243 sin respuesta)' }
try {
  $env_lines = Get-Content "$base\.env" | Where-Object { $_ -match '^STATS_TOKEN=' }
  $tok = ($env_lines -replace '^STATS_TOKEN=', '').Trim()
  $s = Invoke-RestMethod 'http://127.0.0.1:41243/stats' -Headers @{'x-stats-token' = $tok} -TimeoutSec 8
  Write-Output ('Ventas: {0} | USDC cobrado: {1}' -f $s.ventas, $s.usdc_cobrado)
} catch { Write-Output 'Stats: no disponible (revisa STATS_TOKEN en .env)' }
Write-Output ''
Write-Output '--- Ultimas ventas x402 ---'
$w = "$base\src\ventas_tiktok.jsonl"
if (Test-Path $w) { Get-Content $w -Tail 5 | ForEach-Object { $j = $_ | ConvertFrom-Json; Write-Output ('{0} | {1} {2} | {3} USDC | tx {4}' -f ([datetime]'1970-01-01').AddSeconds($j.ts).ToString('dd HH:mm'), $j.kind, $j.network, ([int]$j.amount / 1e6), ($j.tx.Substring(0, [Math]::Min(12, $j.tx.Length)) + '...')) } }
else { Write-Output '(aun no hay ventas)' }
Write-Output ''
Write-Output '--- Coste Apify por llamada (margen vs $0.08) ---'
$c = "$base\src\coste_tiktok.jsonl"
if (Test-Path $c) { Get-Content $c -Tail 5 | ForEach-Object { $j = $_ | ConvertFrom-Json; Write-Output ('{0} | {1} | items {2} | ok {3} | ~${4}' -f ([datetime]'1970-01-01').AddSeconds($j.ts).ToString('dd HH:mm'), $j.actor, $j.items, $j.ok, $j.cost_est_usd) } }
else { Write-Output '(sin llamadas a Apify aun)' }
Write-Output ''
Write-Output '--- Ultimas peticiones HTTP ---'
$l = "$base\src\server-tiktok.log"
if (Test-Path $l) { Get-Content $l -Tail 8 | Where-Object { $_ -match 'GET|POST' } | Select-Object -Last 5 | ForEach-Object { Write-Output $_.Substring(0, [Math]::Min(160, $_.Length)) } }
else { Write-Output '(log aun no existe: arranca con arrancar_tiktok.bat para log a archivo)' }
Write-Output ''
Write-Output '--- 402 publico ---'
try {
  $b = Invoke-WebRequest 'https://veredicto.dpdns.org/v1/tiktok/search' -Method POST -Body '{"q":"paella"}' -ContentType 'application/json' -TimeoutSec 15 -UseBasicParsing
  Write-Output ("internet: HTTP {0}" -f [int]$b.StatusCode)
} catch {
  $code = $_.Exception.Response.StatusCode.value__
  if ($code -eq 402) { Write-Output 'internet: HTTP 402 (402 con payTo = puente vivo)' }
  else { Write-Output ('internet: sin respuesta (revisa Caddy/DDNS): {0}' -f $_.Exception.Message) }
}
Write-Output ''
Write-Output '--- Procesos ---'
Get-NetTCPConnection -LocalPort 41243, 41245, 443 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Output ("puerto {0} <- PID {1}" -f $_.LocalPort, $_.OwningProcess) }
