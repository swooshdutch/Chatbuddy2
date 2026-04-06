"""
Helpers for the file-backed main system prompt template.
"""

import os

SYSTEM_PROMPT_TEMPLATE_FILE = "llm_sys_instruct.md"
DEFAULT_SYSTEM_PROMPT_TEMPLATE = "Replace this line with your system prompt."

BOTNAME_PLACEHOLDER = "<!BOTNAME!>"
BOTPERSONALITY_PLACEHOLDER = "<!BOTPERSONALITY!>"

DEFAULT_BOT_NAME = "Bot"
DEFAULT_BOT_PERSONALITY = "a playfull tamagochi bot"


def _normalise_prompt_text(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def ensure_system_prompt_template_file() -> None:
    """Create the main system prompt template file when it does not exist yet."""
    if os.path.exists(SYSTEM_PROMPT_TEMPLATE_FILE):
        return
    with open(SYSTEM_PROMPT_TEMPLATE_FILE, "w", encoding="utf-8") as f:
        f.write(DEFAULT_SYSTEM_PROMPT_TEMPLATE)


def read_system_prompt_template() -> str:
    """Read the stored main system prompt template from disk."""
    ensure_system_prompt_template_file()
    try:
        with open(SYSTEM_PROMPT_TEMPLATE_FILE, "r", encoding="utf-8") as f:
            return _normalise_prompt_text(f.read())
    except OSError:
        return DEFAULT_SYSTEM_PROMPT_TEMPLATE


def write_system_prompt_template(prompt: str) -> None:
    """Persist the main system prompt template to disk."""
    with open(SYSTEM_PROMPT_TEMPLATE_FILE, "w", encoding="utf-8") as f:
        f.write(_normalise_prompt_text(prompt))


def get_bot_name(config: dict | None = None) -> str:
    value = str((config or {}).get("bot_name", "") or "").strip()
    return value or DEFAULT_BOT_NAME


def get_bot_personality(config: dict | None = None) -> str:
    value = str((config or {}).get("bot_personality", "") or "").strip()
    return value or DEFAULT_BOT_PERSONALITY


def render_prompt_template(prompt: str, config: dict | None = None) -> str:
    """Render runtime prompt variables without mutating the stored template."""
    rendered = _normalise_prompt_text(prompt)
    rendered = rendered.replace(BOTNAME_PLACEHOLDER, get_bot_name(config))
    rendered = rendered.replace(
        BOTPERSONALITY_PLACEHOLDER,
        get_bot_personality(config),
    )
    return rendered


def migrate_legacy_system_prompt(legacy_prompt: str | None) -> bool:
    """
    Move an older config-stored system prompt into the template file when needed.

    Returns True when the file was updated.
    """
    prompt = _normalise_prompt_text(legacy_prompt).strip("\n")
    if not prompt.strip():
        return False

    if not os.path.exists(SYSTEM_PROMPT_TEMPLATE_FILE):
        write_system_prompt_template(prompt)
        return True

    current = read_system_prompt_template()
    if current.strip() in ("", DEFAULT_SYSTEM_PROMPT_TEMPLATE.strip()):
        write_system_prompt_template(prompt)
        return True

    return False
