# CONTEXT MAP: Security Sweep (TVC)

- **Goal**: 100% elimination of hardcoded secrets from the TVC pipeline.
- **Definition of Done**: 
    - No plaintext secrets in source code.
    - All secrets loaded via `tvc_vault.py`.
    - Proved via Repo-wide Grep and Runtime Validation.
    - Evidence Pack (PROMPT#04.zip) delivered.
- **Constraints**: 
    - Do not print full secrets in any evidence.
    - Redact as `first 4 ... last 4`.
    - Windows environment.
- **Current State**: Phase 1 (Discovery) complete. CONFIRMED hardcoded key in `tvc_langgraph_core.py`.
- **Risks**: 
    - Brittle path dependencies in secondary scripts.
    - Potential for secrets in VTT/Log history (will audit).
