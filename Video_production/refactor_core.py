import os, re

def restrict_and_update_core():
    with open('tvc_langgraph_core.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Imports
    content = content.replace('from google import genai\n', '')
    content = content.replace('from google.genai import types\n', '')
    content = content.replace('import base64\n', '')
    content = 'import base64\n' + content

    # Vault keys
    content = content.replace('RUNWARE_API_KEY = get_secret("key_HGmChvaB")', 'FIREWORKS_API_KEY = get_secret("key_HGmChvaB")')
    
    # Replace runware_generate_image function entirely
    runware_func_pattern = re.compile(r'def runware_generate_image.*?except Exception as e:.*?return False\n+', re.DOTALL)
    
    fireworks_image_func = '''def fireworks_generate_image(prompt: str, width: int = 1920, height: int = 1088, output_path: str = "") -> bool:
    import uuid
    task_uuid = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "image/jpeg"
    }
    payload = {
        "prompt": prompt,
        "aspect_ratio": "16:9",
        "guidance_scale": 3.5,
        "num_inference_steps": 4,
        "output_image_format": "JPG"
    }
    try:
        resp = _requests.post(
            "https://api.fireworks.ai/inference/v1/workflows/accounts/fireworks/models/flux-1-schnell-fp8/text_to_image",
            headers=headers, json=payload, timeout=120
        )
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)
        print(f"    [FIREWORKS IMAGE] Generated image: {output_path}")
        return True
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
             err_msg += f". Response: {e.response.text}"
        print(f"    [FIREWORKS IMAGE] API Error: {err_msg[:250]}")
        return False
'''
    content = runware_func_pattern.sub(fireworks_image_func, content)

    # Add fireworks LLM
    fireworks_chat_func = '''
class DummyRes:
    def __init__(self, text):
        self.text = text

def fireworks_chat_completion(model, contents, config=None, api_key=None, **kwargs):
    if api_key is None:
        api_key = FIREWORKS_API_KEY
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    messages = []
    sys_instruction = None
    
    if config and hasattr(config, 'system_instruction') and config.system_instruction:
        sys_instruction = config.system_instruction
    
    if isinstance(contents, str):
        if sys_instruction:
            messages.append({"role": "system", "content": sys_instruction})
        messages.append({"role": "user", "content": contents})
    elif isinstance(contents, list):
        content_arr = []
        for part in contents:
            if isinstance(part, str):
                content_arr.append({"type": "text", "text": part})
            elif hasattr(part, 'inline_data') or hasattr(part, 'data'):
                data = part.inline_data.data if hasattr(part, 'inline_data') else part.data
                b64 = base64.b64encode(data).decode('utf-8')
                content_arr.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
        if sys_instruction:
            messages.append({"role": "system", "content": sys_instruction})
        messages.append({"role": "user", "content": content_arr})

    payload = {
        "model": "accounts/fireworks/models/kimi-k2p5",
        "messages": messages,
        "max_tokens": 4000
    }
    
    resp = _requests.post("https://api.fireworks.ai/inference/v1/chat/completions", headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return DummyRes(data["choices"][0]["message"]["content"])
'''
    if 'FIREWORKS_LLM_INJECTED' not in content:
         content = content.replace('def smart_retry(', fireworks_chat_func + '\n# FIREWORKS_LLM_INJECTED\ndef smart_retry(')
         
    # Removals
    content = re.sub(r'client = genai\.Client\(api_key=state\["api_key"\]\)\n*', '', content)
    content = re.sub(r'client\.models\.generate_content,\s*(?:"gemini_text"|"gemini_image"),\s*model="[^"]+",', 
                     'fireworks_chat_completion, "fireworks_llm",', content)
    content = re.sub(r'client\.models\.generate_content,\s*(?:"gemini_text"|"gemini_image"),', 
                     'fireworks_chat_completion, "fireworks_llm",', content)

    content = content.replace('runware_generate_image', 'fireworks_generate_image')
    content = content.replace('IMAGE_GEN_MODE = "RUNWARE"', 'IMAGE_GEN_MODE = "FIREWORKS"')
    content = content.replace('IMAGE_GEN_MODE == "RUNWARE"', 'IMAGE_GEN_MODE == "FIREWORKS"')

    with open('tvc_langgraph_core.py', 'w', encoding='utf-8') as f:
        f.write(content)

restrict_and_update_core()
print("tvc_langgraph_core.py refactored.")
