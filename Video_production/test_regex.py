import json
import re
import os

import tvc_config
intel_dir = tvc_config.PATHS["intelligence"]
prompts_file = os.path.join(intel_dir, 'master_prompts.json')

with open(prompts_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

sota_prompts = data if isinstance(data, list) else data.get('prompts', [])

print(f'Testing regex on {len(sota_prompts)} prompts...\n')

for i, current_prompt in enumerate(sota_prompts):
    scene_match = re.search(
        r'(?:Cinematic 16:9|Photorealistic 16:9)\s+(.+?)(?:\s*ABSOLUTE NEGATIVE|$)',
        current_prompt, re.DOTALL | re.IGNORECASE
    )
    raw_scene = scene_match.group(1).strip() if scene_match else current_prompt[-200:]
    scene_clauses = [c.strip() for c in raw_scene.split(',') if c.strip()]
    main_description = ', '.join(scene_clauses[:2])
    print(f'Prompt {i+1}: {main_description[:80]}...')
