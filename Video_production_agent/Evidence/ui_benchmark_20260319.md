# UI Benchmark 2026-03-19

- Benchmark branch: `codex/studio-benchmark-2026-03-19`
- Benchmark intent: accepted good UI baseline before the next UI polish branch
- Primary evidence folder: `Evidence/ui_golden/20260319_123002_studio_benchmark`
- Primary accepted state: Narrate screen after live-geometry repair
- Themes/densities captured:
  - Narrate: `aurora_graphite` and `obsidian_contrast`, `cozy` and `compact`
  - Sizes: `1366x768`, `1600x900`, `1920x1080`, `2560x1440`
- Full-workspace captures included at `1920x1080` for `aurora_graphite/cozy`

## Verification

- Fresh benchmark capture generation completed successfully on this branch.
- Fresh branch-local UI smoke check completed successfully:
  - offscreen Narrate launch
  - `layout_mode='stacked-tight'` at `1366x768`
  - `progress='100.0%'`
  - `node='Verifier'`
- Code-validation baseline for this checkpointed code state:
  - `python -m pytest -q`
  - Result before benchmark-only evidence additions: `125 passed in 59.86s`
- Post-capture broad pytest reruns timed out locally and were not used as pass evidence for this note.
- Fresh compile verification completed successfully for:
  - `ui/components.py`
  - `ui/main_window.py`
  - `ui/services.py`
  - `ui/state.py`
  - `ui/tokens.py`
  - `tvc_studio_agent_ui.py`

## Benchmark Read

This checkpoint marks the point where the UI moved from unstable/overlapping to acceptable for continued polish. The accepted qualities in this baseline are:

- stable Narrate geometry under live-stress layouts
- responsive stacking instead of overlap
- committed visual evidence for future comparison
- preserved Control Room visual direction

## Next Branch Intent

Use the next branch for further UI polish without mutating this benchmark baseline directly:

- `codex/ui-polish-next`
