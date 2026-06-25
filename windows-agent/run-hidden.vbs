# ============================================================
# run-hidden.vbs - arranca el agente SIN ventana de consola
# Útil para ejecutarlo minimizado o desde el Programador de tareas
# ============================================================
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run """cmd.exe"" /c run.bat", 0, False
