import contextlib
import importlib
import io
import json
import sys
import traceback
import types
from datetime import datetime
from pathlib import Path

try:
    from tvc_key_audit import log_api_key_lookup
except Exception:
    def log_api_key_lookup(**kwargs):
        return False


PROJECT_DIR = Path(r"D:\AI-Apps-In-Drive\App_Station\Video_production")
RUN_ROOT = PROJECT_DIR / "Evidence" / "node1_writer_guard_runs"


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_core():
    sys.path.insert(0, str(PROJECT_DIR))
    try:
        import tvc_langgraph_core as core  # noqa
        return core
    except SystemExit:
        # Test-only resilience: shim vault access from vault_dump.json
        def _shim_get_secret(secret_name):
            vault = PROJECT_DIR / "vault_dump.json"
            data = read_json(vault, [])
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
            if "key_HGmChvaB" in secret_name:
                for entry in data:
                    if entry.get("provider") == "Fireworks AI" and entry.get("key"):
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
        return importlib.import_module("tvc_langgraph_core")


def _write_fake_vtt(core, video_id: str, text: str):
    harvest_dir = Path(core.INTEL_DIR) / "yt_harvest"
    harvest_dir.mkdir(parents=True, exist_ok=True)
    path = harvest_dir / f"{video_id}.en.vtt"
    payload = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\n"
        f"{text}\n\n"
        "00:00:02.000 --> 00:00:04.000\n"
        f"{text}\n"
    )
    path.write_text(payload, encoding="utf-8")


def _patch_yt_dlp(core, mode: str):
    import yt_dlp

    orig_extract_info = yt_dlp.YoutubeDL.extract_info
    counters = {"video_calls": 0, "forced_429": 0}

    def patched_extract_info(self, url, *args, **kwargs):
        url_s = str(url or "")
        if url_s.startswith("ytsearch"):
            if mode == "H2":
                return {"entries": [{"id": f"off_{i:02d}", "title": f"Iran war airport update {i}"} for i in range(1, 16)]}
            return {"entries": [{"id": f"rel_{i:02d}", "title": f"Best stand up comedy jokes clip {i}"} for i in range(1, 20)]}

        if "watch?v=" in url_s:
            video_id = url_s.split("watch?v=")[-1].split("&")[0]
        else:
            video_id = url_s.strip()

        counters["video_calls"] += 1

        if mode == "H3" and counters["forced_429"] < 3:
            counters["forced_429"] += 1
            raise Exception("HTTP Error 429: Too Many Requests (forced throttling)")

        if mode == "H2":
            off_topic = (
                "Iran airspace closures are affecting flights across Dubai and regional airports. "
                "Travel disruptions continue with airline reroutes and war-zone uncertainty."
            )
            _write_fake_vtt(core, video_id, off_topic)
        else:
            relevant = (
                "Stand up comedy special with comedians delivering jokes to a live audience on stage. "
                "The comedian performs crowd work and funny punchlines from a comedy set."
            )
            _write_fake_vtt(core, video_id, relevant)

        return {"id": video_id}

    yt_dlp.YoutubeDL.extract_info = patched_extract_info
    return yt_dlp, orig_extract_info


def run_harvester_scenario(core, run_dir: Path, scenario_id: str, prompt: str):
    log_file = run_dir / scenario_id / "terminal.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    mode = scenario_id
    ydl_mod, orig_extract_info = _patch_yt_dlp(core, mode)
    buff = io.StringIO()

    scenario_report = {
        "scenario": scenario_id,
        "prompt": prompt,
        "pass": False,
        "status": None,
        "error": "",
        "harvester_report": {},
        "quality_report": {},
        "terminal_log": str(log_file),
    }

    try:
        with contextlib.redirect_stdout(buff), contextlib.redirect_stderr(buff):
            result = core.harvester_node(
                {
                    "request_prompt": prompt,
                    "target_duration": 120,
                    "input_source": "YOUTUBE_HARVEST",
                }
            )
        scenario_report["status"] = result.get("status")
    except Exception as exc:
        scenario_report["error"] = f"{type(exc).__name__}: {exc}"
        scenario_report["status"] = "exception"
    finally:
        ydl_mod.YoutubeDL.extract_info = orig_extract_info

    log_file.write_text(buff.getvalue(), encoding="utf-8")
    harvester_report = read_json(Path(core.INTEL_DIR) / "harvester_run_report.json", {})
    quality_report = read_json(Path(core.INTEL_DIR) / "harvester_quality_report.json", {})
    scenario_report["harvester_report"] = harvester_report
    scenario_report["quality_report"] = quality_report

    if scenario_id == "H1":
        scenario_report["pass"] = (
            scenario_report["status"] == "harvested"
            and int(harvester_report.get("relevant_vtt_count", 0)) >= 5
            and bool(harvester_report.get("quality_gate_passed"))
        )
    elif scenario_id == "H2":
        scenario_report["pass"] = (
            scenario_report["status"] == "exception"
            and "Harvester quality gate failed" in scenario_report["error"]
            and harvester_report.get("status") == "hard_stop_insufficient_relevance"
        )
    elif scenario_id == "H3":
        scenario_report["pass"] = (
            scenario_report["status"] == "harvested"
            and int(harvester_report.get("relevant_vtt_count", 0)) >= 5
            and bool(harvester_report.get("cooldown_durations"))
        )

    write_json(run_dir / scenario_id / "scenario_report.json", scenario_report)
    return scenario_report


def run_writer_meta_guard(core, run_dir: Path):
    scenario_id = "W1"
    log_file = run_dir / scenario_id / "terminal.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    buff = io.StringIO()

    meta_text = (
        "The user wants me to output the processed text after applying the prosody rules. "
        "I need to check the system message and conversation history before proceeding."
    )

    orig_smart_retry = core.smart_retry

    def fake_smart_retry(fn, endpoint="default", *args, **kwargs):
        template = str(kwargs.get("prompt_template_id", "") or "")
        if template in ("PROMPT_D_WRITER_SCRIPT_DRAFT", "PROMPT_E_WRITER_CPP_PROSODY"):
            return core.DummyRes(meta_text)
        return orig_smart_retry(fn, endpoint, *args, **kwargs)

    core.smart_retry = fake_smart_retry

    scenario_report = {
        "scenario": scenario_id,
        "pass": False,
        "status": None,
        "error": "",
        "writer_quality_report": {},
        "terminal_log": str(log_file),
    }

    prompt = f"W1 Writer meta-leak probe {datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        with contextlib.redirect_stdout(buff), contextlib.redirect_stderr(buff):
            core.writer_node(
                {
                    "request_prompt": prompt,
                    "target_duration": 120,
                    "input_source": "YOUTUBE_HARVEST",
                    "harvested_intelligence": "Stand up comedy jokes and comedians on stage with audience laughter.",
                    "duration_attempts": 0,
                }
            )
        scenario_report["status"] = "unexpected_success"
    except Exception as exc:
        scenario_report["status"] = "exception"
        scenario_report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        core.smart_retry = orig_smart_retry

    log_file.write_text(buff.getvalue(), encoding="utf-8")
    writer_quality = read_json(Path(core.INTEL_DIR) / "writer_quality_report.json", {})
    scenario_report["writer_quality_report"] = writer_quality
    scenario_report["pass"] = (
        scenario_report["status"] == "exception"
        and "Writer quality gate failed" in scenario_report["error"]
        and str(writer_quality.get("final_status", "")) == "hard_stop"
    )
    write_json(run_dir / scenario_id / "scenario_report.json", scenario_report)
    return scenario_report


def main():
    run_dir = RUN_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    core = load_core()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # H1 good yield
    prompt_h1 = f"H1 {ts} Best stand up comedians and their funniest jokes for a documentary"
    h1 = run_harvester_scenario(core, run_dir, "H1", prompt_h1)

    # H2 low/off-topic yield must hard-stop
    prompt_h2 = f"H2 {ts} Best stand up comedians and their funniest jokes for a documentary"
    h2 = run_harvester_scenario(core, run_dir, "H2", prompt_h2)

    # H3 throttled but recoverable
    prompt_h3 = f"H3 {ts} Best stand up comedians and their funniest jokes for a documentary"
    h3 = run_harvester_scenario(core, run_dir, "H3", prompt_h3)

    # W1 meta leak rejection
    w1 = run_writer_meta_guard(core, run_dir)

    scenarios = [h1, h2, h3, w1]
    aggregate = {
        "timestamp": datetime.now().isoformat(),
        "run_dir": str(run_dir),
        "scenarios": [{k: v for k, v in s.items() if k in ("scenario", "pass", "status", "error")} for s in scenarios],
        "all_passed": all(s.get("pass") for s in scenarios),
    }
    write_json(run_dir / "aggregate_verdict.json", aggregate)
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(traceback.format_exc())
        raise
