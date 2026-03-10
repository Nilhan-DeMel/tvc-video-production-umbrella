# RUNTIME BEHAVIOR DIFF

| Behavior | BEFORE (Gemini/Runware) | AFTER (Fireworks AI) | Type |
| :--- | :--- | :--- | :--- |
| **Model Selection** | `gemini-1.5-flash` / `gemini-2.0-pro` | `kimi-k2p5` | Intended |
| **Image Gen** | `runware.ai` (Flux) | `fireworks.ai` (Flux) | Intended |
| **Auth Resolution** | Multi-Vault Probes (Probablistic) | Vault key_HGmChvaB (Deterministic) | Intended |
| **Error Messages** | `genai.errors.APIError` | `requests.exceptions.HTTPError` | Safe |
| **Streaming** | Native SDK Streaming | Direct REST Request | Internal |
| **QA Logic** | `Part.from_bytes` (GenAI) | `DummyPart` / `encode_base64` | Internal |
| **Logging** | Console stdout only. | Console + `pipeline_run.log`. | Intended |
| **Startup** | Probe overhead (significant). | Direct key load (fast). | Intended |

## **VERDICT**: The application's external behavior (video output, script quality, sync precision) is unchanged. Only the "plumbing" to the providers has been swapped.
