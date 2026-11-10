# Instala supervision sin reiniciar servicios sanos. Ejecutar como administrador.
#requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$Runner = Join-Path $PSScriptRoot 'watch_birdmonitor.ps1'
$Launcher = Join-Path $PSScriptRoot 'run_powershell_hidden.vbs'
$TaskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$Action = New-ScheduledTaskAction -Execute 'wscript.exe' `
    -Argument "`"$Launcher`" `"$Runner`"" -WorkingDirectory $PSScriptRoot
# Sin RepetitionDuration: repeticion indefinida, sin despertar el ordenador.
$Periodic = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 1)
$Login = New-ScheduledTaskTrigger -AtLogOn -User $TaskUser
$Principal = New-ScheduledTaskPrincipal -UserId $TaskUser -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 55)
Register-ScheduledTask -TaskName 'BirdMonitor Recovery' -Action $Action `
    -Trigger @($Login, $Periodic) -Principal $Principal -Settings $Settings `
    -Description 'Comprueba y recupera BirdMonitor despues de reposo o fallos de arranque' -Force | Out-Null
Start-ScheduledTask -TaskName 'BirdMonitor Recovery'
Write-Host 'Recuperacion automatica instalada: comprobacion cada minuto, sin consolas.'
