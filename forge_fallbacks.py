import os
from google import genai
from google.genai import types

import tvc_config
PROJECT_DIR = tvc_config.PATHS["root"]
INTEL_DIR = os.path.join(PROJECT_DIR, "intelligence_7min")
EPOCH_ASSETS_DIR = os.path.join(INTEL_DIR, "epoch_assets")

from tvc_vault import get_secret
api_key = get_secret("key_HGmChvaB")

# MIGRATED TO FIREWORKS: client = genai.Client(api_key=api_key)

missing_epochs = [26, 31]

for ep in missing_epochs:
    print(f"Forging Fallback Epoch {ep}...")
    prompt = "Cinematic b-roll of a healthy woman over 50 walking outdoors, beautiful soft lighting, fitness tracking."
    
    result = client.models.generate_content(
        model='gemini-3-pro-image-preview',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="16:9")
        )
    )
    
    output_path = os.path.join(EPOCH_ASSETS_DIR, f"epoch_{ep:03d}.png")
    for part in result.parts:
        if part.as_image():
            with open(output_path, "wb") as f:
                f.write(part.as_image().image_bytes)
            print(f"✅ Saved Fallback {output_path}")
            break
