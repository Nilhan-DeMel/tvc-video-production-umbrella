# SOTA API Key Vault Audit (PROMPT#09)

## 1. Vault Locations
*   **System Vault Path**: `D:\AI\API\Secrets\`
*   **App-Local Index**: `D:\AI-Apps-In-Drive\App_Station\Video_production\vault_dump.json`

## 2. Key Files Discovered (System Vault)
*   `1772186455949.json`
*   `1772209608994.json`
*   `1772271161734.json`
*   `anthropic_sota_v1__claude_4_6__sota.json`
*   `dashscope_vault_2026.json`
*   `deepseek_sota_v1_sota.json`
*   `deepseek_vault_2026.json`
*   `imperial_gemini.json`
*   `minimax_sota_v1_sota.json`
*   `openai_sota_1772288453509.json`
*   `runware_sota.json`

## 3. TVC Pipeline Provider Mapping
Based on a comprehensive `grep` of all Python files in the TVC Pipeline repository, only the following two providers are actively loaded via the `get_secret` interface:

1.  **Google Gemini**
    *   *Usage*: LLM orchestrator, metadata extraction, timeline intelligence, image intelligence.
    *   *Identifier*: Loaded via `get_secret("Imperial Gemini")`
    *   *Key Candidates in Vault*: 
        *   `imperial_gemini.json`
        *   `1772209608994.json` (Gemini Dev)
2.  **Runware**
    *   *Usage*: Fast multimodal inference (images).
    *   *Identifier*: Loaded via `get_secret("Runware SOTA")`
    *   *Key Candidates in Vault*:
        *   `runware_sota.json`

*(Note: No hardcoded environment variables or legacy fallbacks such as OPENAI_API_KEY, REPLICATE_API_TOKEN, FIREWORKS_API_KEY, or FAL_KEY are used in the active pipeline codebase.)*
