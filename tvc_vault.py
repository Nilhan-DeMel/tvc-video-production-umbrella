import os
import sys
from typing import Dict, List, Tuple

from tvc_key_audit import log_api_key_lookup

# Cache keys by canonical secret name to avoid alias-fragmented cache entries.
_ACTIVE_KEY_CACHE: Dict[str, str] = {}
_ACTIVE_KEY_META: Dict[str, Dict[str, str]] = {}

_FIREWORKS_ENV_VAR = "FIREWORKS_API_KEY"
_FIREWORKS_CANONICAL_SECRET = _FIREWORKS_ENV_VAR
_FIREWORKS_SECRET_ALIASES = {"key_HGmChvaB", _FIREWORKS_ENV_VAR}

_BFL_IMAGE_ENV_VAR = "BLF_FLUX2PRO"
_BFL_IMAGE_ENV_FALLBACK = "BFL_API_KEY"
_BFL_IMAGE_CANONICAL_SECRET = _BFL_IMAGE_ENV_VAR
_BFL_IMAGE_SECRET_ALIASES = {_BFL_IMAGE_ENV_VAR, _BFL_IMAGE_ENV_FALLBACK}

_DISABLED_SECRETS = {"Gemini Dev"}


def _canonical_secret_for_alias(secret_alias: str) -> str:
    alias = str(secret_alias or "").strip()
    if alias in _FIREWORKS_SECRET_ALIASES:
        return _FIREWORKS_CANONICAL_SECRET
    if alias in _BFL_IMAGE_SECRET_ALIASES:
        return _BFL_IMAGE_CANONICAL_SECRET
    return ""


def _env_vars_for_canonical_secret(canonical_secret: str) -> List[str]:
    if canonical_secret == _FIREWORKS_CANONICAL_SECRET:
        return [_FIREWORKS_ENV_VAR]
    if canonical_secret == _BFL_IMAGE_CANONICAL_SECRET:
        return [_BFL_IMAGE_ENV_VAR, _BFL_IMAGE_ENV_FALLBACK]
    return []


def _read_windows_registry_env(env_var_name: str, scope: str) -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg  # type: ignore
    except Exception:
        return ""

    if scope == "user":
        hive = winreg.HKEY_CURRENT_USER
        subkey = r"Environment"
    elif scope == "machine":
        hive = winreg.HKEY_LOCAL_MACHINE
        subkey = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
    else:
        return ""

    try:
        with winreg.OpenKey(hive, subkey) as key_handle:
            value, _ = winreg.QueryValueEx(key_handle, env_var_name)
    except Exception:
        return ""
    return str(value or "").strip()


def _resolve_from_sources(env_var_names: List[str]) -> Tuple[str, str, str]:
    for env_var_name in env_var_names:
        key = str(os.getenv(env_var_name, "") or "").strip()
        if key:
            return key, env_var_name, "process"

    for scope in ("user", "machine"):
        for env_var_name in env_var_names:
            key = _read_windows_registry_env(env_var_name, scope)
            if key:
                return key, env_var_name, scope

    return "", "", ""


def _hydrate_process_env(canonical_secret: str, key_value: str) -> None:
    key = str(key_value or "").strip()
    if not key:
        return
    if canonical_secret == _FIREWORKS_CANONICAL_SECRET:
        os.environ[_FIREWORKS_ENV_VAR] = key
    elif canonical_secret == _BFL_IMAGE_CANONICAL_SECRET:
        os.environ[_BFL_IMAGE_ENV_VAR] = key
        os.environ[_BFL_IMAGE_ENV_FALLBACK] = key


def _record_lookup(
    *,
    secret_alias: str,
    outcome: str,
    key_value: str = "",
    cache_hit: bool = False,
    extra: Dict[str, str] = None,
) -> None:
    log_api_key_lookup(
        secret_alias=secret_alias,
        outcome=outcome,
        source="tvc_vault",
        key_value=key_value,
        cache_hit=cache_hit,
        stack_skip_modules={"tvc_vault"},
        extra=(extra or {}),
    )


def _missing_env_message(tried_env_vars: List[str]) -> str:
    tried = "|".join(tried_env_vars) if tried_env_vars else "UNKNOWN_ENV"
    first_env = tried_env_vars[0] if tried_env_vars else "UNKNOWN_ENV"
    return (
        f"[VAULT ERROR] Missing required env var(s): {tried}\n"
        f'[VAULT ERROR] Set once with: setx {first_env} "<your_key>" '
        "and restart terminal/app."
    )


def try_get_secret(secret_name: str) -> Dict[str, str]:
    """
    Resolve a secret without terminating the process.
    Resolution order: process env -> HKCU user env -> HKLM machine env.
    """
    lookup_name = str(secret_name or "").strip()

    if lookup_name in _DISABLED_SECRETS:
        _record_lookup(
            secret_alias=lookup_name,
            outcome="failure_disabled_secret",
            extra={"canonical_secret": ""},
        )
        return {
            "ok": False,
            "key": "",
            "error_code": "disabled_secret",
            "secret_alias": lookup_name,
            "canonical_secret": "",
            "resolved_env_var": "",
            "resolved_scope": "",
            "message": "'Gemini Dev' is disabled in Fireworks-only mode.",
        }

    canonical_secret = _canonical_secret_for_alias(lookup_name)
    if not canonical_secret:
        _record_lookup(
            secret_alias=lookup_name,
            outcome="failure_unsupported_secret",
            extra={"canonical_secret": ""},
        )
        return {
            "ok": False,
            "key": "",
            "error_code": "unsupported_secret",
            "secret_alias": lookup_name,
            "canonical_secret": "",
            "resolved_env_var": "",
            "resolved_scope": "",
            "message": f"Unsupported secret in Fireworks-only mode: {lookup_name}",
        }

    if canonical_secret in _ACTIVE_KEY_CACHE:
        key = _ACTIVE_KEY_CACHE[canonical_secret]
        meta = _ACTIVE_KEY_META.get(canonical_secret, {})
        extra = {
            "canonical_secret": canonical_secret,
            "resolved_env_var": str(meta.get("resolved_env_var", "") or ""),
            "resolved_scope": str(meta.get("resolved_scope", "cache") or "cache"),
        }
        _record_lookup(
            secret_alias=lookup_name,
            outcome="success_cache_hit",
            key_value=key,
            cache_hit=True,
            extra=extra,
        )
        print(
            f"[VAULT] Loaded CACHED {lookup_name} "
            f"(canonical={canonical_secret}, len={len(key)})"
        )
        return {
            "ok": True,
            "key": key,
            "error_code": "",
            "secret_alias": lookup_name,
            "canonical_secret": canonical_secret,
            "resolved_env_var": extra["resolved_env_var"],
            "resolved_scope": "cache",
            "message": "cache_hit",
        }

    env_var_names = _env_vars_for_canonical_secret(canonical_secret)
    key, resolved_env_var, resolved_scope = _resolve_from_sources(env_var_names)
    if not key:
        _record_lookup(
            secret_alias=lookup_name,
            outcome="failure_missing_env",
            extra={
                "canonical_secret": canonical_secret,
                "resolved_env_var": "",
                "resolved_scope": "",
                "tried_env_vars": "|".join(env_var_names),
            },
        )
        return {
            "ok": False,
            "key": "",
            "error_code": "missing_env",
            "secret_alias": lookup_name,
            "canonical_secret": canonical_secret,
            "resolved_env_var": "",
            "resolved_scope": "",
            "tried_env_vars": "|".join(env_var_names),
            "message": _missing_env_message(env_var_names),
        }

    _hydrate_process_env(canonical_secret, key)
    _ACTIVE_KEY_CACHE[canonical_secret] = key
    _ACTIVE_KEY_META[canonical_secret] = {
        "resolved_env_var": resolved_env_var,
        "resolved_scope": resolved_scope,
    }
    _record_lookup(
        secret_alias=lookup_name,
        outcome="success_env",
        key_value=key,
        cache_hit=False,
        extra={
            "canonical_secret": canonical_secret,
            "resolved_env_var": resolved_env_var,
            "resolved_scope": resolved_scope,
        },
    )
    print(
        f"[VAULT] Loaded ACTIVE {lookup_name} "
        f"(canonical={canonical_secret}, source={resolved_scope}:{resolved_env_var}, len={len(key)})"
    )
    return {
        "ok": True,
        "key": key,
        "error_code": "",
        "secret_alias": lookup_name,
        "canonical_secret": canonical_secret,
        "resolved_env_var": resolved_env_var,
        "resolved_scope": resolved_scope,
        "message": "resolved",
    }


def get_secret(secret_name: str) -> str:
    """
    Strict resolver for runtime callsites that must fail-closed.
    """
    result = try_get_secret(secret_name)
    if result.get("ok"):
        return str(result.get("key", "") or "")

    error_code = str(result.get("error_code", "") or "")
    if error_code == "disabled_secret":
        print(
            "[VAULT ERROR] 'Gemini Dev' is disabled in Fireworks-only mode. "
            "Use Fireworks-only workflows."
        )
    elif error_code == "unsupported_secret":
        print(f"[VAULT ERROR] Unsupported secret in Fireworks-only mode: {secret_name}")
    elif error_code == "missing_env":
        print(str(result.get("message", _missing_env_message([]))))
    else:
        print(f"[VAULT ERROR] Secret resolution failed: {secret_name} ({error_code})")
    sys.exit(1)


if __name__ == "__main__":
    # Test loader
    test_key = get_secret("key_HGmChvaB")
    print("Vault loader functional.")

