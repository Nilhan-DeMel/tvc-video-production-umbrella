# TVC Studio Agent: Engineering Overview

> A local-first, multi-stage AI media system that turns a production brief into traceable script, audio, visual, edit, and verification artifacts.

## At a glance

| Area | Implementation |
| --- | --- |
| Product | Desktop studio and orchestration pipeline for TV commercial and short-form video production |
| Core stack | Python, LangGraph, PyQt6, async provider integrations, TTS, image/video tooling |
| Architecture | Typed node contracts around a state graph, artifact stores, provider services, and a desktop control surface |
| Quality strategy | Focused seam tests, deterministic fallbacks, duration checks, output verification, UI smoke tests, and committed visual baselines |
| Canonical code | `Video_production_agent/` |

## Why this project is technically interesting

TVC Studio Agent is not a single prompt wrapped in a UI. It treats media production as a stateful engineering workflow with explicit handoffs, retry boundaries, intermediate artifacts, and a final verification stage.

- **Multi-stage orchestration.** The pipeline separates writing, timing, topic extraction, scene direction, audio, prompt design, image generation, editing, and verification instead of asking one model to do everything.
- **Typed boundaries.** Inputs and outputs for the major nodes are represented by dataclasses in `tvc_nodes/contracts.py`, while external effects are supplied through service interfaces in `tvc_nodes/services.py`.
- **Artifact-first observability.** Runs produce manifests, JSON reports, timing traces, provider-resilience events, active/latest run pointers, and media artifacts that can be inspected after execution.
- **Duration-aware generation.** Script writing and audio generation feed duration gates rather than assuming that word count, narration, and rendered duration will naturally align.
- **Human-operable desktop tooling.** A PyQt6 studio exposes the pipeline as a usable workstation with themes, density modes, run state, diagnostics, and post-production surfaces.
- **Verification is a pipeline stage.** Output existence, timing, subtitles, narration, and render results are checked explicitly instead of treating provider success as product success.

## System shape

```mermaid
flowchart LR
    Brief["Production brief"] --> Harvester["Harvester"]
    Harvester --> Writer["Writer"]
    Writer --> Duration["Duration gate"]
    Duration -->|revise| Writer
    Duration --> Topics["Topic extractor"]
    Topics --> Scene["Scene director"]
    Scene --> Audio["Audio engineer"]
    Audio --> Prompts["Prompt architect"]
    Prompts --> Forge["Visual forge"]
    Forge --> Editor["Lead editor"]
    Editor --> Verifier["Verifier"]
    Verifier --> Output["Video + reports + traces"]
    Output --> Studio["PyQt6 studio"]
```

The orchestration lives in `Video_production_agent/tvc_langgraph_core.py`. The node modules remain independently testable because their contracts and effectful services are separated from graph wiring.

## Guided code tour

Start with these files when reviewing the system:

1. **`Video_production_agent/tvc_langgraph_core.py`**
   State definition, graph wiring, provider resilience, run-scoped artifacts, timing, and pipeline-level control flow.
2. **`Video_production_agent/tvc_nodes/contracts.py`**
   Typed inputs and outputs for the production stages.
3. **`Video_production_agent/tvc_nodes/services.py`**
   Service seams that let tests replace provider and filesystem behavior.
4. **`Video_production_agent/tvc_nodes/`**
   Focused implementations for writing, duration, scene direction, audio, prompt architecture, visual generation, editing, and verification.
5. **`Video_production_agent/ui/`**
   Desktop state, services, design tokens, reusable components, visual regression support, and the main window.
6. **`Video_production_agent/tests/`**
   Tests for node seams, duration behavior, deterministic fallbacks, voice handling, launch contracts, UI state, and verification.
7. **`Video_production_agent/Evidence/ui_golden/`**
   Committed visual baselines across themes, densities, and desktop sizes.

## Engineering decisions worth discussing

### 1. Contracts before orchestration

Each production stage receives a purpose-built input object and returns a state update. This makes ownership visible and reduces the chance that a node silently depends on unrelated graph state.

### 2. Run-scoped artifacts

Artifacts are written beneath a run directory, with active and latest pointers for operator tooling. Optional legacy mirroring preserves compatibility without making the legacy layout authoritative.

### 3. Provider failure is modeled, not hidden

The core records retryable failures, invalid requests, open circuits, sanitized retries, and successful calls. This is more useful than a generic catch-all error when external media services behave differently under load.

### 4. Visual quality has a regression surface

The UI repository includes golden captures at multiple resolutions and display densities. That makes future layout changes comparable against a known baseline instead of relying on memory.

## Verification

From the umbrella root, the supported boundary check is:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_active_app.ps1
```

It performs two important checks:

1. rejects live runtime references to the archived `Video_production/` tree;
2. runs the focused pytest suite under `Video_production_agent/tests`.

The accepted UI benchmark note records a 125-test passing checkpoint and fresh UI smoke/compile evidence. Treat that as evidence for the recorded checkpoint, not as a substitute for rerunning the current branch.

## For coding agents

1. Read the root `README.md` and work only in `Video_production_agent/`.
2. Run `tools/check_live_boundary.py` before and after structural work.
3. Locate the relevant contract, service seam, implementation, and focused test before changing a node.
4. Preserve run-scoped artifact and provider-reporting behavior.
5. Never add credentials or provider responses to source, logs, screenshots, or evidence.
6. Re-run the umbrella verification command before handoff.

## Current boundaries

- `Video_production/` is archived reference code, not a second live implementation.
- Full end-to-end generation depends on local media tools, provider credentials, and external services; the unit/seam suite does not prove provider availability.
- The repository does not currently declare its Python environment in a dependency manifest, so a fresh workstation must reconstruct packages such as PyQt6, LangGraph, and Requests before the complete suite can run.
- Some production paths remain Windows-workstation-oriented. This repository should not be presented as a portable cloud service without path and dependency hardening.
- Audit notes under `Evidence/` describe specific checkpoints. Where an older note conflicts with current code or a fresh run, current code and fresh verification win.

## What this repository demonstrates

This project demonstrates how to engineer an AI workflow as a system: explicit stages, typed contracts, deterministic control points, observable artifacts, human-operable tooling, and verification that goes beyond whether a model returned a response.
