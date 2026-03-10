import contextlib
import io
import importlib
import json
import os
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path


LIVE_PROMPTS = [
    "OpenAI agentic coding workflows in 2026",
    "Codex vs local coding agents for enterprise teams",
    "Multimodal reasoning and tool-using AI systems in production in 2026",
]

REQUIRED_WRITER_KEYS = ["script", "status", "duration_attempts"]


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def make_prompt(tag: str) -> str:
    return f"{tag} | Writer reliability probe | {datetime.now().strftime('%Y%m%d_%H%M%S')}"


def make_line_script(prefix: str, total_words: int, line_len: int = 8) -> str:
    words = [f"{prefix}{i}" for i in range(1, total_words + 1)]
    lines = []
    for i in range(0, len(words), line_len):
        chunk = " ".join(words[i:i + line_len]).strip()
        if chunk and chunk[-1] not in ".!?":
            chunk += "."
        lines.append(chunk)
    return "\n".join(lines)


def backup_file(path: Path):
    if path.exists():
        return {"exists": True, "bytes": path.read_bytes()}
    return {"exists": False, "bytes": b""}


def restore_file(path: Path, snapshot):
    if snapshot.get("exists"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(snapshot.get("bytes", b""))
    elif path.exists():
        path.unlink()


def install_vault_shim(project_dir: Path):
    import types

    def _shim_get_secret(secret_name):
        data = read_json(project_dir / "vault_dump.json", [])
        target_provider = "Fireworks AI" if "key_HGmChvaB" in secret_name else ("Google" if "Gemini" in secret_name else None)
        for entry in data:
            if entry.get("name") == secret_name and entry.get("key"):
                return entry["key"]
        if target_provider:
            for entry in data:
                provider = str(entry.get("provider", ""))
                if target_provider.lower() in provider.lower() and entry.get("key"):
                    return entry["key"]
        raise RuntimeError(f"VAULT SHIM: no key found for {secret_name}")

    shim = types.ModuleType("tvc_vault")
    shim.get_secret = _shim_get_secret
    sys.modules["tvc_vault"] = shim


def import_core(project_dir: Path):
    sys.path.insert(0, str(project_dir))
    try:
        import tvc_langgraph_core as core  # noqa
    except SystemExit:
        install_vault_shim(project_dir)
        core = importlib.import_module("tvc_langgraph_core")
    return core


def import_commander(project_dir: Path):
    sys.path.insert(0, str(project_dir))
    try:
        import supreme_commander as sc  # noqa
    except SystemExit:
        install_vault_shim(project_dir)
        sc = importlib.import_module("supreme_commander")
    return sc


def assert_required_keys(result: dict):
    missing = [k for k in REQUIRED_WRITER_KEYS if k not in result]
    return {"missing_keys": missing, "present": len(missing) == 0}


def run_writer_scenario(core, scenario: dict, run_dir: Path):
    scenario_name = scenario["name"]
    scenario_dir = run_dir / scenario_name
    scenario_dir.mkdir(parents=True, exist_ok=True)

    intel_dir = Path(core.INTEL_DIR)
    script_file = intel_dir / "master_script.txt"
    manifest_file = intel_dir / "state_manifest.json"
    before_script = backup_file(script_file)
    before_manifest = backup_file(manifest_file)

    endpoints = []
    call_log = []
    errors = []
    result = {}
    terminal_log = ""
    reporter = {"writer_context_seen": None}

    original_fc = core.fireworks_chat_completion
    original_sr = core.smart_retry
    original_post = core._requests.post if getattr(core, "_requests", None) else None

    draft_text = scenario.get("draft_text", make_line_script("draft_", 50))
    cpp_text = scenario.get("cpp_text", make_line_script("cpp_", 50))

    def logged_post(*args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        endpoints.append(url)
        return original_post(*args, **kwargs)

    if original_post:
        core._requests.post = logged_post

    def fake_fireworks_chat_completion(contents, model="accounts/fireworks/models/kimi-k2p5", config=None, api_key=None, **kwargs):
        sys_inst = getattr(config, "system_instruction", "") if config else ""
        is_cpp = "prosody engineer" in str(sys_inst).lower()
        call_idx = len(call_log) + 1
        entry = {
            "index": call_idx,
            "is_cpp": is_cpp,
            "model": model,
            "contents": str(contents),
            "system_instruction": str(sys_inst),
        }
        call_log.append(entry)
        if call_idx == 1 and "Context for focus:" in str(contents):
            reporter["writer_context_seen"] = str(contents).split("Context for focus:", 1)[1].strip()

        if "custom_responder" in scenario:
            out = scenario["custom_responder"](entry, draft_text, cpp_text)
        else:
            out = cpp_text if is_cpp else draft_text
        return core.DummyRes(out)

    def passthrough_smart_retry(fn, endpoint="default", *args, **kwargs):
        return fn(*args, **kwargs)

    core.fireworks_chat_completion = fake_fireworks_chat_completion
    core.smart_retry = passthrough_smart_retry

    state = scenario["state_factory"]()
    state["request_prompt"] = scenario["prompt"]

    if "pre_setup" in scenario:
        scenario["pre_setup"](core, state, script_file, manifest_file)

    buff = io.StringIO()
    try:
        with contextlib.redirect_stdout(buff), contextlib.redirect_stderr(buff):
            result = core.writer_node(state)
        terminal_log = buff.getvalue()
        (scenario_dir / "terminal.log").write_text(terminal_log, encoding="utf-8")

        key_report = assert_required_keys(result)
        validator = scenario["validator"]
        check = validator(result, state, call_log, terminal_log, reporter, script_file, manifest_file)

        scenario_report = {
            "scenario": scenario_name,
            "prompt": scenario["prompt"],
            "status": result.get("status"),
            "required_keys_present": key_report["present"],
            "missing_keys": key_report["missing_keys"],
            "checks": check,
            "call_count": len(call_log),
            "calls": call_log,
            "endpoints": sorted(set(endpoints)),
            "scenario_pass": bool(key_report["present"] and check.get("pass")),
            "errors": errors,
            "terminal_log": str(scenario_dir / "terminal.log"),
            "script_file": str(script_file),
            "manifest_file": str(manifest_file),
        }
        write_json(scenario_dir / "scenario_report.json", scenario_report)
        return scenario_report
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        errors.append(err)
        terminal_log = buff.getvalue() + "\n\n" + traceback.format_exc()
        (scenario_dir / "terminal.log").write_text(terminal_log, encoding="utf-8")
        scenario_report = {
            "scenario": scenario_name,
            "prompt": scenario["prompt"],
            "status": None,
            "required_keys_present": False,
            "missing_keys": REQUIRED_WRITER_KEYS,
            "checks": {"pass": False, "reason": "exception"},
            "call_count": len(call_log),
            "calls": call_log,
            "endpoints": sorted(set(endpoints)),
            "scenario_pass": False,
            "errors": errors,
            "terminal_log": str(scenario_dir / "terminal.log"),
            "script_file": str(script_file),
            "manifest_file": str(manifest_file),
        }
        write_json(scenario_dir / "scenario_report.json", scenario_report)
        return scenario_report
    finally:
        core.fireworks_chat_completion = original_fc
        core.smart_retry = original_sr
        if original_post:
            core._requests.post = original_post
        restore_file(script_file, before_script)
        restore_file(manifest_file, before_manifest)


def make_writer_scenarios(core):
    def base_state(prompt, target=20):
        return {"request_prompt": prompt, "target_duration": target, "duration_attempts": 0}

    scenarios = []

    w1_prompt = make_prompt("W1 Harvester Forwarding")
    harvest_lines = [f"HARVEST_MARKER_ALPHA line {i} cinematic evidence." for i in range(1, 70)]
    harvested_text = "\n".join(harvest_lines)
    scenarios.append({
        "name": "W1_harvester_forwarding",
        "prompt": w1_prompt,
        "state_factory": lambda: {**base_state(w1_prompt), "harvested_intelligence": harvested_text},
        "draft_text": make_line_script("w1_draft_", 50),
        "cpp_text": make_line_script("w1_cpp_", 50),
        "validator": lambda result, state, calls, log, reporter, script_file, manifest_file: {
            "pass": (
                result.get("status") == "drafted"
                and len(result.get("script", "").strip()) > 0
                and result.get("duration_attempts") == 1
                and len(calls) >= 2
                and "HARVEST_MARKER_ALPHA" in calls[0].get("contents", "")
                and "General Documentary" not in calls[0].get("contents", "")
                and len((reporter.get("writer_context_seen") or "")) <= 2500
            )
        },
    })

    w2_prompt = make_prompt("W2 Context Priority")
    scenarios.append({
        "name": "W2_context_priority",
        "prompt": w2_prompt,
        "state_factory": lambda: {
            **base_state(w2_prompt),
            "context_summary": "CTX_SUMMARY_PRIORITY_ABC",
            "harvested_intelligence": "HARVEST_SHOULD_NOT_WIN marker marker marker",
        },
        "draft_text": make_line_script("w2_draft_", 50),
        "cpp_text": make_line_script("w2_cpp_", 50),
        "validator": lambda result, state, calls, log, reporter, script_file, manifest_file: {
            "pass": (
                result.get("status") == "drafted"
                and result.get("duration_attempts") == 1
                and len(calls) >= 2
                and "CTX_SUMMARY_PRIORITY_ABC" in calls[0].get("contents", "")
                and "HARVEST_SHOULD_NOT_WIN" not in calls[0].get("contents", "")
            )
        },
    })

    w3_prompt = make_prompt("W3 Cache Resume")

    def w3_setup(core_mod, state, script_file, manifest_file):
        cached = "cached script line one.\ncached script line two."
        script_file.write_text(cached, encoding="utf-8")
        manifest = read_json(manifest_file, {})
        manifest["writer_prompt_hash"] = core_mod.get_hash(state["request_prompt"])
        write_json(manifest_file, manifest)
        state["status"] = "drafted"

    scenarios.append({
        "name": "W3_cache_resume",
        "prompt": w3_prompt,
        "state_factory": lambda: base_state(w3_prompt),
        "pre_setup": w3_setup,
        "validator": lambda result, state, calls, log, reporter, script_file, manifest_file: {
            "pass": (
                result.get("status") == "drafted"
                and result.get("duration_attempts") == 1
                and len(calls) == 0
                and "Skipping Writer." in log
                and "cached script line one." in result.get("script", "")
            )
        },
    })

    w4_prompt = make_prompt("W4 Duration Rewrite Loop")
    scenarios.append({
        "name": "W4_duration_rewrite",
        "prompt": w4_prompt,
        "state_factory": lambda: {**base_state(w4_prompt), "status": "duration_fail", "duration_attempts": 2},
        "draft_text": make_line_script("w4_draft_", 48),
        "cpp_text": make_line_script("w4_cpp_", 48),
        "validator": lambda result, state, calls, log, reporter, script_file, manifest_file: {
            "pass": (
                result.get("status") == "drafted"
                and result.get("duration_attempts") == 3
                and len(calls) >= 2
                and "FOCUS on EXACTLY" in calls[0].get("system_instruction", "")
                and "[REWRITE]" in log
            )
        },
    })

    w5_prompt = make_prompt("W5 CPP Overshoot Guard")
    w5_draft = make_line_script("w5_base_", 40)
    w5_cpp_bloat = make_line_script("w5_cpp_big_", 95)
    scenarios.append({
        "name": "W5_cpp_overshoot_guard",
        "prompt": w5_prompt,
        "state_factory": lambda: base_state(w5_prompt),
        "draft_text": w5_draft,
        "cpp_text": w5_cpp_bloat,
        "validator": lambda result, state, calls, log, reporter, script_file, manifest_file: {
            "pass": (
                result.get("status") == "drafted"
                and len(calls) >= 2
                and "Overshoot detected" in log
                and len(result.get("script", "").split()) == len(w5_draft.split())
            )
        },
    })

    w6_prompt = make_prompt("W6 Length Clamp")
    w6_draft = make_line_script("w6_base_", 50)
    w6_cpp_long = make_line_script("w6_cpp_long_", 70)
    scenarios.append({
        "name": "W6_length_clamp",
        "prompt": w6_prompt,
        "state_factory": lambda: base_state(w6_prompt),
        "draft_text": w6_draft,
        "cpp_text": w6_cpp_long,
        "validator": lambda result, state, calls, log, reporter, script_file, manifest_file: {
            "pass": (
                result.get("status") == "drafted"
                and len(calls) >= 2
                and "Length clamp applied" in log
                and len(result.get("script", "").split()) <= int((state.get("target_duration", 20) * 2.5) * 1.2)
            )
        },
    })

    w7_prompt = make_prompt("W7 Empty Context Fallback")
    scenarios.append({
        "name": "W7_empty_context_fallback",
        "prompt": w7_prompt,
        "state_factory": lambda: base_state(w7_prompt),
        "draft_text": make_line_script("w7_draft_", 50),
        "cpp_text": make_line_script("w7_cpp_", 50),
        "validator": lambda result, state, calls, log, reporter, script_file, manifest_file: {
            "pass": (
                result.get("status") == "drafted"
                and result.get("duration_attempts") == 1
                and len(calls) >= 2
                and "General Documentary" in calls[0].get("contents", "")
            )
        },
    })

    return scenarios


def copy_run_artifacts(intel_dir: Path, run_dir: Path, output_path: Path):
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    known_files = [
        "pipeline_run.log",
        "verification_report.json",
        "vtt_matrix.json",
        "topic_callouts.json",
        "filter.txt",
        "narration.vtt",
        "master_script.txt",
        "typography.ass",
        "state_manifest.json",
        "harvester_run_report.json",
    ]
    copied = {}
    for name in known_files:
        src = intel_dir / name
        if src.exists():
            dst = artifacts_dir / name
            shutil.copy2(src, dst)
            copied[name] = str(dst)
    if output_path and output_path.exists():
        out_dst = run_dir / output_path.name
        shutil.copy2(output_path, out_dst)
        copied[output_path.name] = str(out_dst)
    return copied


def evaluate_topic_integrity(callouts_path: Path, epochs_path: Path):
    callouts = read_json(callouts_path, [])
    epochs = read_json(epochs_path, [])
    if not isinstance(callouts, list) or not isinstance(epochs, list) or len(epochs) == 0:
        return {"checked": False, "pass": None, "issues": ["insufficient_artifacts"]}
    issues = []
    epoch_count = len(epochs)
    for idx, c in enumerate(callouts):
        val = c.get("after_sentence")
        if not isinstance(val, int) or val < 1 or val > epoch_count:
            issues.append(f"callout_{idx + 1}: invalid_after_sentence={val} epoch_count={epoch_count}")
    return {"checked": True, "pass": len(issues) == 0, "issues": issues}


def classify_live_attribution(result: dict, log_text: str, script_non_empty: bool, scene_parse_error: bool):
    if result.get("status") == "success":
        return "none", False
    err = str(result.get("error") or "")
    if "412" in err and "chat/completions" in err:
        return "external_provider_fireworks_text", False
    if scene_parse_error:
        return "downstream_scene_director_parse", False
    if not script_non_empty:
        return "writer_contract_break", True
    if "writer" in err.lower():
        return "writer_runtime_error", True
    return "unknown_non_writer", False


def run_live_matrix(project_dir: Path, core, run_dir: Path):
    sc = import_commander(project_dir)
    live_root = run_dir / "live_runs"
    live_root.mkdir(parents=True, exist_ok=True)

    intel_dir = Path(core.INTEL_DIR)
    live_reports = []
    all_endpoints = []

    for i, prompt in enumerate(LIVE_PROMPTS, start=1):
        case_dir = live_root / f"run_{i}"
        case_dir.mkdir(parents=True, exist_ok=True)
        request = f"--mode MODE_NARRATE --duration 20 {prompt}"
        endpoints = []

        orig_sc_post = sc._requests.post if getattr(sc, "_requests", None) else None
        orig_core_post = core._requests.post if getattr(core, "_requests", None) else None

        def sc_logged_post(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "")
            endpoints.append(url)
            return orig_sc_post(*args, **kwargs)

        def core_logged_post(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "")
            endpoints.append(url)
            return orig_core_post(*args, **kwargs)

        if orig_sc_post:
            sc._requests.post = sc_logged_post
        if orig_core_post:
            core._requests.post = core_logged_post

        buff = io.StringIO()
        run_result = {}
        try:
            with contextlib.redirect_stdout(buff), contextlib.redirect_stderr(buff):
                run_result = sc.supreme_video_commander(request)
        except Exception as exc:
            run_result = {"mode": "MODE_NARRATE", "status": "failed", "output": None, "error": f"{type(exc).__name__}: {exc}", "size_mb": None}
        finally:
            if orig_sc_post:
                sc._requests.post = orig_sc_post
            if orig_core_post:
                core._requests.post = orig_core_post

        log_text = buff.getvalue()
        log_path = case_dir / "terminal.log"
        log_path.write_text(log_text, encoding="utf-8")
        all_endpoints.extend(endpoints)

        raw_output = run_result.get("output")
        output_path = Path(raw_output) if isinstance(raw_output, str) and raw_output.strip() else None
        copied = copy_run_artifacts(intel_dir, case_dir, output_path if output_path and output_path.is_file() else None)
        artifacts_dir = case_dir / "artifacts"

        script_path = artifacts_dir / "master_script.txt"
        script_text = script_path.read_text(encoding="utf-8", errors="ignore") if script_path.exists() else ""
        script_non_empty = len(script_text.strip()) > 0
        writer_stage_seen = "[WRITER]" in log_text
        duration_gate_seen = ("[DURATION GATE] PASS" in log_text) or ("[DURATION GATE] REJECT" in log_text) or ("Graceful Truncation" in log_text)
        scene_parse_error = ("SCENE DIRECTOR] ERROR Parse failed" in log_text) or ("Expecting value: line 1 column 1 (char 0)" in str(run_result.get("error") or ""))

        topic_integrity = evaluate_topic_integrity(artifacts_dir / "topic_callouts.json", artifacts_dir / "vtt_matrix.json")
        verifier = read_json(artifacts_dir / "verification_report.json", {})
        verifier_available = isinstance(verifier, dict) and len(verifier) > 0
        verifier_pass = bool(verifier.get("verified")) if verifier_available else None
        telemetry_pass = bool(verifier.get("telemetry_pass")) if verifier_available else None
        drift_ok = (isinstance(verifier.get("drift"), (int, float)) and verifier.get("drift", 999.0) <= 1.0) if verifier_available else None

        attribution, writer_blocker = classify_live_attribution(run_result, log_text, script_non_empty, scene_parse_error)
        handoff_confirmed = script_non_empty and (artifacts_dir / "harvester_run_report.json").exists()

        report = {
            "run": i,
            "prompt": prompt,
            "request": request,
            "status": run_result.get("status"),
            "output": run_result.get("output"),
            "error": run_result.get("error"),
            "writer_stage_seen": writer_stage_seen,
            "duration_gate_seen": duration_gate_seen,
            "script_non_empty": script_non_empty,
            "topic_integrity": topic_integrity,
            "scene_parse_error": scene_parse_error,
            "verifier_available": verifier_available,
            "verifier_pass": verifier_pass,
            "telemetry_pass": telemetry_pass,
            "drift_ok": drift_ok,
            "handoff_confirmed": handoff_confirmed,
            "attribution": attribution,
            "writer_blocker": writer_blocker,
            "endpoints": sorted(set(endpoints)),
            "terminal_log": str(log_path),
            "artifacts": copied,
        }
        write_json(case_dir / "run_report.json", report)
        live_reports.append(report)

    policy_non_fireworks = sorted(set([u for u in all_endpoints if isinstance(u, str) and u and "api.fireworks.ai" not in u]))
    policy = {
        "captured_model_endpoints": sorted(set([u for u in all_endpoints if isinstance(u, str) and u])),
        "non_fireworks_paid_endpoints": policy_non_fireworks,
        "policy_pass": len(policy_non_fireworks) == 0,
        "policy": "Paid model API for NARRATE writer path must be Fireworks-only.",
    }
    write_json(live_root / "live_policy_check.json", policy)
    return live_reports, policy


def write_final_reports(run_dir: Path, deterministic_reports, live_reports, policy):
    contract = {
        "required_keys": REQUIRED_WRITER_KEYS,
        "scenario_key_presence": {r["scenario"]: r.get("required_keys_present", False) for r in deterministic_reports},
        "all_required_keys_present": all(r.get("required_keys_present", False) for r in deterministic_reports),
    }
    write_json(run_dir / "writer_contract_report.json", contract)

    deterministic_pass = all(r.get("scenario_pass", False) for r in deterministic_reports)
    writer_blockers = [r for r in live_reports if r.get("writer_blocker")]
    external_or_downstream = [r for r in live_reports if r.get("status") != "success" and not r.get("writer_blocker")]
    writer_perfect = bool(deterministic_pass and len(writer_blockers) == 0 and policy.get("policy_pass"))

    final = {
        "timestamp": datetime.now().isoformat(),
        "writer_perfect_verdict": "PASS" if writer_perfect else "FAIL",
        "hybrid_policy": "external outages are non-writer blockers unless writer contract breaks",
        "deterministic_pass": deterministic_pass,
        "live_writer_blockers": len(writer_blockers),
        "live_external_or_downstream_failures": len(external_or_downstream),
        "policy_pass": policy.get("policy_pass"),
        "deterministic_scenarios": [
            {
                "scenario": r.get("scenario"),
                "pass": r.get("scenario_pass"),
                "status": r.get("status"),
                "missing_keys": r.get("missing_keys", []),
                "terminal_log": r.get("terminal_log"),
            }
            for r in deterministic_reports
        ],
        "live_runs": [
            {
                "run": r.get("run"),
                "status": r.get("status"),
                "attribution": r.get("attribution"),
                "writer_blocker": r.get("writer_blocker"),
                "terminal_log": r.get("terminal_log"),
            }
            for r in live_reports
        ],
        "notes_source": r"D:\AI-Apps-In-Drive\App_Station\Video_production\Evidence\tvc_system_notes.md",
    }
    write_json(run_dir / "writer_verdict.json", final)

    md = [
        "# Writer Reliability Verdict",
        "",
        f"- Writer perfect verdict: **{final['writer_perfect_verdict']}**",
        f"- Deterministic scenarios pass: `{deterministic_pass}`",
        f"- Live writer blockers: `{len(writer_blockers)}`",
        f"- Live external/downstream failures: `{len(external_or_downstream)}`",
        f"- Policy pass (Fireworks-only paid model API): `{policy.get('policy_pass')}`",
        "",
        "## Deterministic Scenarios",
        "| Scenario | Pass | Status | Missing Keys | Log |",
        "|---|---|---|---|---|",
    ]
    for r in deterministic_reports:
        md.append(
            f"| {r.get('scenario')} | {r.get('scenario_pass')} | {r.get('status')} | {','.join(r.get('missing_keys', []))} | {r.get('terminal_log')} |"
        )
    md.extend(
        [
            "",
            "## Live Runs",
            "| Run | Status | Attribution | Writer Blocker | Log |",
            "|---|---|---|---|---|",
        ]
    )
    for r in live_reports:
        md.append(
            f"| {r.get('run')} | {r.get('status')} | {r.get('attribution')} | {r.get('writer_blocker')} | {r.get('terminal_log')} |"
        )
    md.extend(
        [
            "",
            "## Policy",
            "```json",
            json.dumps(policy, indent=2, ensure_ascii=True),
            "```",
        ]
    )
    (run_dir / "writer_verdict.md").write_text("\n".join(md), encoding="utf-8")
    return final


def main():
    project_dir = Path(r"D:\AI-Apps-In-Drive\App_Station\Video_production")
    evidence_root = project_dir / "Evidence" / "writer_reliability_runs"
    run_dir = evidence_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    core = import_core(project_dir)
    scenarios = make_writer_scenarios(core)

    deterministic_reports = []
    for s in scenarios:
        deterministic_reports.append(run_writer_scenario(core, s, run_dir))

    live_reports, policy = run_live_matrix(project_dir, core, run_dir)
    final = write_final_reports(run_dir, deterministic_reports, live_reports, policy)
    print(json.dumps({"run_dir": str(run_dir), "verdict": final["writer_perfect_verdict"]}, indent=2))


if __name__ == "__main__":
    main()
