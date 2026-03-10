import os
import json
import time
from google import genai
from google.genai import types

from tvc_vault import get_secret

IMPERIAL_API_KEY = get_secret("key_HGmChvaB")
# MIGRATED TO FIREWORKS: client = genai.Client(api_key=IMPERIAL_API_KEY)

import tvc_config
MODEL_NAME = "imagen-3.0-generate-001"
OUTPUT_DIR = tvc_config.PATHS["assets"]

def forge_mass_images(prompt_dict: dict):
    """
    Takes a dictionary of { "filename_prefix": "Detailed high-fidelity prompt..." }
    and renders them all to disk using Google's Imagen 3.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print(f"\n[IMAGEN-3 FORGE] Igniting mass generation protocol for {len(prompt_dict)} assets...")
    print(f"[IMAGEN-3 FORGE] Output Directory: {OUTPUT_DIR}\n")
    
    success_count = 0
    for filename, prompt in prompt_dict.items():
        output_path = os.path.join(OUTPUT_DIR, f"{filename}.png")
        
        # Skip if already exists (resume capability)
        if os.path.exists(output_path):
            print(f"  [SKIP] {filename}.png already exists. Skipping.")
            success_count += 1
            continue
            
        print(f"  [FORGING] {filename}.png -> {prompt[:60]}...")
        
        try:
            # Using the Gemini 3 Pro Image preview model as documented
            result = client.models.generate_content(
                model='gemini-3-pro-image-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio="16:9",
                        # We cannot set number_of_images on generate_content
                    )
                )
            )
            
            # Write bytes directly to disk
            for part in result.parts:
                if part.as_image():
                    image_bytes = part.as_image().image_bytes
                    with open(output_path, "wb") as f:
                        f.write(image_bytes)
                    print(f"  [SUCCESS] -> Saved {filename}.png")
                    success_count += 1
                    break
            
        except Exception as e:
            print(f"  [ERROR] Failed to forge {filename}: {e}")
            
        # Respect API rate limits
        time.sleep(2)

    print(f"\n[IMAGEN-3 FORGE] Extraction Complete. {success_count}/{len(prompt_dict)} assets secured.")

# If run as the main script via CLI, taking a JSON file of prompts
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                prompts = json.load(f)
            forge_mass_images(prompts)
        except Exception as e:
            print(f"Error loading {json_file}: {e}")
    else:
        print("Usage: python imagen_forge.py <path_to_prompts.json>")
        print("\nTest mode executing with two sample prompts...\n")
        prompts = {
            "test_sample_01": "Cinematic 4K shot, 1960s London, vintage aesthetic",
            "test_sample_02": "Cinematic close-up of a fresh sliced tomato on a dark wooden board, bright studio lighting, photorealistic macro"
        }
        forge_mass_images(prompts)
