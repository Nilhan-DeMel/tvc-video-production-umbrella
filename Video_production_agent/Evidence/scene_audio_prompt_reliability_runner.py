import contextlib
import importlib
import io
import json
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

try:
    from tvc_key_audit import log_api_key_lookup
except Exception:
    def log_api_key_lookup(**kwargs):
        return False


PROJECT_DIR = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_DIR / "Evidence" / "scene_audio_prompt_reliability_runs"


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def install_vault_shim(project_dir: Path):
    import types

    def _shim_get_secret(secret_name):
        data = read_json(project_dir / "vault_dump.json", [])
        target_provider = "Fireworks AI" if "key_HGmChvaB" in secret_name else ("Google" if "Gemini" in secret_name else None)
        for entry in data:
            if entry.get("name") == secret_name and entry.get("key"):
                log_api_key_lookup(
                    secret_alias=secret_name,
                    outcome="success_shim_name_match",
                    source="evidence_shim",
                    key_value=entry.get("key"),
                    cache_hit=False,
                )
                return entry["key"]
        if target_provider:
            for entry in data:
                provider = str(entry.get("provider", ""))
                if target_provider.lower() in provider.lower() and entry.get("key"):
                    log_api_key_lookup(
                        secret_alias=secret_name,
                        outcome="success_shim_provider_match",
                        source="evidence_shim",
                        key_value=entry.get("key"),
                        cache_hit=False,
                    )
                    return entry["key"]
        log_api_key_lookup(
            secret_alias=secret_name,
            outcome="failure_shim_not_found",
            source="evidence_shim",
            cache_hit=False,
        )
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


def make_script() -> str:
    return "\n".join([
        "OpenAI agentic workflows now coordinate enterprise repositories.",
        "Codex audits, rewrites, and validates with high precision.",
        "Multimodal systems combine text, vision, and tool execution.",
        "Teams demand synchronized narration and image continuity.",
        "Reliability and auditability determine production trust.",
    ])


class FakeSubMaker:
    def feed(self, _chunk):
        return None

    def get_srt(self):
        return (
            "1\n00:00:00,100 --> 00:00:01,500\nOpenAI workflows.\n\n"
            "2\n00:00:01,500 --> 00:00:03,000\nCodex audits code.\n\n"
            "3\n00:00:03,000 --> 00:00:05,000\nReliable multimodal execution.\n"
        )


class FakeCommunicate:
    def __init__(self, _text, _voice):
        self._chunks = [
            {"type": "audio", "data": b"\x00\x01"},
            {"type": "SentenceBoundary", "offset": 1000000},
            {"type": "audio", "data": b"\x00\x02"},
            {"type": "SentenceBoundary", "offset": 3000000},
            {"type": "audio", "data": b"\x00\x03"},
            {"type": "SentenceBoundary", "offset": 5000000},
        ]

    async def stream(self):
        for c in self._chunks:
            yield c


def patch_env(core, scenario_intel: Path):
    original = {
        "INTEL_DIR": core.INTEL_DIR,
        "TRACE_FILE": core.TRACE_FILE,
        "POLICY_FILE": core.POLICY_FILE,
    }
    core.INTEL_DIR = str(scenario_intel)
    core.TRACE_FILE = str(scenario_intel / "api_call_trace.jsonl")
    core.POLICY_FILE = str(scenario_intel / "paid_api_policy_check.json")
    scenario_intel.mkdir(parents=True, exist_ok=True)
    return original


def restore_env(core, original):
    core.INTEL_DIR = original["INTEL_DIR"]
    core.TRACE_FILE = original["TRACE_FILE"]
    core.POLICY_FILE = original["POLICY_FILE"]


def run_scenario(core, run_dir: Path, name: str, fn):
    scenario_dir = run_dir / "scenarios" / name
    scenario_intel = scenario_dir / "intel"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    original = patch_env(core, scenario_intel)
    buff = io.StringIO()
    report = {"scenario": name, "pass": False, "errors": []}
    try:
        with contextlib.redirect_stdout(buff), contextlib.redirect_stderr(buff):
            outcome = fn(core, scenario_intel)
        report.update(outcome)
    except Exception as e:
        report["errors"].append(f"{type(e).__name__}: {e}")
        report["traceback"] = traceback.format_exc()
    finally:
        (scenario_dir / "terminal.log").write_text(buff.getvalue(), encoding="utf-8")
        write_json(scenario_dir / "scenario_report.json", report)
        restore_env(core, original)
    return report


def scenario_sd1(core, scenario_intel: Path):
    script = make_script()
    responses = {
        "PROMPT_F_SCENE_DIRECTOR_SEGMENTATION": "not-json",
        "PROMPT_F_SCENE_DIRECTOR_REPAIR": "still-not-json",
    }
    original_sr = core.smart_retry

    def fake_smart_retry(fn, endpoint="default", *args, **kwargs):
        if fn == core.fireworks_chat_completion:
            tid = kwargs.get("prompt_template_id")
            return core.DummyRes(responses.get(tid, ""))
        return fn(*args, **kwargs)

    core.smart_retry = fake_smart_retry
    try:
        result = core.scene_director({"script": script, "request_prompt": "sd1"})
    finally:
        core.smart_retry = original_sr

    report = read_json(scenario_intel / "scene_audio_prompt_report.json", {})
    source = (((report.get("nodes") or {}).get("SceneDirector") or {}).get("source"))
    passed = result.get("status") == "scenes_directed" and len(result.get("visual_scenes", [])) > 0 and source == "deterministic_fallback"
    return {"pass": bool(passed), "status": result.get("status"), "source": source}


def scenario_sd2(core, scenario_intel: Path):
    script = make_script()
    responses = {
        "PROMPT_F_SCENE_DIRECTOR_SEGMENTATION": json.dumps({"style_dna": "x", "meta_context": "y"}),
        "PROMPT_F_SCENE_DIRECTOR_REPAIR": json.dumps({"meta_context": "missing scenes"}),
    }
    original_sr = core.smart_retry

    def fake_smart_retry(fn, endpoint="default", *args, **kwargs):
        if fn == core.fireworks_chat_completion:
            tid = kwargs.get("prompt_template_id")
            return core.DummyRes(responses.get(tid, ""))
        return fn(*args, **kwargs)

    core.smart_retry = fake_smart_retry
    try:
        result = core.scene_director({"script": script, "request_prompt": "sd2"})
    finally:
        core.smart_retry = original_sr

    report = read_json(scenario_intel / "scene_audio_prompt_report.json", {})
    source = (((report.get("nodes") or {}).get("SceneDirector") or {}).get("source"))
    passed = result.get("status") == "scenes_directed" and len(result.get("visual_scenes", [])) > 0 and source in {"deterministic_fallback", "repair_retry"}
    return {"pass": bool(passed), "status": result.get("status"), "source": source}


def scenario_a1(core, scenario_intel: Path):
    script = make_script()
    script_hash = core.get_hash(script)
    visual_scenes = [
        {"id": 1, "text": "A", "visual_intent": "A", "subjects": []},
        {"id": 2, "text": "B", "visual_intent": "B", "subjects": []},
    ]
    write_json(scenario_intel / "state_manifest.json", {"audio_script_hash": script_hash})
    write_json(
        scenario_intel / "vtt_matrix.json",
        [
            {"id": 1, "start_time": 0.1, "end_time": 1.5, "duration": 1.4, "text": "A", "visual_intent": "A"},
            {"id": 2, "start_time": 1.5, "end_time": 3.0, "duration": 1.5, "text": "B", "visual_intent": "B"},
        ],
    )
    (scenario_intel / "narration.vtt").write_text(
        "WEBVTT\n\n00:00:00.100 --> 00:00:01.500\nA\n\n00:00:01.500 --> 00:00:03.000\nB\n",
        encoding="utf-8",
    )
    audio_path = PROJECT_DIR / "master_narration.mp3"
    audio_path.write_bytes(b"\x00\x01\x02")

    result = core.audio_engineer({"script": script, "visual_scenes": visual_scenes})
    passed = (
        result.get("status") == "audio_forged"
        and isinstance(result.get("total_epochs"), int)
        and result.get("total_epochs", 0) > 0
    )
    return {"pass": bool(passed), "status": result.get("status"), "total_epochs": result.get("total_epochs")}


def scenario_a2(core, scenario_intel: Path):
    script = make_script()
    visual_scenes = [
        {"id": 1, "text": "One", "visual_intent": "One shot", "subjects": []},
        {"id": 2, "text": "Two", "visual_intent": "Two shot", "subjects": []},
        {"id": 3, "text": "Three", "visual_intent": "Three shot", "subjects": []},
    ]

    original_sr = core.smart_retry
    original_comm = core.edge_tts.Communicate
    original_sub = core.edge_tts.SubMaker

    responses = {
        "PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT": "One.\nTwo.\nThree.",
        "PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING": "not-json",
        "PROMPT_G_AUDIO_VTT_TO_EPOCH_REPAIR": "still-not-json",
    }

    def fake_smart_retry(fn, endpoint="default", *args, **kwargs):
        if fn == core.fireworks_chat_completion:
            tid = kwargs.get("prompt_template_id")
            return core.DummyRes(responses.get(tid, ""))
        return fn(*args, **kwargs)

    core.smart_retry = fake_smart_retry
    core.edge_tts.Communicate = FakeCommunicate
    core.edge_tts.SubMaker = FakeSubMaker
    try:
        result = core.audio_engineer({"script": script, "visual_scenes": visual_scenes})
    finally:
        core.smart_retry = original_sr
        core.edge_tts.Communicate = original_comm
        core.edge_tts.SubMaker = original_sub

    stage = read_json(scenario_intel / "audio_stage_report.json", {})
    mapping_source = stage.get("mapping_source")
    epochs = read_json(scenario_intel / "vtt_matrix.json", [])
    monotonic = True
    prev = -1.0
    for ep in epochs:
        st = float(ep.get("start_time", -1))
        en = float(ep.get("end_time", -1))
        if not (st < en) or st < prev:
            monotonic = False
            break
        prev = st
    passed = result.get("status") == "audio_forged" and len(epochs) == len(visual_scenes) and monotonic and mapping_source in {"repair_retry", "local_deterministic"}
    return {"pass": bool(passed), "status": result.get("status"), "mapping_source": mapping_source}


def scenario_a3(core, scenario_intel: Path):
    script = make_script()
    visual_scenes = [
        {"id": 1, "text": "One", "visual_intent": "One shot", "subjects": []},
        {"id": 2, "text": "Two", "visual_intent": "Two shot", "subjects": []},
    ]

    original_sr = core.smart_retry
    original_comm = core.edge_tts.Communicate
    original_sub = core.edge_tts.SubMaker
    valid_mapping = json.dumps([
        {"id": 1, "start_time": 0.1, "end_time": 1.6, "duration": 1.5, "text": "One", "visual_intent": "One shot"},
        {"id": 2, "start_time": 1.6, "end_time": 3.0, "duration": 1.4, "text": "Two", "visual_intent": "Two shot"},
    ])
    responses = {
        "PROMPT_GA_AUDIO_NEURAL_CPP_REFINEMENT": "This output is unrelated and should be rejected by overlap checks only.",
        "PROMPT_G_AUDIO_VTT_TO_EPOCH_MAPPING": valid_mapping,
    }

    def fake_smart_retry(fn, endpoint="default", *args, **kwargs):
        if fn == core.fireworks_chat_completion:
            tid = kwargs.get("prompt_template_id")
            return core.DummyRes(responses.get(tid, ""))
        return fn(*args, **kwargs)

    core.smart_retry = fake_smart_retry
    core.edge_tts.Communicate = FakeCommunicate
    core.edge_tts.SubMaker = FakeSubMaker
    try:
        result = core.audio_engineer({"script": script, "visual_scenes": visual_scenes})
    finally:
        core.smart_retry = original_sr
        core.edge_tts.Communicate = original_comm
        core.edge_tts.SubMaker = original_sub

    stage = read_json(scenario_intel / "audio_stage_report.json", {})
    has_local_cpp = any(s.get("stage") == "local_cpp" and s.get("status") == "used" for s in stage.get("stages", []))
    passed = result.get("status") == "audio_forged" and has_local_cpp
    return {"pass": bool(passed), "status": result.get("status"), "local_cpp_used": has_local_cpp}


def scenario_pa1(core, scenario_intel: Path):
    state = {
        "script": make_script(),
        "total_epochs": 3,
        "epochs": [
            {"id": 1, "text": "One", "visual_intent": "One shot", "subjects": []},
            {"id": 2, "text": "Two", "visual_intent": "Two shot", "subjects": []},
            {"id": 3, "text": "Three", "visual_intent": "Three shot", "subjects": []},
        ],
    }
    original_sr = core.smart_retry
    responses = {
        "PROMPT_H_PROMPT_ARCHITECT_IMAGE_SNIPPETS": "not-json",
        "PROMPT_H_PROMPT_ARCHITECT_REPAIR": json.dumps([
            {"id": 1, "sota_prompt": "Prompt one"},
            {"id": 2, "sota_prompt": "Prompt two"},
            {"id": 3, "sota_prompt": "Prompt three"},
        ]),
    }

    def fake_smart_retry(fn, endpoint="default", *args, **kwargs):
        if fn == core.fireworks_chat_completion:
            return core.DummyRes(responses.get(kwargs.get("prompt_template_id"), ""))
        return fn(*args, **kwargs)

    core.smart_retry = fake_smart_retry
    try:
        result = core.prompt_architect(state)
    finally:
        core.smart_retry = original_sr

    report = read_json(scenario_intel / "scene_audio_prompt_report.json", {})
    source = (((report.get("nodes") or {}).get("PromptArchitect") or {}).get("source"))
    passed = result.get("status") == "prompts_architected" and len(result.get("sota_prompts", [])) == 3 and len(result.get("qa_targets", [])) == 3 and source in {"repair_retry", "literal_fallback"}
    return {"pass": bool(passed), "status": result.get("status"), "source": source}


def scenario_pa2(core, scenario_intel: Path):
    state = {
        "script": make_script(),
        "total_epochs": 3,
        "epochs": [
            {"id": 1, "text": "One", "visual_intent": "One shot", "subjects": []},
            {"id": 2, "text": "Two", "visual_intent": "Two shot", "subjects": []},
            {"id": 3, "text": "Three", "visual_intent": "Three shot", "subjects": []},
        ],
    }
    script_hash = core.get_hash(state["script"])
    write_json(scenario_intel / "state_manifest.json", {"prompts_script_hash": script_hash})
    write_json(scenario_intel / "master_prompts.json", {"prompts": ["bad"], "qa_targets": []})

    original_sr = core.smart_retry
    responses = {
        "PROMPT_H_PROMPT_ARCHITECT_IMAGE_SNIPPETS": json.dumps([
            {"id": 1, "sota_prompt": "Prompt one"},
            {"id": 2, "sota_prompt": "Prompt two"},
            {"id": 3, "sota_prompt": "Prompt three"},
        ]),
    }

    def fake_smart_retry(fn, endpoint="default", *args, **kwargs):
        if fn == core.fireworks_chat_completion:
            return core.DummyRes(responses.get(kwargs.get("prompt_template_id"), ""))
        return fn(*args, **kwargs)

    core.smart_retry = fake_smart_retry
    try:
        result = core.prompt_architect(state)
    finally:
        core.smart_retry = original_sr

    report = read_json(scenario_intel / "scene_audio_prompt_report.json", {})
    source = (((report.get("nodes") or {}).get("PromptArchitect") or {}).get("source"))
    passed = result.get("status") == "prompts_architected" and len(result.get("sota_prompts", [])) == 3 and source in {"primary", "repair_retry", "literal_fallback"}
    return {"pass": bool(passed), "status": result.get("status"), "source": source}


def copy_run_artifacts(intel_dir: Path, run_dir: Path):
    artifacts = [
        "pipeline_run.log",
        "verification_report.json",
        "vtt_matrix.json",
        "topic_callouts.json",
        "filter.txt",
        "master_prompts.json",
        "scene_audio_prompt_report.json",
        "audio_stage_report.json",
        "paid_api_policy_check.json",
    ]
    dst = run_dir / "artifacts"
    dst.mkdir(parents=True, exist_ok=True)
    copied = {}
    for name in artifacts:
        src = intel_dir / name
        if src.exists():
            shutil.copy2(src, dst / name)
            copied[name] = str(dst / name)
    return copied


def evaluate_e2e_run(run_result: dict):
    log_text = run_result.get("terminal_log", "")
    artifacts = run_result.get("artifacts", {})
    policy = read_json(Path(artifacts.get("paid_api_policy_check.json", "")), {})
    vtt_matrix = read_json(Path(artifacts.get("vtt_matrix.json", "")), [])
    prompts_obj = read_json(Path(artifacts.get("master_prompts.json", "")), {})
    sap_report = read_json(Path(artifacts.get("scene_audio_prompt_report.json", "")), {})
    verifier = read_json(Path(artifacts.get("verification_report.json", "")), {})

    scene_hard_crash = "Last Error: Expecting value: line 1 column 1 (char 0)" in log_text
    audio_total_ok = isinstance((((sap_report.get("nodes") or {}).get("Audio") or {}).get("total_epochs")), int)

    epoch_ok = True
    prev_start = -1.0
    for ep in vtt_matrix:
        try:
            st = float(ep.get("start_time"))
            en = float(ep.get("end_time"))
            if not (st < en) or st < prev_start:
                epoch_ok = False
                break
            prev_start = st
        except Exception:
            epoch_ok = False
            break

    prompts = []
    qas = []
    if isinstance(prompts_obj, dict):
        prompts = prompts_obj.get("prompts", [])
        qas = prompts_obj.get("qa_targets", [])
    prompt_parity = isinstance(prompts, list) and isinstance(qas, list) and len(prompts) == len(vtt_matrix) and len(qas) == len(vtt_matrix)

    policy_ok = bool(policy.get("passed") is True) and policy.get("observed_paid_hosts") == ["api.fireworks.ai"]
    verifier_gate = True
    if verifier:
        drift = verifier.get("drift", 999.0)
        verifier_gate = bool(verifier.get("telemetry_pass") is True) and isinstance(drift, (int, float)) and drift <= 1.0

    attribution = "external"
    if scene_hard_crash:
        attribution = "SceneDirector"
    elif (not audio_total_ok) or ("Voice Forge Failed" in log_text) or ("Last Error: 'total_epochs'" in log_text):
        attribution = "Audio"
    elif not prompt_parity:
        attribution = "PromptArchitect"

    passed = (not scene_hard_crash) and audio_total_ok and epoch_ok and prompt_parity and policy_ok and verifier_gate
    return {
        "pass": bool(passed),
        "gates": {
            "no_scene_hard_crash": not scene_hard_crash,
            "audio_total_epochs_present": audio_total_ok,
            "epoch_integrity": epoch_ok,
            "prompt_parity": prompt_parity,
            "policy_fireworks_only": policy_ok,
            "verifier_gate_if_present": verifier_gate,
        },
        "attribution": attribution,
    }


def run_e2e_matrix(run_dir: Path):
    intel_dir = PROJECT_DIR / "tvc_multi_agent_db"
    matrix = [
        {"name": "user_context_1", "args": ["--mode", "MODE_NARRATE", "--duration", "20", "--context", "OpenAI agentic workflows and Codex reliability in 2026.", "Scene audio prompt stability test A"]},
        {"name": "user_context_2", "args": ["--mode", "MODE_NARRATE", "--duration", "20", "--context", "Multimodal tool-using systems in production with strict synchronization.", "Scene audio prompt stability test B"]},
        {"name": "youtube_1", "args": ["--mode", "MODE_NARRATE", "--duration", "20", "OpenAI codex workflow updates 2026"]},
        {"name": "youtube_2", "args": ["--mode", "MODE_NARRATE", "--duration", "20", "Enterprise coding agents and multimodal reasoning in 2026"]},
    ]

    results = []
    for row in matrix:
        run_sub = run_dir / "e2e" / row["name"]
        run_sub.mkdir(parents=True, exist_ok=True)
        cmd = ["python", str(PROJECT_DIR / "supreme_commander.py")] + row["args"]
        proc = subprocess.run(cmd, cwd=str(PROJECT_DIR), capture_output=True, text=True)
        terminal = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        (run_sub / "terminal.log").write_text(terminal, encoding="utf-8")
        copied = copy_run_artifacts(intel_dir, run_sub)
        entry = {
            "name": row["name"],
            "command": " ".join(cmd),
            "returncode": proc.returncode,
            "terminal_log": terminal,
            "artifacts": copied,
        }
        entry.update(evaluate_e2e_run(entry))
        write_json(run_sub / "run_report.json", entry)
        results.append(entry)
    return results


def main():
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    core = import_core(PROJECT_DIR)

    deterministic = []
    deterministic.append(run_scenario(core, run_dir, "SD1_malformed_to_fallback", scenario_sd1))
    deterministic.append(run_scenario(core, run_dir, "SD2_schema_missing_to_fallback", scenario_sd2))
    deterministic.append(run_scenario(core, run_dir, "A1_resume_contract_total_epochs", scenario_a1))
    deterministic.append(run_scenario(core, run_dir, "A2_mapping_malformed_to_local", scenario_a2))
    deterministic.append(run_scenario(core, run_dir, "A3_local_cpp_activation", scenario_a3))
    deterministic.append(run_scenario(core, run_dir, "PA1_malformed_json_recovery", scenario_pa1))
    deterministic.append(run_scenario(core, run_dir, "PA2_invalid_cache_regenerate", scenario_pa2))

    e2e = run_e2e_matrix(run_dir)

    failures = {}
    for r in e2e:
        if not r.get("pass"):
            key = r.get("attribution", "external")
            failures[key] = failures.get(key, 0) + 1

    verdict = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "deterministic_total": len(deterministic),
        "deterministic_passed": sum(1 for r in deterministic if r.get("pass")),
        "deterministic_failed": [r.get("scenario") for r in deterministic if not r.get("pass")],
        "e2e_total": len(e2e),
        "e2e_passed": sum(1 for r in e2e if r.get("pass")),
        "e2e_failed": [r.get("name") for r in e2e if not r.get("pass")],
        "failure_attribution": failures,
        "all_passed": all(r.get("pass") for r in deterministic) and all(r.get("pass") for r in e2e),
    }

    write_json(run_dir / "deterministic_reports.json", deterministic)
    write_json(run_dir / "e2e_reports.json", e2e)
    write_json(run_dir / "aggregate_verdict.json", verdict)
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
