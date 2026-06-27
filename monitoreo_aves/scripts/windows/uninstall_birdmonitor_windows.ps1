# BirdMonitor Windows Uninstaller
# Ejecutar como administrador

Write-Host ""
Write-Host "Eliminando tareas de BirdMonitor..." -ForegroundColor Cyan

Unregister-ScheduledTask -TaskName "BirdMonitor MediaMTX" -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "BirdMonitor Backend" -Confirm:$false -ErrorAction SilentlyContinue

Write-Host "Deteniendo MediaMTX..." -ForegroundColor Cyan
Get-Process mediamtx -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "Tareas eliminadas." -ForegroundColor Green
Write-Host ""
Write-Host "Nota: no se elimina el proyecto ni mediamtx.exe."