# COVERAGE LIMITS & UNVERIFIED RISKS

The following areas were NOT verified in this audit due to the following environmental and technical limits:

## 1. Git History Audit
- **Limit**: Workspace is not a Git repository.
- **Impact**: Unable to provide `git log -S` or `git grep` proof of historical purge.
- **Risk**: If this folder was ever a git repo in a parent directory, the key might still exist in the `.git/` history of that parent.

## 2. Downstream Hardware & API Stress
- **Limit**: Pipeline was tested with a short 10s-120s prompt but remains buggy (Harvester/Telemetry).
- **Unverified**: 
  - **Veo 3.1 Rate Limits**: Not tested under sustained load.
  - **Runware Socket Stability**: Not verified.
  - **Memory Leaks**: The image upscaler and NLE rendering buffers were not stress-tested.

## 3. Deployment Scaling
- **Limit**: Hardcoded absolute paths (`D:\AI-Apps-In-Drive\...`) still exist in several source files.
- **Impact**: The system is likely to fail if deployed to a Cloud Run or Linux-based container without path re-mapping.
