import os
import re
import json
import time
import asyncio
import subprocess
from google import genai
from google.genai import types
from PIL import Image

# Import Smartcrop
try:
    import smartcrop
except ImportError:
    print("FATAL: smartcrop not installed. Run `pip install smartcrop Pillow`")
    sys.exit(1)

import tvc_config
PROJECT_DIR = tvc_config.PATHS["root"]
INTEL_DIR = os.path.join(PROJECT_DIR, "tvc_nle_temp")
os.makedirs(INTEL_DIR, exist_ok=True)

VOICE = "en-GB-RyanNeural"
MAX_EPOCH_DUR = 4.8
XFADE_DUR = 0.5

# ============================================================
# STAGE 0: INTELLIGENCE HARVESTER (Optional)
# ============================================================
def harvest_script(client: genai.Client, prompt: str) -> str:
    """ If the user gives a short prompt, generate the 1200-word SOTA script. """
    print(f"📡 [TVC NARRATOR] Harvesting Intelligence for: {prompt}")
    sys_inst = (
        "You are the absolute master of cinematic documentary scriptwriting. "
        "Write a highly engaging, narratively cohesive 1200-word video script about the user's prompt. "
        "CRITICAL: Output ONLY the spoken text. NO headers, NO [Upbeat music plays], NO scene directions. "
        "EVERY sentence must be on its own line."
    )
    res = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=sys_inst, temperature=0.4)
    )
    raw_script = res.text.strip()
    script_path = os.path.join(INTEL_DIR, "master_script.txt")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(raw_script)
    print(f"✅ SOTA Script Synthesized: {len(raw_script.split())} words.")
    return raw_script

# ============================================================
# STAGE 1: CPP (Cinematic Prosody Preprocessor)
# ============================================================
def execute_cpp(raw_script: str) -> str:
    """ Strips disruptive commas that cause edge-tts to drag, keeping grammatical stops. """
    cpp_text = re.sub(r'(\w+)\s*,\s*(\w+)', r'\1 \2', raw_script) # Remove mid-clause commas
    return cpp_text

# ============================================================
# STAGE 2: AUDIO & VTT FORGE
# ============================================================
def forge_audio(cpp_script: str) -> tuple:
    import edge_tts
    print("🎙️ [TVC NARRATOR] Forging neural voiceover via edge-tts...")
    audio_file = os.path.join(INTEL_DIR, "master_narration.mp3")
    vtt_file = os.path.join(INTEL_DIR, "master_timings.vtt")
    
    async def _synth():
        comm = edge_tts.Communicate(cpp_script, VOICE, boundary="WordBoundary") # FIX 7: Forced WordBoundary
        sub = edge_tts.SubMaker()
        chunks = []
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                sub.feed(chunk)
        with open(audio_file, "wb") as f:
            for c in chunks: f.write(c)
        with open(vtt_file, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n" + sub.get_srt().replace(',', '.'))
            
    asyncio.run(_synth())
    if not os.path.exists(vtt_file) or os.path.getsize(vtt_file) < 20:
        raise RuntimeError("VTT file generation failed. WordBoundary likely missing.")
    return audio_file, vtt_file

# ============================================================
# STAGE 3: SOTA DUAL-TRACK ALIGNMENT (Gemini VTT Parser)
# ============================================================
def forge_sync_matrix(client: genai.Client, raw_script: str, vtt_file: str) -> list:
    """ Maps VTT timestamps back to the ORIGINAL raw script to preserve punctuation and numbers (Fixes 11, 12, 13). """
    print("🧠 [TVC NARRATOR] Aligning dual-track script via Gemini 2.5 Pro...")
    matrix_file = os.path.join(INTEL_DIR, "sync_matrix.json")
    
    with open(vtt_file, "r", encoding="utf-8") as f:
        vtt_data = f.read()

    # If script is huge, chunk it. For 7 mins, Gemini 2.5 Pro handles the 1.5M token window easily.
    prompt = f"""
    You are a precision video alignment engineer.
    I am providing you with:
    1. A RAW SCRIPT (with perfect punctuation and numbers).
    2. A VTT FILE (which strips punctuation and numbers, but contains precise word boundary timestamps).
    
    Your task:
    Map the precise start and end times from the VTT onto the EXACT sentences from the RAW SCRIPT.
    Chunk the RAW SCRIPT into visual "Epochs" lasting a MAX of {MAX_EPOCH_DUR} seconds each.
    Return ONLY a raw JSON array of objects. No markdown formatting, no code blocks. Just the array.
    
    JSON Object Format:
    {{
        "id": <int>,
        "start_time": <float seconds>,
        "end_time": <float seconds>,
        "duration": <float seconds>,
        "text": "<The EXACT string chunk from the RAW SCRIPT, preserving commas, periods, and numbers>"
    }}
    
    RAW SCRIPT:
    {raw_script}
    
    VTT FILE:
    {vtt_data}
    """
    
    sys_inst = "Output pure raw JSON. Nothing else. Ensure temporal continuity."
    resp = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=sys_inst, temperature=0.1)
    )
    
    json_text = resp.text.strip()
    if json_text.startswith("```json"): json_text = json_text[7:-3]
    elif json_text.startswith("```"): json_text = json_text[3:-3]
    
    try:
        epochs = json.loads(json_text)
    except json.JSONDecodeError:
        print("FATAL: Gemini failed to return valid JSON matrix.")
        print("RAW RESPONSE:", resp.text)
        epochs = [] # Fallback
        
    with open(matrix_file, "w", encoding="utf-8") as f:
        json.dump(epochs, f, indent=4)
        
    return epochs

# ============================================================
# STAGE 4: BATCH GENERATION WITH EXPONENTIAL RETRY
# ============================================================
def forge_epoch_assets(client: genai.Client, epochs: list):
    """ Generates images perfectly mapped to semantic text with exact loop retry. """
    print(f"🎬 [TVC NARRATOR] Forging {len(epochs)} Epoch Assets...")
    asset_dir = os.path.join(INTEL_DIR, "epoch_assets")
    os.makedirs(asset_dir, exist_ok=True)
    
    for epoch in epochs:
        ep_id = epoch['id']
        txt = epoch['text']
        filepath = os.path.join(asset_dir, f"epoch_{ep_id:03d}.png")
        if os.path.exists(filepath): continue
        
        prompt = f"Cinematic, 4K b-roll, professional: {txt}"
        print(f"  -> Forging {ep_id:03d}: {txt[:40]}...")
        
        # FIX 5: Robust retry loop. NO generic fallbacks.
        max_retries = 5
        for attempt in range(max_retries):
            try:
                res = client.models.generate_content(
                    model='gemini-3-pro-image-preview',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(aspect_ratio="16:9")
                    )
                )
                for part in res.parts:
                    if part.as_image():
                        with open(filepath, "wb") as f: f.write(part.as_image().image_bytes)
                        break
                break # Success, exit retry loop
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    wait_time = 15 * (attempt + 1)
                    print(f"     [429 Quota] Retrying {ep_id:03d} in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"     [API Error] {err}")
                    time.sleep(5)
        time.sleep(2) # Baseline pacing

# ============================================================
# STAGE 5: OMNI-CROP (SALIENCY ENFORCEMENT)
# ============================================================
def execute_omnicrop():
    """ Enforces exact 1920x1080 16:9 ratio via entropy detection (Fix 10). """
    print("✂️ [TVC NARRATOR] Executing Omni-Crop Saliency Enforcement...")
    asset_dir = os.path.join(INTEL_DIR, "epoch_assets")
    sc = smartcrop.SmartCrop()
    target_w, target_h = 1920, 1080
    
    for file in os.listdir(asset_dir):
        if not file.endswith(".png"): continue
        fp = os.path.join(asset_dir, file)
        with Image.open(fp) as img:
            if img.mode != 'RGB': img = img.convert('RGB')
            w, h = img.size
            if w == 1920 and h == 1080: continue # Already perfect
            
            scale = min(w / target_w, h / target_h)
            cw, ch = int(target_w * scale), int(target_h * scale)
            result = sc.crop(img, cw, ch)
            tc = result['top_crop']
            cropped = img.crop((tc['x'], tc['y'], tc['x'] + tc['width'], tc['y'] + tc['height']))
            resized = cropped.resize((1920, 1080), Image.Resampling.LANCZOS)
            resized.save(fp, quality=95)

# ============================================================
# STAGE 6: DYNAMIC TYPOGRAPHY (CLASSY BLURBS)
# ============================================================
def sec_to_ass(s):
    h, m = int(s // 3600), int((s % 3600) // 60)
    sc, cs = int(s % 60), int(round((s - int(s)) * 100))
    if cs == 100: cs = 99
    return f"{h}:{m:02d}:{sc:02d}.{cs:02d}"

def forge_ass(epochs: list) -> str:
    print("🔤 [TVC NARRATOR] Forging ASS Typography...")
    ass_path = os.path.join(INTEL_DIR, "typography.ass")
    header = "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 1\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: ClassyBlurb,Arial,65,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,3,10,0,2,100,100,80,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header)
        for ep in epochs:
            txt = ep['text'].replace('\n', ' ').replace(',', ', ')
            f.write(f"Dialogue: 0,{sec_to_ass(ep['start_time'])},{sec_to_ass(ep['end_time'])},ClassyBlurb,,0,0,0,,{txt}\n")
    return ass_path

# ============================================================
# STAGE 7: SUPREME SYNC RENDER (ZERO-DRIFT)
# ============================================================
def render_symphony(epochs: list, audio_file: str, ass_file: str, final_output: str):
    """ Executes absolute math to stitch the video to the audio perfectly. """
    print("🎞️ [TVC NARRATOR] Activating Final FFmpeg Symphony Render...")
    asset_dir = os.path.join(INTEL_DIR, "epoch_assets")
    
    cmd = ["ffmpeg", "-y"]
    
    # Inputs
    for ep in epochs:
        img_path = os.path.join(asset_dir, f"epoch_{ep['id']:03d}.png")
        # Fix 4: Total image duration must include the crossfade it participates in
        on_screen_time = ep['duration'] + XFADE_DUR
        cmd += ["-loop", "1", "-t", str(on_screen_time), "-i", img_path]
        
    cmd += ["-i", audio_file] # The final input is audio
    
    filt = []
    # Video pre-processing
    for i, ep in enumerate(epochs):
        frames = int((ep['duration'] + XFADE_DUR) * 30)
        filt.append(f"[{i}:v]scale=1920:1080,zoompan=z='min(zoom+0.0003,1.05)':d={frames}:s=1920x1080:fps=30,setpts=PTS-STARTPTS,format=yuv420p[v{i}]")
        
    # Crossfades with Absolute Drift-Free Math
    prev = "v0"
    current_time = epochs[0]['duration'] # First overlap begins when Epoch 0 semantic time is over
    
    for i in range(1, len(epochs)):
        nxt = f"xf{i}"
        filt.append(f"[{prev}][v{i}]xfade=transition=fade:duration={XFADE_DUR}:offset={current_time}[{nxt}]")
        prev = nxt
        current_time += epochs[i]['duration'] # Next offset pushes exactly the length of Epoch i
        
    # Typography: FIX 6 (Robust relative ASS path format for FFmpeg)
    # Forward slashes required.
    safe_ass = ass_file.replace("\\", "/").split("/")[-2:] # Gets intellectual_7min/typography.ass
    ass_filter_path = "/".join(safe_ass)
    
    filt.append(f"[{prev}]ass='{ass_filter_path}'[outv]")
    
    filt_script = os.path.join(INTEL_DIR, "filter.txt")
    with open(filt_script, "w", encoding="utf-8") as f:
        f.write(";\n".join(filt))
        
    cmd += [
        "-filter_complex_script", filt_script,
        "-map", "[outv]", "-map", f"{len(epochs)}:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        # FIX 8: Do not use -shortest. 
        # The crossfade math guarantees the video track is exactly Audio Length + 0.5s.
        # Allowing FFmpeg to finish on its own ensures no audio is chopped off.
        final_output
    ]
    
    subprocess.run(cmd, cwd=PROJECT_DIR, check=True)
    print(f"\n✅ [DONE] SOTA V2.0 Narrator Pipeline Complete: {final_output}")

# ============================================================
# MAIN ORCHESTRATOR FOR EXPORT
# ============================================================
def execute_narrator_pipeline(user_prompt: str, final_output: str, api_key: str):
    print("="*65)
    print("     TVC SOTA NARRATOR (The 14-Point Drift-Free Engine)")
    print("="*65)
    
    # MIGRATED TO FIREWORKS: client = genai.Client(api_key=api_key)
    
    # 0. Intelligent Script Harvesting (if the input is short, expand it into a full script)
    if len(user_prompt.split()) < 50:
        raw_script = harvest_script(client, user_prompt)
    else:
        raw_script = user_prompt
        
    # 1. Prosody Prep
    cpp_script = execute_cpp(raw_script)
    # 2. Audio Genesis
    aud_path, vtt_path = forge_audio(cpp_script)
    # 3. Dual-Track Sync
    epochs = forge_sync_matrix(client, raw_script, vtt_path)
    if not epochs: raise RuntimeError("Sync matrix failed.")
    # 4. Image Generation
    forge_epoch_assets(client, epochs)
    # 5. Perfect Framing
    execute_omnicrop()
    # 6. SOTA True Typography
    ass_path = forge_ass(epochs)
    # 7. Zero-Drift Symphony
    render_symphony(epochs, aud_path, ass_path, final_output)
    
    return final_output

if __name__ == "__main__":
    pass
