import os
import subprocess
import glob
from google import genai

# Setup directories
import tvc_config
PROJECT_DIR = tvc_config.PATHS["root"]
INTEL_DIR = tvc_config.PATHS["intelligence_7min"]
os.makedirs(INTEL_DIR, exist_ok=True)

# 1. Harvest Transcripts via yt-dlp
print("🚀 [STAGE 1] Activating yt-dlp to harvest intelligence on Women's Health after 50...")

query = "women's health after 50 advice tips masterclass"
cmd = [
    "yt-dlp",
    "--write-auto-subs",
    "--sub-langs", "en",
    "--sub-format", "vtt",
    "--skip-download",
    f"ytsearch15:{query}", # Grab top 15 videos to ensure massive intelligence
    "-o", os.path.join(INTEL_DIR, "%(id)s.%(ext)s")
]

try:
    subprocess.run(cmd, check=True)
    print("✅ Intelligence Harvested.")
except Exception as e:
    print(f"⚠️ Error in yt-dlp: {e}")

# 2. Combine Transcripts
print("⚙️ [STAGE 2] Synthesizing raw VTT transcripts into local memory...")

combined_text = ""
vtt_files = glob.glob(os.path.join(INTEL_DIR, "*.en.vtt"))

if not vtt_files:
    print("❌ FATAL: No VTT files downloaded. Exiting.")
    exit(1)

for file in vtt_files:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
            # Clean VTT timing tags to save tokens
            import re
            content = re.sub(r'<[^>]+>', '', content)
            content = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*\n', '', content)
            combined_text += content + "\n---\n"
    except Exception as e:
        print(f"Skipping {file}: {e}")

print(f"✅ Loaded {len(vtt_files)} transcripts. Total raw characters: {len(combined_text)}")

# 3. Prompt Gemini 2.5 Pro for the 7-Minute Masterclass Script
print("🧠 [STAGE 3] Engaging Gemini 2.5 Pro for 1200-word SOTA Synthesis...")

from tvc_vault import get_secret
api_key = get_secret("key_HGmChvaB")

# MIGRATED TO FIREWORKS: client = genai.Client(api_key=api_key)

system_instruction = """
You are the absolute master of health, wellness, and anti-aging advice for women over 50. 
Distill the absolute most valuable, medically sound, and actionable advice from the provided transcripts. 
You must output a highly engaging, narratively cohesive Youtube 7-minute Masterclass script.

CRITICAL REQUIREMENTS:
1. DURATION: The script MUST be roughly 1200 words (this guarantees a 7-minute run time at 170 WPM).
2. FORMATTING: Output ONLY the spoken text. NO headers, NO [Upbeat music plays], NO scene directions.
3. LINE BREAKS: Every sentence or distinct idea MUST be on its own line. This limits lines to readable chunks that we will later parse into 3-5 second visual epochs. Do not use massive paragraph blocks.
4. TONE: Classy, empowering, highly educational, direct, and sophisticated.
"""

response = client.models.generate_content(
    model="gemini-2.5-pro",
    contents=combined_text[:1000000],  # Gemini 2.5 Pro handles massive context
    config={"system_instruction": system_instruction, "temperature": 0.4}
)

script_path = os.path.join(INTEL_DIR, "master_7min_script.txt")
with open(script_path, 'w', encoding='utf-8') as f:
    f.write(response.text.strip())

word_count = len(response.text.split())
est_minutes = word_count / 170

print(f"✅ SOTA Synthesis Complete!")
print(f"📊 Word Count: {word_count} words")
print(f"⏱️ Estimated Duration: {est_minutes:.1f} minutes")
print(f"💾 Saved to: {script_path}")
