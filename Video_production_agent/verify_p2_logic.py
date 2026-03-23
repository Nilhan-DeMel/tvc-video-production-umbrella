import re

def test_whisper_word_count_logic(vtt_content, script_content):
    print("Testing Whisper VTT Word Count Logic (ISSUE-007)...")
    
    word_regex = re.compile(r"\b\w+(?:['\-]\w+)*\b")
    script_words = len(word_regex.findall(script_content))
    
    subtitle_words = []
    vtt_lines = vtt_content.splitlines()
    for line in vtt_lines:
        line = line.strip()
        if not line or line.startswith('WEBVTT') or re.match(r'^\d+$', line) or '-->' in line:
            continue
        # SOTA Logic: Handle hyphenated words and multiple words per segment
        line_words = word_regex.findall(line)
        subtitle_words.extend(line_words)
    vtt_words = len(subtitle_words)
    
    diff = abs(script_words - vtt_words)
    tolerance = script_words * 0.15
    print(f"  Script Words: {script_words}")
    print(f"  VTT Words: {vtt_words}")
    print(f"  Diff: {diff} (Tolerance: {tolerance:.1f})")
    
    if diff <= tolerance:
        print("  [OK] Telemetry Accuracy Verified.")
    else:
        print("  [FAIL] Telemetry Accuracy Failed.")

def test_duration_truncation_logic(script_content, target_duration):
    print("\nTesting Duration Truncation Logic (ISSUE-004)...")
    words = script_content.split()
    force_limit = int(target_duration * 2.7)
    primary_cutoff = " ".join(words[:force_limit])
    
    last_sentence = re.search(r'.*[.!?]', primary_cutoff)
    if last_sentence:
        truncated = last_sentence.group(0).strip()
    else:
        truncated = primary_cutoff
        
    print(f"  Target: {target_duration}s | Max Words: {force_limit}")
    print(f"  Truncated Length: {len(truncated.split())} words")
    print(f"  Ends with: '{truncated[-20:]}'")
    
    if truncated.endswith(('.', '!', '?')):
        print("  [OK] Clean Sentence Cut Verified.")
    else:
        print("  [WARN] No Sentence Boundary found, raw cut applied.")

if __name__ == "__main__":
    vtt_sample = """WEBVTT

1
00:00:00.000 --> 00:00:02.000
The world-famous red cube is-a-mystery.

2
00:00:02.000 --> 00:00:04.000
It's located in the middle of nowhere!
"""
    script_sample = "The world-famous red cube is-a-mystery. It's located in the middle of nowhere!"
    
    test_whisper_word_count_logic(vtt_sample, script_sample)
    test_duration_truncation_logic("This is a long script. It has many sentences. This sentence should be cut. Too many words here " * 20, 10)
