"""
secret_store.py - Environment-backed secret storage for ChatBuddy.

Secrets are stored in environment variables / .env, never in config.json.
Legacy config-based secrets are migrated on load and scrubbed from disk.
"""

import os
from pathlib import Path

from dotenv import load_dotenv, set_key

ENV_FILE = Path(".env")
SECRET_KEYS = {
    "api_key": "API_KEY",
    "api_key_custom": "API_KEY_CUSTOM",
}


def load_environment() -> None:
    """Load environment variables from .env if present."""
    load_dotenv()


def get_secret(config_key: str) -> str:
    env_key = SECRET_KEYS[config_key]
    return os.getenv(env_key, "").strip()


def has_secret(config_key: str) -> bool:
    return bool(get_secret(config_key))


def set_secret(config_key: str, value: str) -> None:
    """Persist a secret to the local .env file and process environment."""
    env_key = SECRET_KEYS[config_key]
    clean_value = str(value).strip()
    if clean_value:
        set_key(str(ENV_FILE), env_key, clean_value)
    os.environ[env_key] = clean_value


def migrate_legacy_secrets(stored_config: dict | None) -> bool:
    """
    Move old config.json secrets into .env if they still exist there.

    Returns True when the config should be rewritten to scrub legacy keys.
    """
    if not isinstance(stored_config, dict):
        return False

    changed = False
    for config_key, env_key in SECRET_KEYS.items():
        legacy_value = str(stored_config.get(config_key) or "").strip()
        if not legacy_value:
            continue
        if not os.getenv(env_key, "").strip():
            set_secret(config_key, legacy_value)
        changed = True
    return changed


def scrub_config_secrets(config: dict) -> dict:
    """Return a copy of config with secret fields removed."""
    sanitized = dict(config)
    for config_key in SECRET_KEYS:
        sanitized.pop(config_key, None)
    return sanitized
