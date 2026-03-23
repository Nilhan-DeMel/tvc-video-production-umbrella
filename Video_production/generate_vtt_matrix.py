import os
import asyncio
import edge_tts
import json

# Paths
import tvc_config
PROJECT_DIR = tvc_config.PATHS["root"]
INTEL_DIR = tvc_config.PATHS["intelligence_7min"]
SCRIPT_FILE = os.path.join(INTEL_DIR, "master_7min_script.txt")
AUDIO_FILE = os.path.join(INTEL_DIR, "master_voiceover.mp3")
VTT_FILE = os.path.join(INTEL_DIR, "master_timings.vtt")
MATRIX_FILE = os.path.join(INTEL_DIR, "sync_matrix.json")

VOICE = "en-GB-RyanNeural"
MAX_EPOCH_DURATION = 4.8 # seconds

async def synthesize_audio():
    print(f"🎙️ [STAGE 2] Synthesizing 8.5-minute audio via edge-tts ({VOICE})...")
    with open(SCRIPT_FILE, 'r', encoding='utf-8') as f:
        text = f.read()

    communicate = edge_tts.Communicate(text, VOICE, boundary="WordBoundary")
    submaker = edge_tts.SubMaker()

    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            submaker.feed(chunk)

    with open(AUDIO_FILE, 'wb') as f:
        for c in audio_chunks:
            f.write(c)

    srt_content = submaker.get_srt()
    vtt_content = "WEBVTT\n\n" + srt_content.replace(',', '.')
    with open(VTT_FILE, 'w', encoding='utf-8') as f:
        f.write(vtt_content)
    
    print(f"✅ Audio Synthesis Complete! -> {AUDIO_FILE}")

def parse_vtt_to_matrix():
    print("🧠 [STAGE 2] Parsing VTT into Max 4.8-Second Visual Epochs...")
    
    with open(VTT_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    def time_to_sec(t_str):
        h, m, s = t_str.split(':')
        s, ms = s.split('.')
        return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0

    epochs = []
    current_epoch = {"id": 1, "start_time": 0.0, "end_time": 0.0, "duration": 0.0, "text": ""}
    
    captions = []
    current_cap = None
    
    for line in lines:
        line = line.strip()
        if "-->" in line:
            parts = line.split("-->")
            start = time_to_sec(parts[0].strip())
            end = time_to_sec(parts[1].strip())
            current_cap = {"start": start, "end": end, "text": ""}
        elif line and line != "WEBVTT" and not line.isdigit():
            if current_cap:
                current_cap["text"] = line
                captions.append(current_cap)
                current_cap = None

    if not captions:
        print("❌ FATAL: No captions parsed.")
        return

    # Chunk captions into epochs
    epoch_id = 1
    current_start = captions[0]["start"]
    current_text_chunks = []
    
    for i, cap in enumerate(captions):
        duration_so_far = cap["end"] - current_start
        
        # If adding this word exceeds MAX_EPOCH_DURATION or it's a long pause
        # (We could check distance between previous end and current start, but let's stick to duration)
        if duration_so_far > MAX_EPOCH_DURATION and len(current_text_chunks) > 0:
            # Finalize previous epoch
            epochs.append({
                "id": epoch_id,
                "start_time": round(current_start, 3),
                "end_time": round(captions[i-1]["end"], 3),
                "duration": round(captions[i-1]["end"] - current_start, 3),
                "text": " ".join(current_text_chunks).replace('  ', ' ')
            })
            # Start new epoch
            epoch_id += 1
            current_start = cap["start"]
            current_text_chunks = [cap["text"]]
        else:
            current_text_chunks.append(cap["text"])
            
    # Add final epoch
    if current_text_chunks:
        epochs.append({
            "id": epoch_id,
            "start_time": round(current_start, 3),
            "end_time": round(captions[-1]["end"], 3),
            "duration": round(captions[-1]["end"] - current_start, 3),
            "text": " ".join(current_text_chunks).replace('  ', ' ')
        })

    with open(MATRIX_FILE, 'w', encoding='utf-8') as f:
        json.dump(epochs, f, indent=4)
        
    print(f"✅ Sync Matrix Forged! {len(epochs)} Total Visual Epochs created.")
    print(f"💾 Saved to: {MATRIX_FILE}")

if __name__ == "__main__":
    if not os.path.exists(AUDIO_FILE) or not os.path.exists(VTT_FILE):
        asyncio.run(synthesize_audio())
    else:
        print("[SKIP] Audio already exists, proceeding directly to VTT parse...")
        
    parse_vtt_to_matrix()
