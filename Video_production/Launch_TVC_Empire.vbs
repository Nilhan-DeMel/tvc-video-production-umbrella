Set WshShell = CreateObject("WScript.Shell")
' Run pythonw.exe to launch without a console window
WshShell.Run "pythonw.exe tvc_launcher.py", 0, False
