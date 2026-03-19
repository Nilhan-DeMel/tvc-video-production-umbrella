import hashlib
import inspect
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parent
API_KEY_LOG_PATH = PROJECT_ROOT / "Evidence" / "api_key_usage.log"


def _fingerprint_key(key_value: Optional[str]) -> str:
    key = str(key_value or "").strip()
    if not key:
        return ""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return digest[:12]


def _resolve_caller(stack_skip_modules: Optional[set] = None) -> Dict[str, Any]:
    skip = set(stack_skip_modules or set())
    skip.add("tvc_key_audit")
    frames = inspect.stack()[2:]
    for frame in frames:
        module = inspect.getmodule(frame.frame)
        module_name = module.__name__ if module else ""
        file_name = frame.filename or ""
        if module_name in skip:
            continue
        if Path(file_name).name == "tvc_key_audit.py":
            continue
        return {
            "module": module_name,
            "file": file_name,
            "function": frame.function,
            "line": int(frame.lineno),
        }
    return {"module": "", "file": "", "function": "", "line": 0}


def _auto_reason(caller: Dict[str, Any]) -> str:
    file_name = Path(str(caller.get("file", "") or "")).name.lower()
    function = str(caller.get("function", "") or "")
    file_path = str(caller.get("file", "") or "").lower()

    if function == "<module>":
        phase = "module_import"
    else:
        phase = "function_call"

    if "evidence" in file_path:
        context = "evidence_runner"
    elif "/tests/" in file_path.replace("\\", "/") or file_name.startswith("test_") or file_name.endswith("_test.py"):
        context = "test"
    elif "smoke" in file_name:
        context = "smoke"
    else:
        context = "runtime"

    return f"{context}:{phase}"


def log_api_key_lookup(
    *,
    secret_alias: str,
    outcome: str,
    source: str,
    key_value: Optional[str] = None,
    cache_hit: bool = False,
    reason: str = "",
    stack_skip_modules: Optional[set] = None,
    extra: Optional[Dict[str, Any]] = None,
    retries: int = 3,
    retry_delay_s: float = 0.05,
) -> bool:
    caller = _resolve_caller(stack_skip_modules=stack_skip_modules)
    resolved_reason = str(reason or "").strip() or _auto_reason(caller)
    record = {
        "timestamp_local": datetime.now().astimezone().isoformat(timespec="seconds"),
        "event": "api_key_lookup",
        "secret_alias": str(secret_alias or ""),
        "outcome": str(outcome or ""),
        "reason": resolved_reason,
        "source": str(source or ""),
        "cache_hit": bool(cache_hit),
        "key_fingerprint_sha256_12": _fingerprint_key(key_value),
        "pid": int(os.getpid()),
        "caller_module": str(caller.get("module", "") or ""),
        "caller_file": str(caller.get("file", "") or ""),
        "caller_function": str(caller.get("function", "") or ""),
        "caller_line": int(caller.get("line", 0) or 0),
    }
    if extra:
        record["extra"] = extra

    API_KEY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    attempts = max(1, int(retries))
    for idx in range(attempts):
        try:
            with open(API_KEY_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=True) + "\n")
            return True
        except Exception as exc:
            if idx < attempts - 1:
                time.sleep(float(retry_delay_s) * (idx + 1))
                continue
            print(
                f"[KEY-AUDIT WARN] Unable to write API key audit log after {attempts} attempts: {exc}",
                file=sys.stderr,
            )
            return False
    return False
