import os, glob

def sweep_and_purge():
    target_dir = r"d:\AI-Apps-In-Drive\App_Station\Video_production"
    py_files = glob.glob(os.path.join(target_dir, "*.py"))
    
    count = 0
    for file in py_files:
        if file.endswith("tvc_langgraph_core.py") or file.endswith("supreme_commander.py") or file.endswith("tvc_vault.py"):
            continue # already handled
            
        with open(file, "r", encoding="utf-8") as f:
            content = f.read()
            
        original = content
        
        # Replace occurrences of getting old secrets
        content = content.replace('get_secret("key_HGmChvaB")', 'get_secret("key_HGmChvaB")')
        content = content.replace('get_secret("key_HGmChvaB")', 'get_secret("key_HGmChvaB")')
        
        # Replace explicitly hardcoded names if assigned to variables (basic sweep)
        content = content.replace('"key_HGmChvaB"', '"key_HGmChvaB"')
        content = content.replace('"key_HGmChvaB"', '"key_HGmChvaB"')
        
        # Change # MIGRATED TO FIREWORKS: client = genai.Client(api_key=...) to a comment since we migrated away
        if 'genai.Client' in content:
            content = content.replace('# MIGRATED TO FIREWORKS: client = genai.Client(', '# MIGRATED TO FIREWORKS: # MIGRATED TO FIREWORKS: client = genai.Client(')
            
        if content != original:
            with open(file, "w", encoding="utf-8") as f:
                f.write(content)
            count += 1
            print(f"[PURGE] Swept {os.path.basename(file)}")

    print(f"Total auxiliary files purged: {count}")

sweep_and_purge()
