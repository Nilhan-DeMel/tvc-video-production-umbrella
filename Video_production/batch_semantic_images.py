import os
import json
import time
from google import genai
from google.genai import types

# Setup
import tvc_config
PROJECT_DIR = tvc_config.PATHS["root"]
INTEL_DIR = tvc_config.PATHS["intelligence_7min"]
MATRIX_FILE = os.path.join(INTEL_DIR, "sync_matrix.json")
EPOCH_ASSETS_DIR = os.path.join(INTEL_DIR, "epoch_assets")
os.makedirs(EPOCH_ASSETS_DIR, exist_ok=True)

# API
from tvc_vault import get_secret
api_key = get_secret("key_HGmChvaB")

# MIGRATED TO FIREWORKS: client = genai.Client(api_key=api_key)

def batch_semantic_images():
    with open(MATRIX_FILE, 'r', encoding='utf-8') as f:
        epochs = json.load(f)
        
    print(f"🚀 [STAGE 3] Igniting Semantic Image Batching for {len(epochs)} Epochs...")
    
    success_count = 0
    fail_count = 0
    
    for epoch in epochs:
        epoch_id = epoch['id']
        text = epoch['text'].strip()
        filename = f"epoch_{epoch_id:03d}.png"
        output_path = os.path.join(EPOCH_ASSETS_DIR, filename)
        
        # Resume capability
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            print(f"  [SKIP] {filename} already exists.")
            success_count += 1
            continue
            
        # Construct the direct Image prompt based on the epoch text
        # Overriding with safety to avoid false positives on "women's health" anatomy terms
        safe_prompt = (
            f"Cinematic, photorealistic, 4K b-roll footage shot holding on: {text}. "
            "High fidelity, elegant, professional wellness masterclass aesthetic, beautiful lighting, positive energy."
        )
        
        print(f"  [FORGING] Epoch {epoch_id:03d} -> \"{text[:40]}...\"")
        
        try:
            result = client.models.generate_content(
                model='gemini-3-pro-image-preview',
                contents=safe_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio="16:9"
                    )
                )
            )
            
            for part in result.parts:
                if part.as_image():
                    with open(output_path, "wb") as f:
                        f.write(part.as_image().image_bytes)
                    print(f"  [SUCCESS] -> Saved {filename} ({epoch['duration']}s)")
                    success_count += 1
                    break
        except Exception as e:
            print(f"  [ERROR] Epoch {epoch_id:03d} failed: {e}")
            fail_count += 1
            
        time.sleep(3) # Respect API limits (122 images = ~6 minutes)

    print(f"\n✅ [STAGE 3] Semantic Image Batching Complete.")
    print(f"📊 Success: {success_count}/{len(epochs)} | Failed: {fail_count}")

if __name__ == "__main__":
    batch_semantic_images()
