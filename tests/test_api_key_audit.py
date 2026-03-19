import builtins
import json
import os

import pytest

import tvc_key_audit
import tvc_vault


def _read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _reset_vault_cache():
    tvc_vault._ACTIVE_KEY_CACHE.clear()
    tvc_vault._ACTIVE_KEY_META.clear()


def test_get_secret_logs_success_and_cache_hit(monkeypatch, tmp_path):
    log_path = tmp_path / "api_key_usage.log"
    monkeypatch.setattr(tvc_key_audit, "API_KEY_LOG_PATH", log_path)
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw_test_success_cache_123456")
    _reset_vault_cache()

    first = tvc_vault.get_secret("key_HGmChvaB")
    second = tvc_vault.get_secret("key_HGmChvaB")

    assert first == second
    rows = _read_jsonl(log_path)
    assert len(rows) >= 2

    env_row = rows[-2]
    cache_row = rows[-1]

    assert env_row["outcome"] == "success_env"
    assert cache_row["outcome"] == "success_cache_hit"
    assert cache_row["cache_hit"] is True
    assert env_row["secret_alias"] == "key_HGmChvaB"
    assert env_row["key_fingerprint_sha256_12"]
    assert "fw_test_success_cache_123456" not in json.dumps(rows)
    assert "test:" in str(cache_row["reason"])
    assert str(cache_row["caller_file"]).endswith("test_api_key_audit.py")


def test_get_secret_missing_env_logs_before_exit(monkeypatch, tmp_path):
    log_path = tmp_path / "api_key_usage.log"
    monkeypatch.setattr(tvc_key_audit, "API_KEY_LOG_PATH", log_path)
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    monkeypatch.setattr(tvc_vault, "_read_windows_registry_env", lambda env_var_name, scope: "")
    _reset_vault_cache()

    with pytest.raises(SystemExit) as exc:
        tvc_vault.get_secret("key_HGmChvaB")

    assert exc.value.code == 1
    rows = _read_jsonl(log_path)
    assert rows
    last = rows[-1]
    assert last["outcome"] == "failure_missing_env"
    assert last["secret_alias"] == "key_HGmChvaB"
    assert "test:" in str(last["reason"])


def test_try_get_secret_resolves_user_scope_and_hydrates_process_env(monkeypatch, tmp_path):
    log_path = tmp_path / "api_key_usage.log"
    monkeypatch.setattr(tvc_key_audit, "API_KEY_LOG_PATH", log_path)
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    _reset_vault_cache()

    def _fake_registry(env_var_name, scope):
        if scope == "user" and env_var_name == "FIREWORKS_API_KEY":
            return "fw_user_scope_key_123456"
        return ""

    monkeypatch.setattr(tvc_vault, "_read_windows_registry_env", _fake_registry)
    result = tvc_vault.try_get_secret("key_HGmChvaB")
    assert result["ok"] is True
    assert result["resolved_scope"] == "user"
    assert result["resolved_env_var"] == "FIREWORKS_API_KEY"
    assert str(os.getenv("FIREWORKS_API_KEY", "")) == "fw_user_scope_key_123456"
    rows = _read_jsonl(log_path)
    assert rows[-1]["outcome"] == "success_env"
    assert rows[-1].get("extra", {}).get("resolved_scope") == "user"


def test_try_get_secret_resolves_machine_scope_when_user_missing(monkeypatch, tmp_path):
    log_path = tmp_path / "api_key_usage.log"
    monkeypatch.setattr(tvc_key_audit, "API_KEY_LOG_PATH", log_path)
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    _reset_vault_cache()

    def _fake_registry(env_var_name, scope):
        if scope == "machine" and env_var_name == "FIREWORKS_API_KEY":
            return "fw_machine_scope_key_123456"
        return ""

    monkeypatch.setattr(tvc_vault, "_read_windows_registry_env", _fake_registry)
    result = tvc_vault.try_get_secret("key_HGmChvaB")
    assert result["ok"] is True
    assert result["resolved_scope"] == "machine"
    rows = _read_jsonl(log_path)
    assert rows[-1].get("extra", {}).get("resolved_scope") == "machine"


def test_get_secret_blf_image_key_logs_success(monkeypatch, tmp_path):
    log_path = tmp_path / "api_key_usage.log"
    monkeypatch.setattr(tvc_key_audit, "API_KEY_LOG_PATH", log_path)
    monkeypatch.setenv("BLF_FLUX2PRO", "bfl_test_image_key_123456")
    _reset_vault_cache()

    key = tvc_vault.get_secret("BLF_FLUX2PRO")

    assert key == "bfl_test_image_key_123456"
    rows = _read_jsonl(log_path)
    assert rows
    last = rows[-1]
    assert last["outcome"] == "success_env"
    assert last["secret_alias"] == "BLF_FLUX2PRO"
    assert last["key_fingerprint_sha256_12"]
    assert "bfl_test_image_key_123456" not in json.dumps(rows)


def test_get_secret_blf_image_accepts_bfl_api_key_alias(monkeypatch, tmp_path):
    log_path = tmp_path / "api_key_usage.log"
    monkeypatch.setattr(tvc_key_audit, "API_KEY_LOG_PATH", log_path)
    monkeypatch.delenv("BLF_FLUX2PRO", raising=False)
    monkeypatch.setenv("BFL_API_KEY", "bfl_alias_key_123456")
    _reset_vault_cache()

    key = tvc_vault.get_secret("BLF_FLUX2PRO")

    assert key == "bfl_alias_key_123456"
    rows = _read_jsonl(log_path)
    assert rows
    last = rows[-1]
    assert last["outcome"] == "success_env"
    assert last["secret_alias"] == "BLF_FLUX2PRO"
    assert last.get("extra", {}).get("resolved_env_var") == "BFL_API_KEY"
    assert str(os.getenv("BLF_FLUX2PRO", "")) == "bfl_alias_key_123456"


def test_get_secret_blf_image_prefers_blf_flux2pro_when_both_present(monkeypatch, tmp_path):
    log_path = tmp_path / "api_key_usage.log"
    monkeypatch.setattr(tvc_key_audit, "API_KEY_LOG_PATH", log_path)
    monkeypatch.setenv("BLF_FLUX2PRO", "bfl_primary_key_123456")
    monkeypatch.setenv("BFL_API_KEY", "bfl_secondary_key_654321")
    _reset_vault_cache()

    key = tvc_vault.get_secret("BLF_FLUX2PRO")

    assert key == "bfl_primary_key_123456"
    rows = _read_jsonl(log_path)
    assert rows
    last = rows[-1]
    assert last["outcome"] == "success_env"
    assert last.get("extra", {}).get("resolved_env_var") == "BLF_FLUX2PRO"


def test_get_secret_blf_image_missing_env_logs_before_exit(monkeypatch, tmp_path):
    log_path = tmp_path / "api_key_usage.log"
    monkeypatch.setattr(tvc_key_audit, "API_KEY_LOG_PATH", log_path)
    monkeypatch.delenv("BLF_FLUX2PRO", raising=False)
    monkeypatch.delenv("BFL_API_KEY", raising=False)
    monkeypatch.setattr(tvc_vault, "_read_windows_registry_env", lambda env_var_name, scope: "")
    _reset_vault_cache()

    with pytest.raises(SystemExit) as exc:
        tvc_vault.get_secret("BLF_FLUX2PRO")

    assert exc.value.code == 1
    rows = _read_jsonl(log_path)
    assert rows
    last = rows[-1]
    assert last["outcome"] == "failure_missing_env"
    assert last["secret_alias"] == "BLF_FLUX2PRO"


def test_log_retry_then_success(monkeypatch, tmp_path):
    log_path = tmp_path / "api_key_usage.log"
    monkeypatch.setattr(tvc_key_audit, "API_KEY_LOG_PATH", log_path)

    state = {"count": 0}
    real_open = builtins.open

    def flaky_open(*args, **kwargs):
        target = str(args[0]) if args else ""
        if target == str(log_path):
            state["count"] += 1
            if state["count"] < 3:
                raise OSError("simulated lock")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)

    ok = tvc_key_audit.log_api_key_lookup(
        secret_alias="key_HGmChvaB",
        outcome="success_env",
        source="unit_test",
        key_value="fw_test_retry_123456",
        retries=3,
        retry_delay_s=0.0,
    )
    assert ok is True
    assert state["count"] == 3
    rows = _read_jsonl(log_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "success_env"
