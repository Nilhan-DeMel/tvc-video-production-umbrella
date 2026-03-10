import time
import sys
import os, json
from google import genai
from google.genai import types

def main():
    print("Initiating Supreme Video Weapon: Veo 3.1")
    from tvc_vault import get_secret
    v_key = get_secret("key_HGmChvaB")
    # MIGRATED TO FIREWORKS: client = genai.Client(api_key=v_key)

    prompt = (
        "A breathtaking aerial tracking shot over a futuristic neon city "
        "at night. Flying cars streak past towering glass skyscrapers, "
        "leaving trails of light. The camera pans upwards to reveal "
        "a massive, glowing orbital station in the star-filled sky. "
        "Audio: Deep, pulsing cyberpunk synth bass and the futuristic whir of engines."
    )

    print("Submitting prompt:")
    print(prompt)
    print()

    operation = client.models.generate_videos(
        model="veo-3.1-generate-preview",
        prompt=prompt,
    )

    print(f"Operation created: {operation.name}")
    print("Waiting for generation to complete (this will take a few minutes)...")

    while not operation.done:
        print(f"Polling status... sleeping 10 seconds")
        time.sleep(10)
        # Re-fetch the operation object by passing the current operation back into the SDK
        operation = client.operations.get(operation=operation)
        
    if operation.error:
        print(f"Generation failed: {operation.error}")
        return
        
    print("Generation complete! Downloading video...")
    try:
        video = operation.response.generated_videos[0]
        video_uri = video.video.uri
        print(f"Video URI: {video_uri}")

        # Download via the Files API and save to disk
        output_path = "cinematic_neon_city.mp4"
        response = client.files.download(file=video.video)
        with open(output_path, "wb") as f:
            f.write(response)
        print(f"[DONE] Supreme Video rendered to: {output_path}")
    except Exception as e:
        print(f"Failed to extract video: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
