Option Explicit

Dim arguments
Set arguments = WScript.Arguments

If arguments.Count = 1 Then
    If LCase(arguments(0)) = "--check" Then
        WScript.Echo "BirdMonitor hidden launcher: OK"
        WScript.Quit 0
    End If
End If

If arguments.Count <> 1 Then
    WScript.Quit 2
End If

Dim fileSystem, scriptPath
Set fileSystem = CreateObject("Scripting.FileSystemObject")
scriptPath = fileSystem.GetAbsolutePathName(arguments(0))

If Not fileSystem.FileExists(scriptPath) Then
    WScript.Quit 3
End If
If LCase(fileSystem.GetExtensionName(scriptPath)) <> "ps1" Then
    WScript.Quit 4
End If
If InStr(scriptPath, Chr(34)) > 0 Then
    WScript.Quit 5
End If

Dim shell, powershellPath, command, exitCode
Set shell = CreateObject("WScript.Shell")
powershellPath = shell.ExpandEnvironmentStrings( _
    "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" _
)
command = Chr(34) & powershellPath & Chr(34) & _
    " -NoLogo -NoProfile -NonInteractive" & _
    " -ExecutionPolicy Bypass -File " & _
    Chr(34) & scriptPath & Chr(34)

' Window style 0 oculta el proceso y True mantiene WScript esperando. De este
' modo el Programador de tareas supervisa toda la cadena de procesos.
exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode
