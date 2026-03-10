import re

with open('tvc_langgraph_core.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix overly indented `res = smart_retry(`
text = re.sub(r'([ \t]+)res = smart_retry\(', r'        res = smart_retry(', text)
text = re.sub(r'([ \t]+)cpp_res = smart_retry\(', r'        cpp_res = smart_retry(', text)
text = re.sub(r'([ \t]+)generation_success = smart_retry\(', r'        generation_success = smart_retry(', text)
text = re.sub(r'([ \t]+)qa_res = smart_retry\(', r'                qa_res = smart_retry(', text) # inside Visual QA, try block is 12, res is 16

# Re-align the arguments inside smart_retry:
text = re.sub(r'\n[ \t]*fireworks_chat_completion, "fireworks_llm",', r'\n            fireworks_chat_completion, "fireworks_llm",', text)

with open('tvc_langgraph_core.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Indentation fixed.")
