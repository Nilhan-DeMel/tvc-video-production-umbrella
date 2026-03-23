import os
import sys

import tvc_config
# Get the exact path to pythonw.exe in the same dir as the current python.exe
pythonw_path = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
app_dir = tvc_config.PATHS["root"]
script_path = os.path.join(app_dir, "tvc_launcher.py")
icon_path = os.path.join(app_dir, "tvc_icon.ico")
shortcut_path = r"C:\Users\Nilhan.dev\Desktop\TVC Emperor.lnk"

vbs_script = f"""
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{pythonw_path}"
oLink.Arguments = "{script_path}"
oLink.WorkingDirectory = "{app_dir}"
oLink.Description = "Launch TVC Video Production"
oLink.IconLocation = "{icon_path}"
oLink.Save
"""

vbs_path = os.path.join(app_dir, "create_direct_shortcut.vbs")
with open(vbs_path, "w", encoding="utf-8") as f:
    f.write(vbs_script)

os.system(f"cscript //Nologo \"{vbs_path}\"")
os.remove(vbs_path)
print(f"Direct Native Desktop shortcut created targeting: {pythonw_path}")
