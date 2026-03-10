import os
import json

# Setup
import tvc_config
PROJECT_DIR = tvc_config.PATHS["root"]
INTEL_DIR = os.path.join(PROJECT_DIR, "intelligence_7min")
MATRIX_FILE = os.path.join(INTEL_DIR, "sync_matrix.json")
ASS_FILE = os.path.join(INTEL_DIR, "dynamic_typography.ass")

# ASS Style config for "Classy highlighted blurbs"
# Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
# Color format in ASS is &HAABBGGRR.
# &H00FFFFFF = Solid White.
# &H80000000 = 50% transparent Black.
# BorderStyle = 3 (Opaque box background instead of outline)

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ClassyBlurb,Arial,65,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,3,10,0,2,100,100,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def sec_to_ass_time(seconds):
    """Converts seconds to H:MM:SS.cs (centiseconds) format required by ASS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        cs = 99 # cap to 99 centiseconds
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def forge_typography():
    print("🎨 [STAGE 4] Forging Advanced SubStation Alpha (.ass) Dynamic Typography...")
    
    with open(MATRIX_FILE, 'r', encoding='utf-8') as f:
        epochs = json.load(f)
        
    with open(ASS_FILE, 'w', encoding='utf-8') as f:
        f.write(ASS_HEADER)
        
        for epoch in epochs:
            start_ass = sec_to_ass_time(epoch['start_time'])
            end_ass = sec_to_ass_time(epoch['end_time'])
            text = epoch['text'].replace('\n', ' ')
            
            # Add line break if text is very long to prevent it stretching too wide
            # Even with WrapStyle: 1, explicit control is sometimes better
            # But the max epoch is 4.8 seconds, so text won't be insanely long.
            
            # Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
            f.write(f"Dialogue: 0,{start_ass},{end_ass},ClassyBlurb,,0,0,0,,{text}\n")
            
    print(f"✅ Typography Forged successfully! -> {ASS_FILE}")

if __name__ == "__main__":
    forge_typography()
