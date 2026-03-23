import argparse
import os
import sys

import requests


FIREWORKS_ENV_VAR = "FIREWORKS_API_KEY"
BFL_IMAGE_ENV_VAR = "BLF_FLUX2PRO"


def _mask(key: str) -> str:
    if len(key) >= 8:
        return f"{key[:4]}...{key[-4:]}"
    if len(key) >= 2:
        return f"{key[:2]}..."
    return "***"


def _load_required_key(env_var: str) -> str:
    key = str(os.getenv(env_var, "") or "").strip()
    if not key:
        print(f"[PREFLIGHT-ERROR] Missing env var: {env_var}")
        print(
            f'[PREFLIGHT-ERROR] Set once with: setx {env_var} "<your_key>" '
            "and restart terminal/app."
        )
        sys.exit(1)
    print(f"[PREFLIGHT-OK] {env_var} detected ({_mask(key)})")
    return key


def _ping_fireworks(key: str) -> int:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": "accounts/fireworks/models/kimi-k2p5",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }
    try:
        resp = requests.post(
            "https://api.fireworks.ai/inference/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            print("[PREFLIGHT-OK] Fireworks API ping succeeded.")
            return 0
        print(
            f"[PREFLIGHT-ERROR] Fireworks ping failed. "
            f"HTTP {resp.status_code}: {resp.text[:220]}"
        )
        return 2
    except Exception as exc:
        print(f"[PREFLIGHT-ERROR] Fireworks ping exception: {exc}")
        return 2


def _ping_bfl_image(key: str) -> int:
    headers = {"x-key": key}
    try:
        # Lightweight auth check without triggering generation billing:
        # valid key should return a regular API JSON response (often 200 with missing task status),
        # invalid key should return auth failure.
        resp = requests.get(
            "https://api.bfl.ai/v1/get_result",
            headers=headers,
            params={"id": "preflight_probe"},
            timeout=10,
        )
        if resp.status_code in (200, 404):
            print("[PREFLIGHT-OK] BFL image API key check succeeded.")
            return 0
        print(
            f"[PREFLIGHT-ERROR] BFL key check failed. "
            f"HTTP {resp.status_code}: {resp.text[:220]}"
        )
        return 2
    except Exception as exc:
        print(f"[PREFLIGHT-ERROR] BFL key check exception: {exc}")
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manual reasoning/image key preflight (env check + optional pings)."
    )
    parser.add_argument(
        "--ping",
        action="store_true",
        help="Perform optional live API pings after env-key detection.",
    )
    args = parser.parse_args()

    fireworks_key = _load_required_key(FIREWORKS_ENV_VAR)
    bfl_key = _load_required_key(BFL_IMAGE_ENV_VAR)
    if not args.ping:
        print("[PREFLIGHT] Env check only. Skipping network ping.")
        return 0
    fw_rc = _ping_fireworks(fireworks_key)
    bfl_rc = _ping_bfl_image(bfl_key)
    return 0 if fw_rc == 0 and bfl_rc == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
