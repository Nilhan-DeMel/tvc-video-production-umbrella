import re

current_prompt = "Consistent cinematic palette of deep jewel tones. Documentary video. Character 'Elara': Fiery red hair, piercing green eyes. Photorealistic 16:9 cinematic shot. over-the-shoulder shot of Elara holding a large sign that says 'Rebel', wearing a heavy leather coat. ABSOLUTE NEGATIVE PROMPT: No text, no words, no letters, no typography, no watermarks, no distorted objects."

failure_cat = "TEXT"
print("ORIGINAL PROMPT:")
print(current_prompt)

# Simulate ALC
text_patterns = [
    r'\b(?:sign|banner|inscription|scroll|letter|book|title|headline|placard|poster|notice|calligraphy|writing)\b',
    r'\b(?:text|words|letters|typography)\b',
]
for pat in text_patterns:
    current_prompt = re.sub(pat, '', current_prompt, flags=re.IGNORECASE)
current_prompt = current_prompt.replace(
    "ABSOLUTE NEGATIVE PROMPT:",
    "ABSOLUTE NEGATIVE PROMPT: No visible text of any kind, no signage, no readable letters, no writing, no typography,"
)

print("\nALC SURGERY (TEXT):")
print(current_prompt)
