import re

with open('tvc_langgraph_core.py', 'r', encoding='utf-8') as f:
    text = f.read()

dummy_types_code = '''
class DummyTypes:
    class GenerateContentConfig:
        def __init__(self, system_instruction=None, temperature=None, response_mime_type=None, response_schema=None):
            self.system_instruction = system_instruction
            self.temperature = temperature
            self.response_mime_type = response_mime_type
            self.response_schema = response_schema
types = DummyTypes()
'''

if 'class DummyTypes:' not in text:
    text = text.replace('import base64', 'import base64\n' + dummy_types_code)

# To fix indentation, we will hunt for lines defining `res = smart_retry` and indent them to 8 spaces, EXCEPT qa_res which is inside an inner try block (16 spaces usually)
lines = text.split('\n')
for i, line in enumerate(lines):
    stripped = line.lstrip()
    if stripped.startswith('res = smart_retry(') or stripped.startswith('cpp_res = smart_retry(') or stripped.startswith('generation_success = smart_retry('):
        lines[i] = '        ' + stripped
    elif stripped.startswith('qa_res = smart_retry('):
        lines[i] = '                ' + stripped
    
    # Also fix the closing parenthesis for smart_retry which might be hanging
    if stripped == ')' and i > 0 and 'contents=' in lines[i-1]:
        # just guess 8
        lines[i] = '        )'

with open('tvc_langgraph_core.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print("Structure repaired.")
