import ast
import glob
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


PROMPTS = [
    "OpenAI agentic coding workflows in 2026",
    "Codex vs local coding agents for enterprise teams",
    "Multimodal reasoning and tool-using AI systems in production",
]

NODE_ORDER = [
    "Harvester",
    "Writer",
    "DurationGate",
    "TopicExtractor",
    "SceneDirector",
    "Audio",
    "PromptArchitect",
    "SotaForge",
    "Editor",
    "Verifier",
]

WRITER_PRE_HARDENED = """def writer_node(state: AgentState):

    print("[WRITE]  [WRITER] Synthesizing duration-aware script with real CPP...")

    target_secs = state.get("target_duration", 60)
    print(
        f"    [WRITER] Drafting SOTA documentary script (Target: {state['target_duration']}s)...")
    script_hash = get_hash(state["request_prompt"])
    manifest = get_state_manifest()
    script_file = os.path.join(INTEL_DIR, "master_script.txt")
    if manifest.get("writer_prompt_hash") == script_hash and os.path.exists(script_file) and state.get("status") != "duration_fail":
        try:
            with open(script_file, "r", encoding="utf-8") as f:
                script = f.read()
            print(
                "    [RESUMING] Valid script found for this prompt. Skipping Writer.")
            return {"script": script, "status": "drafted"}
        except Exception:
            pass
    target_secs = state.get("target_duration", 60)
    target_words = int(target_secs * 2.5)
    if state.get("status") == "duration_fail":
        print(f"    [WRITER] [REWRITE] Adjusting for duration mismatch...")
        rewrite_note = f" IMPORTANT: Your previous draft was too long/short. FOCUS on EXACTLY {target_words} words."
    else:
        rewrite_note = ""
    context_block = f"\\n\\nContext for focus: {state.get('context_summary', 'General Documentary')}"
    sys_inst = (
        f"You are the absolute master of cinematic documentary scriptwriting. "
        f"Write a highly engaging documentary narration of EXACTLY {target_words} words. "
        f"This MUST produce a {target_secs}-second voiceover when spoken at natural pace. "
        f"Output ONLY spoken narration text. No headers, no stage directions, no word counts. "
        f"Every sentence on its own line.{rewrite_note}"
    )
    res = smart_retry(
        fireworks_chat_completion, "fireworks_llm",
        contents=f"{state['request_prompt']}{context_block}",
        config=types.GenerateContentConfig(
            system_instruction=sys_inst, temperature=0.5)
    )
    script = res.text.strip()
    # Apply the REAL Cinematic Prosody Preprocessor (Neural CPP)
    print("    [CPP] Executing Neural Prosody Preprocessor...")
    cpp_sys = (
        "You are a SOTA prosody engineer for AI Speech. Your ONLY job is to optimize this script for natural human-like pacing by removing or replacing 'breath-breaking' commas. "
        "RULE 1: Preserve all clause-boundary commas (e.g., 'Meanwhile, Alibaba...', or 'It architects, and it...'). "
        "RULE 2: Remove all serial commas and internal-clause commas that would cause a robotic, stuttering pace. "
        "RULE 3: Do NOT change the words. Only the punctuation. Stop only at sentence-end periods. "
        "Output ONLY the raw processed text."
    )
    cpp_res = smart_retry(
        fireworks_chat_completion, "fireworks_llm",  # Phase 20: Use Utility Flash
        contents=script,
        config=types.GenerateContentConfig(
            system_instruction=cpp_sys, temperature=0.1)
    )
    processed_script = cpp_res.text.strip()
    with open(script_file, "w", encoding="utf-8") as f:
        f.write(processed_script)

    manifest["writer_prompt_hash"] = script_hash
    save_state_manifest(manifest)

    print(
        f"    [WRITER] Script forged ({len(processed_script.split())} words). Locked and loaded.")

    return {"script": processed_script, "status": "drafted", "duration_attempts": state.get("duration_attempts", 0) + 1}
"""


def load_paths() -> Dict[str, str]:
    project_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_dir))
    import tvc_config  # noqa: E402

    return {
        "project": str(project_dir),
        "root": tvc_config.PATHS["root"],
        "intel": tvc_config.PATHS["intelligence"],
        "evidence": tvc_config.PATHS["evidence"],
        "mission_log": tvc_config.PATHS["mission_log"],
        "core_file": str(project_dir / "tvc_langgraph_core.py"),
    }


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def has_writer_hardening(core_text: str) -> bool:
    markers = [
        "# Robust context forwarding:",
        "Overshoot detected",
        "Length clamp applied",
    ]
    return all(marker in core_text for marker in markers)


def rollback_writer(core_file: Path) -> bool:
    text = core_file.read_text(encoding="utf-8")
    start = text.find("def writer_node(state: AgentState):")
    end_marker = "# ==============================================================\n\n# NODE 3: DURATION GATE (Enforce Target Length)"
    end = text.find(end_marker, start)
    if start < 0 or end < 0:
        return False
    rolled_back = text[:start] + WRITER_PRE_HARDENED + "\n\n\n" + text[end:]
    core_file.write_text(rolled_back, encoding="utf-8")
    return True


def ass_to_seconds(ass_time: str) -> float:
    # H:MM:SS.CS
    h, m, s = ass_time.split(":")
    sec, cs = s.split(".")
    return int(h) * 3600 + int(m) * 60 + int(sec) + (int(cs) / 100.0)


def ffprobe_duration(video_path: Path) -> float:
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            text=True,
            stderr=subprocess.STDOUT,
        )
        return float(out.strip())
    except Exception:
        return -1.0


def copy_artifacts(intel_dir: Path, run_dir: Path, output_path: Path) -> Dict[str, str]:
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
    ]
    copied = {}
    for name in known_files:
        src = intel_dir / name
        if src.exists():
            dst = artifacts_dir / name
            shutil.copy2(src, dst)
            copied[name] = str(dst)

    if output_path.exists():
        out_dst = run_dir / "output.mp4"
        shutil.copy2(output_path, out_dst)
        copied["output.mp4"] = str(out_dst)

    return copied


def evaluate_run(
    run_name: str,
    prompt: str,
    run_dir: Path,
    output_path: Path,
    status: str,
    intel_dir: Path,
) -> Dict:
    artifacts = run_dir / "artifacts"
    verification = read_json(artifacts / "verification_report.json", {})
    epochs = read_json(artifacts / "vtt_matrix.json", [])
    callouts = read_json(artifacts / "topic_callouts.json", [])
    filter_text = (artifacts / "filter.txt").read_text(encoding="utf-8") if (artifacts / "filter.txt").exists() else ""

    render_success = status == "success" and output_path.exists()
    video_duration = ffprobe_duration(output_path) if output_path.exists() else -1.0

    gate_verifier_true = bool(verification.get("verified") is True)
    gate_drift = isinstance(verification.get("drift"), (int, float)) and verification.get("drift", 999.0) <= 1.0
    gate_telemetry = bool(verification.get("telemetry_pass") is True)
    gate_duration = 18.0 <= video_duration <= 22.0

    epoch_integrity = True
    epoch_issues = []
    prev_start = -1.0
    assets_dirs = [Path(intel_dir) / "assets", Path(intel_dir).parent / "assets"]
    for ep in epochs:
        try:
            eid = int(ep["id"])
            start = float(ep["start_time"])
            end = float(ep["end_time"])
            if start >= end:
                epoch_integrity = False
                epoch_issues.append(f"epoch_{eid}: start>=end")
            if prev_start > start:
                epoch_integrity = False
                epoch_issues.append(f"epoch_{eid}: non-monotonic start")
            prev_start = start

            img_path = ep.get("image_path")
            has_image = bool(img_path and Path(img_path).exists())
            if not has_image:
                for assets_dir in assets_dirs:
                    matches = glob.glob(str(assets_dir / f"epoch_{eid:03d}_*png"))
                    if matches:
                        has_image = True
                        break
            if not has_image:
                epoch_integrity = False
                epoch_issues.append(f"epoch_{eid}: missing image asset")
        except Exception as exc:
            epoch_integrity = False
            epoch_issues.append(f"epoch_parse_error: {exc}")

    callout_integrity = True
    callout_issues = []
    epoch_count = len(epochs)
    for idx, c in enumerate(callouts):
        after_sentence = c.get("after_sentence")
        if not isinstance(after_sentence, int) or not (1 <= after_sentence <= max(epoch_count, 1)):
            callout_integrity = False
            callout_issues.append(f"callout_{idx}: after_sentence out of range")

    ass_path = artifacts / "typography.ass"
    topic_windows_ok = True
    topic_window_issues = []
    if ass_path.exists() and epochs:
        topic_lines = []
        for line in ass_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ",TopicCard," in line:
                m = re.match(r"Dialogue:\s*1,([^,]+),([^,]+),TopicCard", line)
                if m:
                    topic_lines.append((ass_to_seconds(m.group(1)), ass_to_seconds(m.group(2))))
        if len(topic_lines) != len(callouts):
            topic_windows_ok = False
            topic_window_issues.append("topic_card_count_mismatch")
        else:
            for i, c in enumerate(callouts):
                after = c.get("after_sentence", 1)
                if isinstance(after, int) and 1 <= after <= len(epochs):
                    ep = epochs[min(after - 1, len(epochs) - 1)]
                    try:
                        ep_start = float(ep["start_time"])
                        ep_end = float(ep["end_time"])
                        t_start, t_end = topic_lines[i]
                        if t_start < ep_start - 0.05 or t_end > ep_end + 0.05:
                            topic_windows_ok = False
                            topic_window_issues.append(f"callout_{i}: topic window exceeds epoch bounds")
                    except Exception as exc:
                        topic_windows_ok = False
                        topic_window_issues.append(f"callout_{i}: parse error {exc}")

    transition_ok = True
    transition_issues = []
    offsets = [float(x) for x in re.findall(r"xfade=transition=fade:duration=[^:]+:offset=([0-9.]+)", filter_text)]
    expected_offsets = []
    for i in range(1, len(epochs)):
        try:
            expected_offsets.append(round(float(epochs[i]["start_time"]), 3))
        except Exception:
            expected_offsets.append(None)

    if len(offsets) != max(len(epochs) - 1, 0):
        transition_ok = False
        transition_issues.append("offset_count_mismatch")
    else:
        for i, expected in enumerate(expected_offsets):
            if expected is None:
                transition_ok = False
                transition_issues.append(f"offset_{i}: missing expected")
                continue
            if abs(offsets[i] - expected) > 0.02:
                transition_ok = False
                transition_issues.append(f"offset_{i}: expected={expected}, actual={offsets[i]}")

    gates = {
        "render_success_and_artifact_exists": render_success,
        "verifier_verified_true": gate_verifier_true,
        "drift_lte_1s": gate_drift,
        "telemetry_pass_true": gate_telemetry,
        "duration_18_to_22s": gate_duration,
        "epoch_integrity": epoch_integrity,
        "subtitle_callout_integrity": callout_integrity and topic_windows_ok,
        "transition_offsets_match_epochs": transition_ok,
    }
    required_pass = all(gates.values())

    report = {
        "run": run_name,
        "prompt": prompt,
        "status": status,
        "output_path": str(output_path),
        "output_exists": output_path.exists(),
        "video_duration": video_duration,
        "verification_report": verification,
        "epoch_count": len(epochs),
        "callout_count": len(callouts),
        "gates": gates,
        "required_pass": required_pass,
        "issues": {
            "epoch_issues": epoch_issues,
            "callout_issues": callout_issues,
            "topic_window_issues": topic_window_issues,
            "transition_issues": transition_issues,
        },
    }
    return report


def write_run_report(run_dir: Path, report: Dict):
    write_json(run_dir / "run_report.json", report)
    lines = [
        f"# {report['run']} Report",
        "",
        f"- Prompt: {report['prompt']}",
        f"- Status: {report['status']}",
        f"- Output exists: {report['output_exists']}",
        f"- Video duration: {report['video_duration']}",
        f"- Required pass: {report['required_pass']}",
        "",
        "## Gates",
    ]
    for gate, value in report["gates"].items():
        lines.append(f"- {gate}: {value}")
    lines.append("")
    lines.append("## Issues")
    for k, vals in report["issues"].items():
        lines.append(f"- {k}: {vals if vals else '[]'}")
    (run_dir / "run_report.md").write_text("\n".join(lines), encoding="utf-8")


def generate_contract_map(core_file: Path, out_dir: Path):
    source = core_file.read_text(encoding="utf-8")
    tree = ast.parse(source)
    targets = {
        "harvester_node",
        "writer_node",
        "duration_gate",
        "topic_extractor",
        "scene_director",
        "audio_engineer",
        "prompt_architect",
        "sota_vision_forge",
        "lead_editor",
        "whisper_verifier",
    }

    class NodeVisitor(ast.NodeVisitor):
        def __init__(self):
            self.reads = set()
            self.return_sets = []

        def visit_Subscript(self, node):
            if isinstance(node.value, ast.Name) and node.value.id == "state":
                sl = node.slice
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                    self.reads.add(sl.value)
            self.generic_visit(node)

        def visit_Return(self, node):
            if isinstance(node.value, ast.Dict):
                keys = []
                for k in node.value.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        keys.append(k.value)
                if keys:
                    self.return_sets.append(keys)
            self.generic_visit(node)

    contract = {}
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in targets:
            v = NodeVisitor()
            v.visit(n)
            contract[n.name] = {
                "line": n.lineno,
                "reads": sorted(v.reads),
                "return_key_sets": v.return_sets,
            }

    write_json(out_dir / "contract_map.json", contract)

    md = [
        "# TVC NARRATE Contract Map",
        "",
        "## Active Node Order",
        f"- {' -> '.join(NODE_ORDER)}",
        "",
        "## Writer Downstream Dependencies",
        "- Script sentence boundaries feed SceneDirector segmentation and TopicExtractor sentence indexing.",
        "- AudioEngineer maps VTT boundaries onto SceneDirector scenes to create epoch start/end timing.",
        "- LeadEditor uses epoch timing for xfade offsets, ASS subtitle windows, and topic card bounds.",
        "- WhisperVerifier checks final A/V drift and script-vs-VTT telemetry for sync confidence.",
        "",
        "## Node Contracts",
    ]
    for fn, data in contract.items():
        md.append(f"### {fn} (line {data['line']})")
        md.append(f"- Reads: {', '.join(data['reads']) if data['reads'] else '(none)'}")
        md.append(f"- Return key sets: {json.dumps(data['return_key_sets'])}")
        md.append("")

    (out_dir / "contract_map.md").write_text("\n".join(md), encoding="utf-8")


def read_mission_entries(mission_log_path: Path) -> List[Dict]:
    return read_json(mission_log_path, [])


def run_matrix_variant(
    variant_name: str,
    base_dir: Path,
    project_dir: Path,
    intel_dir: Path,
    mission_log_path: Path,
) -> Dict:
    variant_dir = base_dir / variant_name
    variant_dir.mkdir(parents=True, exist_ok=True)
    run_reports = []

    for idx, prompt in enumerate(PROMPTS, start=1):
        run_name = f"run_{idx}"
        run_dir = variant_dir / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        terminal_log = run_dir / "terminal.log"

        before = read_mission_entries(mission_log_path)
        before_len = len(before)
        cmd = f'python supreme_commander.py "--mode MODE_NARRATE --duration 20 {prompt}" 2>&1 | Tee-Object -FilePath "{terminal_log}"'
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            cwd=str(project_dir),
            text=True,
        )

        after = read_mission_entries(mission_log_path)
        new_entries = after[before_len:] if len(after) >= before_len else []
        mission = new_entries[-1] if new_entries else (after[-1] if after else {})
        status = mission.get("status", "unknown")
        output_raw = mission.get("output") or ""
        output_path = Path(output_raw) if output_raw else (run_dir / "missing_output.mp4")
        if not output_path.is_absolute():
            output_path = project_dir / output_path

        copied = copy_artifacts(intel_dir, run_dir, output_path)
        report = evaluate_run(run_name, prompt, run_dir, output_path, status, intel_dir)
        report["command_exit_code"] = proc.returncode
        report["copied_artifacts"] = copied
        write_run_report(run_dir, report)
        run_reports.append(report)

    agg = {
        "variant": variant_name,
        "runs": run_reports,
        "required_pass_count": sum(1 for r in run_reports if r["required_pass"]),
        "run_count": len(run_reports),
    }
    agg["all_required_pass"] = agg["required_pass_count"] == agg["run_count"]
    write_json(variant_dir / "aggregate_report.json", agg)

    lines = [
        f"# Aggregate Report - {variant_name}",
        "",
        f"- Required pass count: {agg['required_pass_count']}/{agg['run_count']}",
        f"- All required pass: {agg['all_required_pass']}",
        "",
        "## Runs",
    ]
    for r in run_reports:
        lines.append(
            f"- {r['run']}: required_pass={r['required_pass']}, status={r['status']}, duration={r['video_duration']}"
        )
    (variant_dir / "aggregate_report.md").write_text("\n".join(lines), encoding="utf-8")
    return agg


def pick_best_variant(primary: Dict, secondary: Dict) -> str:
    if secondary["required_pass_count"] > primary["required_pass_count"]:
        return secondary["variant"]
    if secondary["required_pass_count"] == primary["required_pass_count"]:
        if secondary["all_required_pass"] and not primary["all_required_pass"]:
            return secondary["variant"]
    return primary["variant"]


def main():
    paths = load_paths()
    project_dir = Path(paths["project"])
    intel_dir = Path(paths["intel"])
    evidence_dir = Path(paths["evidence"])
    core_file = Path(paths["core_file"])
    mission_log = Path(paths["mission_log"])

    run_root = evidence_dir / "sync_integrity_runs" / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

    original_core_text = core_file.read_text(encoding="utf-8")
    hardening_present = has_writer_hardening(original_core_text)

    generate_contract_map(core_file, run_root)
    baseline = run_matrix_variant("baseline_current", run_root, project_dir, intel_dir, mission_log)

    final_variant = "baseline_current"
    rollback_result = None
    rollback_applied = False

    if hardening_present and not baseline["all_required_pass"]:
        rollback_applied = rollback_writer(core_file)
        if rollback_applied:
            rollback_result = run_matrix_variant("rollback_writer", run_root, project_dir, intel_dir, mission_log)
            final_variant = pick_best_variant(baseline, rollback_result)
            if final_variant == "baseline_current":
                core_file.write_text(original_core_text, encoding="utf-8")

    final_summary = {
        "timestamp": datetime.now().isoformat(),
        "run_root": str(run_root),
        "baseline_variant": baseline["variant"],
        "baseline_required_pass_count": baseline["required_pass_count"],
        "rollback_attempted": rollback_applied,
        "rollback_variant": rollback_result["variant"] if rollback_result else None,
        "rollback_required_pass_count": rollback_result["required_pass_count"] if rollback_result else None,
        "selected_variant": final_variant,
        "selected_report": str(run_root / final_variant / "aggregate_report.json"),
    }
    write_json(run_root / "final_verdict.json", final_summary)

    lines = [
        "# TVC Full-System Sync Integrity Verdict",
        "",
        f"- Run root: {run_root}",
        f"- Baseline required pass: {baseline['required_pass_count']}/{baseline['run_count']}",
        f"- Rollback attempted: {rollback_applied}",
        f"- Selected variant: {final_variant}",
        f"- Final report: {run_root / final_variant / 'aggregate_report.json'}",
    ]
    if rollback_result:
        lines.append(f"- Rollback required pass: {rollback_result['required_pass_count']}/{rollback_result['run_count']}")
    (run_root / "final_verdict.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(final_summary, indent=2))


if __name__ == "__main__":
    main()
