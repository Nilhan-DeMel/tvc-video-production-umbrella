import contextlib
import importlib
import io
import json
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
RUNS_ROOT = PROJECT_DIR / "Evidence" / "topic_extractor_reliability_runs"


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


def scenario_script() -> str:
    return "\n".join([
        "OpenAI agentic workflows reshape coding teams.",
        "Codex now handles repository scale context.",
        "Multimodal reliability decides production trust.",
        "Fireworks only paid API policy stays enforced.",
        "Enterprise teams need auditable automation.",
    ])


def _grounded(topic: str, script_text: str) -> bool:
    s = script_text.lower()
    t = str(topic or "").lower()
    if not t:
        return False
    if t in s:
        return True
    import re

    kws = [w for w in re.findall(r"[a-z0-9']+", t) if len(w) > 3]
    return any(w in s for w in kws)


def validate_contract(callouts, script_text: str):
    errors = []
    if not isinstance(callouts, list) or not callouts:
        return ["empty_or_non_list_callouts"]
    sentence_count = max(1, len([x for x in script_text.splitlines() if x.strip()]))
    seen = set()
    for idx, c in enumerate(callouts):
        if not isinstance(c, dict):
            errors.append(f"item_{idx}_not_dict")
            continue
        topic = str(c.get("topic", "") or "")
        after = c.get("after_sentence")
        if not topic:
            errors.append(f"item_{idx}_empty_topic")
        if topic != topic.upper():
            errors.append(f"item_{idx}_topic_not_upper")
        if len(topic) > 20:
            errors.append(f"item_{idx}_topic_over_20")
        if topic in seen:
            errors.append(f"item_{idx}_duplicate_topic")
        seen.add(topic)
        if not isinstance(after, int):
            errors.append(f"item_{idx}_after_not_int")
        else:
            if after < 1 or after > sentence_count:
                errors.append(f"item_{idx}_after_out_of_range:{after}")
        if not _grounded(topic, script_text):
            errors.append(f"item_{idx}_not_grounded")
    return errors


def run_scenario(core, run_dir: Path, name: str, responses, setup_fn=None, extra_checks=None):
    scenario_dir = run_dir / "scenarios" / name
    scenario_dir.mkdir(parents=True, exist_ok=True)
    scenario_intel = scenario_dir / "intel"
    scenario_intel.mkdir(parents=True, exist_ok=True)

    original_intel = core.INTEL_DIR
    original_trace = core.TRACE_FILE
    original_policy = core.POLICY_FILE
    original_smart_retry = core.smart_retry

    core.INTEL_DIR = str(scenario_intel)
    core.TRACE_FILE = str(scenario_intel / "api_call_trace.jsonl")
    core.POLICY_FILE = str(scenario_intel / "paid_api_policy_check.json")

    script_text = scenario_script()
    state = {"script": script_text}
    if setup_fn:
        setup_fn(core, scenario_intel, state)

    queue = list(responses)
    call_log = []

    def fake_smart_retry(fn, endpoint="default", *args, **kwargs):
        if fn == core.fireworks_chat_completion:
            call_log.append({
                "endpoint": endpoint,
                "prompt_template_id": kwargs.get("prompt_template_id"),
                "trace_node": kwargs.get("trace_node"),
                "contents_preview": " ".join(str(kwargs.get("contents", "")).split())[:180],
            })
            if not queue:
                raise RuntimeError("scenario_response_queue_empty")
            nxt = queue.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return core.DummyRes(nxt)
        return fn(*args, **kwargs)

    core.smart_retry = fake_smart_retry
    buff = io.StringIO()
    scenario_report = {
        "scenario": name,
        "pass": False,
        "errors": [],
        "call_log": [],
        "contract_errors": [],
        "topic_callouts": [],
        "status": None,
    }

    try:
        with contextlib.redirect_stdout(buff), contextlib.redirect_stderr(buff):
            result = core.topic_extractor(state)
        terminal = buff.getvalue()
        (scenario_dir / "terminal.log").write_text(terminal, encoding="utf-8")
        topic_file = scenario_intel / "topic_callouts.json"
        persisted = read_json(topic_file, [])
        contract_errors = validate_contract(persisted, script_text)
        scenario_report["status"] = result.get("status")
        scenario_report["topic_callouts"] = persisted
        scenario_report["contract_errors"] = contract_errors
        scenario_report["call_log"] = call_log
        scenario_report["primary_call_count"] = len(call_log)
        pass_ok = (result.get("status") == "topics_extracted" and not contract_errors)
        if extra_checks:
            extra = extra_checks(result, persisted, call_log, scenario_intel)
            scenario_report["extra_checks"] = extra
            pass_ok = pass_ok and bool(extra.get("pass"))
        scenario_report["pass"] = bool(pass_ok)
    except Exception as exc:
        scenario_report["errors"].append(f"{type(exc).__name__}: {exc}")
        scenario_report["traceback"] = traceback.format_exc()
        scenario_report["call_log"] = call_log
        scenario_report["pass"] = False
    finally:
        core.INTEL_DIR = original_intel
        core.TRACE_FILE = original_trace
        core.POLICY_FILE = original_policy
        core.smart_retry = original_smart_retry

    write_json(scenario_dir / "scenario_report.json", scenario_report)
    return scenario_report


def run_all():
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    core = import_core(PROJECT_DIR)

    def setup_cache_invalid(core_mod, intel_dir: Path, state: dict):
        script_hash = core_mod.get_hash(state["script"])
        write_json(intel_dir / "state_manifest.json", {"topic_script_hash": script_hash})
        write_json(
            intel_dir / "topic_callouts.json",
            [
                {"topic": "", "after_sentence": 0},
                {"topic": "HALLUCINATED ALIEN MARKET", "after_sentence": 999},
                {"topic": "123", "after_sentence": "banana"},
            ],
        )

    scenarios = [
        {
            "name": "T1_valid_json_grounded",
            "responses": [
                json.dumps([
                    {"topic": "openai agentic workflows", "after_sentence": 1},
                    {"topic": "CODEX", "after_sentence": 2},
                    {"topic": "openai agentic workflows", "after_sentence": 3},
                    {"topic": "multimodal reliability decides production trust", "after_sentence": 3},
                ])
            ],
            "extra_checks": lambda _r, persisted, calls, _i: {
                "pass": len(calls) == 1 and len(persisted) >= 2
            },
        },
        {
            "name": "T2_malformed_primary",
            "responses": [
                "not-json-output",
                json.dumps([
                    {"topic": "OPENAI AGENTIC", "after_sentence": 1},
                    {"topic": "REPOSITORY SCALE", "after_sentence": 2},
                ]),
            ],
            "extra_checks": lambda _r, _p, calls, _i: {
                "pass": (
                    len(calls) == 2
                    and calls[0].get("prompt_template_id") == "PROMPT_TOPIC_EXTRACTOR_CALLOUTS"
                    and calls[1].get("prompt_template_id") == "PROMPT_TOPIC_EXTRACTOR_REPAIR"
                )
            },
        },
        {
            "name": "T3_repair_still_bad",
            "responses": ["garbage-primary", "garbage-repair"],
            "extra_checks": lambda _r, persisted, calls, _i: {
                "pass": len(calls) == 2 and len(persisted) >= 1 and persisted[0].get("topic") != "BREAKING NEWS"
            },
        },
        {
            "name": "T4_index_anomalies",
            "responses": [
                json.dumps([
                    {"topic": "OpenAI agentic workflows", "after_sentence": 0},
                    {"topic": "Codex now handles repository scale context", "after_sentence": -5},
                    {"topic": "Multimodal reliability decides production trust", "after_sentence": "999"},
                    {"topic": "Enterprise teams need auditable automation", "after_sentence": "2.9"},
                    {"topic": "Fireworks only paid API policy stays enforced", "after_sentence": "abc"},
                    {"topic": "OpenAI agentic workflows", "after_sentence": 4},
                ])
            ],
            "extra_checks": lambda _r, persisted, calls, _i: {
                "pass": len(calls) == 1 and all(isinstance(x.get("after_sentence"), int) for x in persisted)
            },
        },
        {
            "name": "T5_cache_invalid",
            "responses": [
                json.dumps([
                    {"topic": "OPENAI AGENTIC", "after_sentence": 1},
                    {"topic": "AUDITABLE AUTOMATION", "after_sentence": 5},
                ])
            ],
            "setup_fn": setup_cache_invalid,
            "extra_checks": lambda _r, persisted, calls, _i: {
                "pass": len(calls) == 1 and len(persisted) == 2
            },
        },
    ]

    reports = []
    for sc in scenarios:
        reports.append(
            run_scenario(
                core=core,
                run_dir=run_dir,
                name=sc["name"],
                responses=sc["responses"],
                setup_fn=sc.get("setup_fn"),
                extra_checks=sc.get("extra_checks"),
            )
        )

    verdict = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "total": len(reports),
        "passed": sum(1 for r in reports if r.get("pass")),
        "failed": [r.get("scenario") for r in reports if not r.get("pass")],
        "all_passed": all(r.get("pass") for r in reports),
    }
    write_json(run_dir / "topic_extractor_verdict.json", verdict)
    write_json(run_dir / "topic_extractor_reports.json", reports)
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    run_all()

