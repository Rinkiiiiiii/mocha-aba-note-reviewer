"""
Local, on-device app configuration.

Stores the OpenAI API key in a small JSON file in the user's own home
directory — never in this repo, never bundled into a delivered zip, never
written to any project doc or synced source. It's used only as the
Authorization header for requests the user has already chosen to make to
their configured AI backend (see core/ai_client.py's HostedChatClient).

The file is written with owner-only permissions (chmod 600) on platforms
that support it. This is standard "store a local secret in the user's own
config dir" practice — the same trust boundary as an SSH key or a git
credential file — not a compliance control by itself.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional

_APP_DIR_NAME = ".mocha_aba_reviewer"
_CONFIG_FILENAME = "config.json"

# Fixed for now per the architecture decision (see architecture-decisions.md):
# GPT-5.6 Terra, validated against Luna/Sol with live tests. Revisit in code
# if that decision changes; no UI toggle for it yet by deliberate choice.
DEFAULT_MODEL = "gpt-5.6-terra"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def config_dir() -> Path:
    """A function (not a module constant) so tests can monkeypatch it to a
    tmp_path instead of touching the real home directory."""
    return Path(os.path.expanduser("~")) / _APP_DIR_NAME


def config_path() -> Path:
    return config_dir() / _CONFIG_FILENAME


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_config(data: dict) -> None:
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = config_path()
    path.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass  # best-effort; some platforms/filesystems don't support chmod


def get_api_key() -> Optional[str]:
    return load_config().get("api_key") or None


def get_model() -> str:
    return load_config().get("model") or DEFAULT_MODEL


def get_base_url() -> str:
    return load_config().get("base_url") or DEFAULT_BASE_URL


def save_api_key(api_key: str) -> None:
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("API key cannot be empty.")
    data = load_config()
    data["api_key"] = api_key
    _write_config(data)


def clear_api_key() -> None:
    data = load_config()
    data.pop("api_key", None)
    _write_config(data)


def mask_api_key(api_key: str) -> str:
    """Never show the full key back in the UI once saved — only enough to
    recognize which key is configured."""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:5]}...{api_key[-4:]}"
