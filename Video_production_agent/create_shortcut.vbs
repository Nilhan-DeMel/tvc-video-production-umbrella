Set oWS = WScript.CreateObject("WScript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")

appDir = oFSO.GetParentFolderName(WScript.ScriptFullName)
desktopDir = oWS.SpecialFolders("Desktop")
sLinkFile = oFSO.BuildPath(desktopDir, "TVC Emperor.lnk")

Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "wscript.exe"
oLink.Arguments = """" & oFSO.BuildPath(appDir, "Launch_TVC_Empire.vbs") & """"
oLink.WorkingDirectory = appDir
oLink.Description = "Launch TVC Video Production"
oLink.IconLocation = oFSO.BuildPath(appDir, "tvc_icon.ico")
oLink.Save
