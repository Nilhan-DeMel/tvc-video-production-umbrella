# OUTSTANDING BUG REGISTER

| BUG-ID | Title | Status | Severity | Blocking Release? |
| :--- | :--- | :--- | :--- | :--- |
| BUG-001 | Hardcoded Imperial API Key | CONFIRMED | Critical | Yes |
| BUG-002 | Telemetry Word Count Mismatch | CONFIRMED | High | No |
| BUG-003 | Harvester Indefinite Hang | CONFIRMED | High | Yes |
| BUG-004 | Hardcoded Local File Paths | SUSPECTED | Medium | No |

---

### BUG-001: Hardcoded Imperial API Key
- **Status**: CONFIRMED
- **Severity**: Critical
- **User impact**: Security vulnerability; potential for API quota theft.
- **Repro steps**: Inspect `supreme_commander.py` line 42.
- **Expected**: API keys should be loaded from environment variables or a secure vault.
- **Actual**: `IMPERIAL_API_KEY = "AIzaSy..."` is hardcoded.
- **Evidence**: [supreme_commander.py](file:///d:/AI-Apps-In-Drive/App_Station/Video_production/supreme_commander.py#L42)
- **Smallest next fix**: Replace with `os.getenv("IMPERIAL_API_KEY")`.

### BUG-002: Telemetry Word Count Mismatch
- **Status**: CONFIRMED
- **Severity**: High
- **User impact**: Verification reports show failures (Word count drift) even when video is correct.
- **Repro**: Inspect `verification_report.json` after a successful run.
- **Actual**: `script_words: 159`, `vtt_words: 280`.
- **Likely root cause**: Regex in `whisper_verifier` failing to filter header/noisy lines in VTT or `audio_engineer` duplicating boundaries.
- **Evidence**: [verification_report.json](file:///d:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/verification_report.json)

### BUG-003: Harvester Indefinite Hang
- **Status**: CONFIRMED
- **Severity**: High
- **User impact**: Pipeline stops and never finishes.
- **Repro**: Run `run_test.py` with generic prompts like "red cube".
- **Actual**: Command hangs at `yt-dlp` stage.
- **Likely root cause**: Subprocess call missing timeout.
- **Evidence**: [pipeline_run.log](file:///d:/AI-Apps-In-Drive/App_Station/Video_production/tvc_multi_agent_db/pipeline_run.log) shows it stuck at Harvester.
