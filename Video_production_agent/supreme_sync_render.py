import os
import json
import subprocess

# Setup
import tvc_config
PROJECT_DIR = tvc_config.PATHS["root"]
INTEL_DIR = os.path.join(PROJECT_DIR, "intelligence_7min")
MATRIX_FILE = os.path.join(INTEL_DIR, "sync_matrix.json")
EPOCH_ASSETS_DIR = os.path.join(INTEL_DIR, "epoch_assets")
AUDIO_FILE = os.path.join(INTEL_DIR, "master_voiceover.mp3")
ASS_FILE = os.path.join(INTEL_DIR, "dynamic_typography.ass")

# Windows handles backslashes inside ffmpeg ass= filter poorly, and absolute paths with colons break filter syntax.
ASS_FILE_FFMPEG = "intelligence_7min/dynamic_typography.ass"

# The FFMPEG filter script to bypass Windows 32K CMD limits
FILTER_SCRIPT = os.path.join(INTEL_DIR, "master_filter.txt")
FINAL_VIDEO = os.path.join(PROJECT_DIR, "Womens_Health_SOTA_7Min.mp4")

XFADE_DUR = 0.5 # 500ms crossfade

def forge_master_render():
    print(f"🎬 [STAGE 5] Forging the Master Render Array...")
    
    with open(MATRIX_FILE, 'r', encoding='utf-8') as f:
        epochs = json.load(f)
        
    num_images = len(epochs)
    if num_images == 0:
        print("❌ FATAL: No epochs loaded.")
        return

    cmd = ["ffmpeg", "-y"]
    
    # 1. Inputs
    for epoch in epochs:
        img_path = os.path.join(EPOCH_ASSETS_DIR, f"epoch_{epoch['id']:03d}.png")
        if not os.path.exists(img_path):
            print(f"❌ FATAL: Missing {img_path}")
            return
            
        dur = epoch['duration']
        # Each image MUST stay on screen for its semantic duration + the crossfade time
        img_on_screen_time = dur + XFADE_DUR
        cmd += ["-loop", "1", "-t", str(img_on_screen_time), "-i", img_path]
        
    cmd += ["-i", AUDIO_FILE]

    # 2. Build Filter Complex
    filt = []
    
    # Zoom/Pan logic for every image exactly relative to its semantic time
    # This guarantees the image is moving for exactly the amount of time it is on screen
    for i, epoch in enumerate(epochs):
        img_dur = epoch['duration'] + XFADE_DUR
        frames = int(img_dur * 30) # 30fps
        filt.append(
            f"[{i}:v]scale=3840:-1,zoompan=z='if(lte(zoom,1.0),1.04,zoom)'"
            f":d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s=1920x1080:fps=30,setpts=PTS-STARTPTS,format=yuv420p[v{i}]"
        )
        
    # Crossfades
    prev = "v0"
    current_offset_time = epochs[0]['duration'] # First fade happens exactly when epoch 1 ends
    
    for i in range(1, num_images):
        nxt = f"xf{i}"
        
        # Crossfade from prev to current starting at current_offset_time
        filt.append(
            f"[{prev}][v{i}]xfade=transition=fade:duration={XFADE_DUR}:offset={current_offset_time}[{nxt}]"
        )
        prev = nxt
        current_offset_time += epochs[i]['duration']

    # Final Subtitle Overlay Layer
    filt.append(f"[{prev}]ass='{ASS_FILE_FFMPEG}'[outv]")

    # Write filter to file to avoid Command Line length limits
    with open(FILTER_SCRIPT, 'w', encoding='utf-8') as f:
        f.write(";\n".join(filt))
        
    cmd += [
        "-filter_complex_script", FILTER_SCRIPT,
        "-map", "[outv]", "-map", f"{num_images}:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-shortest", FINAL_VIDEO
    ]
    
    print(f"✅ Filter complex constructed ({len(filt)} operations).")
    print(f"🚀 Igniting FFmpeg render engine...")
    
    try:
        subprocess.run(cmd, cwd=PROJECT_DIR, check=True)
        print(f"\n✅ [DONE] SOTA Masterpiece Rendered -> {FINAL_VIDEO}")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg Render Failed: {e}")

if __name__ == "__main__":
    forge_master_render()
