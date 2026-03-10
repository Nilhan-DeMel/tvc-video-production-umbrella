Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "C:\Users\Nilhan.dev\Desktop\TVC Emperor.lnk"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "wscript.exe"
oLink.Arguments = """D:\AI-Apps-In-Drive\App_Station\Video_production\Launch_TVC_Empire.vbs"""
oLink.WorkingDirectory = "D:\AI-Apps-In-Drive\App_Station\Video_production"
oLink.Description = "Launch TVC Video Production"
oLink.IconLocation = "D:\AI-Apps-In-Drive\App_Station\Video_production\tvc_icon.ico"
oLink.Save
