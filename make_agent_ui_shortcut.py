import os
import subprocess
import sys


APP_ROOT = os.path.abspath(os.path.dirname(__file__))
UI_SCRIPT = os.path.join(APP_ROOT, "tvc_studio_agent_ui.py")


def _desktop_path() -> str:
    user = os.path.expanduser("~")
    desktop = os.path.join(user, "Desktop")
    if os.path.isdir(desktop):
        return desktop
    return user


def _pythonw() -> str:
    exe = os.path.abspath(sys.executable)
    if exe.lower().endswith("python.exe"):
        alt = exe[:-10] + "pythonw.exe"
        if os.path.exists(alt):
            return alt
    return exe


def _ps_quote(value: str) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def create_shortcut() -> str:
    if not os.path.exists(UI_SCRIPT):
        raise FileNotFoundError(f"UI script not found: {UI_SCRIPT}")
    if os.path.basename(os.path.normpath(APP_ROOT)).lower() != "video_production_agent":
        raise RuntimeError(f"Blocked: APP_ROOT is not Video_production_agent: {APP_ROOT}")

    desktop = _desktop_path()
    lnk_path = os.path.join(desktop, "TVC Studio Agent.lnk")
    target = _pythonw()
    icon = target

    arg_value = f'"{UI_SCRIPT}"'

    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut({_ps_quote(lnk_path)})
$sc.TargetPath = {_ps_quote(target)}
$sc.Arguments = {_ps_quote(arg_value)}
$sc.WorkingDirectory = {_ps_quote(APP_ROOT)}
$sc.IconLocation = {_ps_quote(icon + ",0")}
$sc.Description = "TVC Studio Agent (Video_production_agent)"
$sc.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return lnk_path


def main():
    path = create_shortcut()
    print(f"Created shortcut: {path}")


if __name__ == "__main__":
    main()
