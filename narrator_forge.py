import os
import re
import asyncio
import glob
import subprocess

# Directories
import tvc_config
PROJECT_DIR = tvc_config.PATHS["root"]
INTEL_DIR = tvc_config.PATHS["intelligence"]
ASSETS_DIR = tvc_config.PATHS["assets"]

# Files
RAW_SCRIPT = os.path.join(INTEL_DIR, "script.txt")
PROCESSED_SCRIPT = os.path.join(INTEL_DIR, "processed_script.txt")
AUDIO_OUTPUT = os.path.join(PROJECT_DIR, "womens_health_vo.mp3")
VTT_OUTPUT = os.path.join(PROJECT_DIR, "womens_health_vo.vtt")
FINAL_VIDEO = os.path.join(PROJECT_DIR, "Womens_Health_Masterclass.mp4")

VOICE = "en-GB-RyanNeural"  # or en-US-AvaNeural

# ==========================================
# 1. THE CINEMATIC PROSODY PREPROCESSOR (CPP)
# ==========================================
CLAUSE_STARTERS = {
    'and', 'but', 'or', 'yet', 'so', 'nor', 'for',
    'we', 'they', 'it', 'its', 'our', 'the', 'this', 'that', 'those', 'these',
    'his', 'her', 'she', 'he', 'a', 'an', 'who', 'which', 'whom', 'whose',
    'in', 'on', 'at', 'to', 'from', 'with', 'as', 'if', 'by', 'of',
    'even', 'while', 'where', 'when', 'whether', 'not', 'no', 'every', 'each',
    'once', 'still', 'however', 'therefore', 'thus', 'instead', 'rather',
}

def apply_cpp(text: str) -> str:
    result_parts = []
    i = 0
    while i < len(text):
        if text[i] == ',' and i + 1 < len(text) and text[i + 1] == ' ':
            rest = text[i + 1:].lstrip()
            next_word_match = re.match(r'([a-zA-Z\-]+)', rest)
            if next_word_match:
                next_word = next_word_match.group(1).lower()
                if next_word in CLAUSE_STARTERS or next_word.endswith('ing'):
                    result_parts.append(text[i])
                else:
                    pass # Remove the comma
            else:
                result_parts.append(text[i])
        elif text[i] == '\u2014':  # em-dash
            result_parts.append('... ')
            if i + 1 < len(text) and text[i + 1] == ' ':
                i += 1
        elif text[i] == '\u2013':  # en-dash
            result_parts.append('... ')
            if i + 1 < len(text) and text[i + 1] == ' ':
                i += 1
        else:
            result_parts.append(text[i])
        i += 1

    processed = ''.join(result_parts)
    print(f"[CPP] Original Commas: {text.count(',')} | Final Commas: {processed.count(',')} | Removed: {text.count(',') - processed.count(',')}")
    return processed

# ==========================================
# 2. TTS GENERATION
# ==========================================
async def generate_audio():
    import edge_tts
    print("[TTS] Synthesizing Voiceover...")
    with open(PROCESSED_SCRIPT, 'r', encoding='utf-8') as f:
        text = f.read()
    
    communicate = edge_tts.Communicate(text, VOICE, rate="+5%")
    submaker = edge_tts.SubMaker()
    
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            submaker.feed(chunk)
            
    with open(AUDIO_OUTPUT, 'wb') as f:
        for c in audio_chunks:
            f.write(c)
            
    srt_content = submaker.get_srt()
    vtt_content = "WEBVTT\n\n" + srt_content.replace(',', '.')
    with open(VTT_OUTPUT, 'w', encoding='utf-8') as f:
        f.write(vtt_content)
    print("[TTS] Audio Synthesis Complete.")

# ==========================================
# 3. FFMPEG RENDER
# ==========================================
def render_video():
    print("[RENDER] Assembling Cinematic MP4...")
    
    # Get audio duration
    dur_str = subprocess.getoutput(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{AUDIO_OUTPUT}"')
    try:
        audio_dur = float(dur_str.strip())
    except:
        audio_dur = 60.0 # fallback
        
    images = sorted(glob.glob(os.path.join(ASSETS_DIR, "scene_*.png")))
    num_images = len(images)
    if num_images == 0:
        print("[RENDER] No images found. Aborting.")
        return
        
    xfade = 0.8
    # Calculate duration each image must be on screen (+ xfade overlap)
    per_img = round(audio_dur / num_images + xfade, 3) 
    
    cmd = ["ffmpeg", "-y"]
    for img in images:
        cmd += ["-loop", "1", "-t", str(per_img), "-i", img]
    cmd += ["-i", AUDIO_OUTPUT]
    
    frames = int(per_img * 30)
    net = round(per_img - xfade, 3)
    
    filt = []
    # Add Ken Burns zoom to each image
    for i in range(num_images):
        filt.append(
            f"[{i}:v]scale=3840:-1,zoompan=z='if(lte(zoom,1.0),1.04,zoom)'"
            f":d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s=1920x1080:fps=30,setpts=PTS-STARTPTS,format=yuv420p[v{i}]"
        )
        
    # Link fader
    prev = "v0"
    for i in range(1, num_images):
        nxt = f"xf{i}"
        offset = round(i * net, 3)
        filt.append(
            f"[{prev}][v{i}]xfade=transition=smoothleft:duration={xfade}:offset={offset}[{nxt}]"
        )
        prev = nxt
        
    cmd += [
        "-filter_complex", ";".join(filt),
        "-map", f"[{prev}]", "-map", f"{num_images}:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-shortest", FINAL_VIDEO
    ]
    
    print("[RENDER] Running FFmpeg pipeline with active crossfade smoothing...")
    subprocess.run(cmd, cwd=PROJECT_DIR)
    print(f"[RENDER] Done -> {FINAL_VIDEO}")

# ==========================================
# MAIN ROUTINE
# ==========================================
if __name__ == "__main__":
    with open(RAW_SCRIPT, 'r', encoding='utf-8') as f:
        raw = f.read()
    
    # 1. CPP 
    processed = apply_cpp(raw)
    with open(PROCESSED_SCRIPT, 'w', encoding='utf-8') as f:
        f.write(processed)
        
    # 2. Voice
    if not os.path.exists(AUDIO_OUTPUT) or os.path.getsize(AUDIO_OUTPUT) < 1000:
        asyncio.run(generate_audio())
        
    # 3. Render
    if not os.path.exists(FINAL_VIDEO):
        render_video()
