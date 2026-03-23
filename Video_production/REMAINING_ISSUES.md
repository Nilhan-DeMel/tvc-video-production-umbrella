# REMAINING ISSUES: TVC Video Production Pipeline

## SUMMARY
| Priority | Total | Correctness | Reliability | Devex | Security |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BLOCKER** | 1 | 0 | 1 | 0 | 0 |
| **HIGH** | 2 | 1 | 1 | 0 | 0 |
| **MEDIUM** | 3 | 1 | 1 | 1 | 0 |
| **LOW** | 2 | 0 | 1 | 1 | 0 |
| **TOTAL** | **8** | **2** | **5** | **1** | **0** |

---

## ISSUE REGISTER

| ID | Severity | Category | Symptom / Impact | Repro Steps | Location |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ISSUE-001** | **HIGH** | **Devex** | **Absolute Path Proliferation**: Hardcoded `D:\AI-Apps-In-Drive` paths across 20+ files make the repo non-portable. | `rg "D:\" .` | Multiple Files |
| **ISSUE-002** | **BLOCKER** | **Reliability** | **Harvester Hang**: `yt-dlp` hangs indefinitely on certain queries (e.g. "red cube") due to interactive block. | `python run_test.py "red cube" out.mp4` | `tvc_langgraph_core.py` |
| **ISSUE-003** | **MEDIUM** | **Reliability** | **Pytest Collection Failure**: `pytest` fails with error during collection, preventing automated testing. | `pytest` | Root |
| **ISSUE-004** | **MEDIUM** | **Correctness** | **Brittle Duration Gates**: Force-truncation logic at line 482 of core leads to cut-off audio/video. | Inspect `tvc_langgraph_core.py:482` | `tvc_langgraph_core.py` |
| **ISSUE-005** | **LOW** | **Maintainability** | **Fragmented Config**: `PROJECT_DIR` redefined locally in every script. | `rg "PROJECT_DIR =" .` | Global |
| **ISSUE-006** | **LOW** | **UX** | **Telemetry Noise**: Audio Engineer outputs thousands of "SentenceBoundary" lines without summary. | Run any pipeline with VO | `tvc_langgraph_core.py` |
| **ISSUE-007** | **MEDIUM** | **Reliability** | **Telemetry Defect**: `whisper_verifier` miscalculates word counts (280 vs 159). | Run `whisper_verifier` tests | `tvc_langgraph_core.py` |
| **ISSUE-008** | **HIGH** | **Reliability** | **Asynchronous Status Leak**: `MODE_VOICE` and `MODE_ORCHESTRATE` return `null` output while "bifrost_dispatched". | Run `supreme_commander.py` in Voice mode | `supreme_commander.py` |

---

## VERIFICATION ARTIFACTS
- `ISSUE_MARKERS.txt`: Static scan results.
- `HARDCODED_PATHS.txt`: Path audit.
- `pipeline_run.log`: Runtime failure patterns.
- `repro_test.log`: Output of the "red cube" hang test.
