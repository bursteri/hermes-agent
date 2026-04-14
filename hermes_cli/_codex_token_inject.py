"""Non-interactive codex token injection for fork consumers (e.g. noste-core).

Reads {"access_token": "...", "refresh_token": "..."} JSON from stdin, persists
via hermes_cli.auth helpers, and writes model.provider=openai-codex into
config.yaml. Emits {"status":"ok"} on stdout, or {"status":"error","message":...}
with exit code 1.

Usage: python -m hermes_cli._codex_token_inject < tokens.json

Fork-only; not imported by upstream. Keep coupling to upstream limited to the
three symbols imported below so weekly upstream syncs only break if those are
renamed.
"""
from __future__ import annotations

import json
import os
import sys

from hermes_cli.auth import (
    DEFAULT_CODEX_BASE_URL,
    _save_codex_tokens,
    _update_config_for_provider,
)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
        tokens = {
            "access_token": str(payload["access_token"]),
            "refresh_token": str(payload["refresh_token"]),
        }
        if not tokens["access_token"] or not tokens["refresh_token"]:
            raise ValueError("access_token and refresh_token must be non-empty")
        _save_codex_tokens(tokens)
        base_url = os.getenv("HERMES_CODEX_BASE_URL", "").strip().rstrip("/") or DEFAULT_CODEX_BASE_URL
        _update_config_for_provider("openai-codex", base_url)
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        raise SystemExit(1)
    print(json.dumps({"status": "ok"}))


if __name__ == "__main__":
    main()
