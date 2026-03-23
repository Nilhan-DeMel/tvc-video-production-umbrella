import os

path = r'd:\AI-Apps-In-Drive\App_Station\Video_production\tvc_langgraph_core.py'
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Avoid double patching
    if 'SOTA UTF-8 Stream Hardening' not in content:
        hardening = (
            "import io\n"
            "import sys\n"
            "# SOTA UTF-8 Stream Hardening (Phase 24 Windows Stability)\n"
            "if sys.platform == 'win32':\n"
            "    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')\n"
            "    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')\n\n"
        )
        with open(path, 'w', encoding='utf-8') as f:
            f.write(hardening + content)
        print("Successfully patched tvc_langgraph_core.py with UTF-8 hardening.")
    else:
        print("Already patched.")
else:
    print(f"Path {path} not found.")
