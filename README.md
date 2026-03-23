# TVC Umbrella Repo

This repo has exactly two product folders:

- `Video_production_agent/` - the canonical live TVC app
- `Video_production/` - archived reference code only

## Rules

- Launch, test, and edit the live app only from `Video_production_agent/`.
- Do not point shortcuts, launchers, CI, or operator docs at `Video_production/`.
- Keep `Video_production/` browseable for reference, but treat it as read-only historical context.

## Verification

From the umbrella root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_active_app.ps1
```

That command:

- checks the live subtree for forbidden runtime references to `Video_production/`
- runs the active app test suite from `Video_production_agent/tests`

## Working Directory

Day-to-day app work should happen in:

`D:\AI-Apps-In-Drive\App_Station\tvc_umbrella_repo\Video_production_agent`

## Workspace Launch

To create a desktop entry that opens the canonical TVC folder and launches Codex:

```powershell
python .\tools\create_tvc_codex_workspace_shortcut.py
```

That creates `TVC Codex Workspace.lnk` on the desktop and keeps the operator flow pointed at this umbrella repo instead of the older `Skills` workspace.

To refresh all canonical TVC desktop shortcuts from the umbrella repo:

```powershell
python .\tools\refresh_tvc_desktop_shortcuts.py
```

That rewrites:

- `TVC Codex Workspace.lnk`
- `TVC Studio Agent.lnk`
- `TVC Emperor.lnk`
