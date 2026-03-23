# Before/After Provider Map: SOTA Migration

| Component | OLD Provider (Legacy) | NEW Provider (Fireworks) | Change Type |
| :--- | :--- | :--- | :--- |
| **LLM / Reasoning** | Google GenAI (Gemini) | Fireworks AI (Kimi K2.5) | Transport Layer |
| **Image Generation** | Runware / Gemini Preview | Fireworks AI (Flux.1) | Transport Layer |
| **Authentication** | `GEMINI_BRAIN` / `RUNWARE` | `FIREWORKS_API_KEY` | Key Consolidation |
| **Transport Lib** | `google.generativeai` | `requests` (Raw HTTP) | Dependency Swap |
| **JSON Handling** | Manual `json.loads` | `sota_json_repair` | Robustness Upgrade |

**Truth Standard: PROVED**
- Verified via `tvc_langgraph_core.py` imports.
- Verified via `tvc_vault.py` secret loader logic.
