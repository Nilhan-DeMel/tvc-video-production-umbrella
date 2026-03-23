import os

REPLACEMENTS = {
    "\u2705": "[OK]",
    "\u274c": "[FAIL]",
    "\u26a0\ufe0f": "[WARN]",
    "\U0001f50d": "[SEARCH]",
    "\u270d\ufe0f": "[WRITE]",
    "\ud83c\udfac": "[DIRECT]",
    "\ud83c\udf99\ufe0f": "[AUDIO]",
    "\ud83e\udde0": "[BRAIN]",
    "\ud83d\udd28": "[FORGE]",
    "\ud83d\udccc": "[NOTE]",
    "\ud83d\udd01": "[RETRY]",
    "\ud83d\udd2c": "[VERIFY]",
    "\ud83c\udf9e\ufe0f": "[EDITOR]",
    "\u2014": "--",
    "\u2714": "[OK]"
}

files = [
    "tvc_langgraph_core.py",
    "supreme_commander.py",
    "harvester_repro.py",
    "async_verifier.py",
    "tvc_vault.py"
]

for filename in files:
    if not os.path.exists(filename): continue
    print(f"Purging {filename}...")
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for emoji, text in REPLACEMENTS.items():
        content = content.replace(emoji, text)
        
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

print("Purge complete.")
