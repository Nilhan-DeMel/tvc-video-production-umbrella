# FIREWORKS WIRING PROOF 

## 1. AUTHENTICATION (The Single Key)
- **Key Loaded From**: `tvc_vault.py` -> `get_secret("key_HGmChvaB")`
- **Source**: `vault_dump.json` (Entry `key_HGmChvaB`)
- **Verification**: `test_kimi_smoke.py` passes using this precise key retrieval path.

## 2. LLM TRANSPORT (Kimi K2.5)
- **Endpoint**: `https://api.fireworks.ai/inference/v1/chat/completions`
- **Method**: `POST` via `requests`
- **Payload Structure**: OpenAI-compatible `messages` array.
- **Model ID**: `accounts/fireworks/models/kimi-k2p5`
- **System Instructions**: Correctly mapped to Fireworks' system role.

## 3. IMAGE TRANSPORT (FLUX.1 Schnell)
- **Endpoint**: `https://api.fireworks.ai/inference/v1/workflows/accounts/fireworks/models/flux-1-schnell-fp8/text_to_image`
- **Method**: `POST` via `requests`
- **Key Location**: `Authorization: Bearer <key>` header (Surgical).
- **Parameters**: `prompt`, `width` (1920), `height` (1088), `aspect_ratio` (16:9).
- **Output**: JSON payload -> base64 decode -> disk write (Verified).

## 4. MULTIMODAL QA (Vision Director)
- **Transport**: `fireworks_chat_completion` (utility mode).
- **Input**: Image bytes encoded as Part data.
- **Scoring**: Art Director rubric preserved exactly.
- **Adaptation**: Used Fireworks' multimodal support for visual inspection.
