"""
utils.py - Utility functions for ChatBuddy.
Mention stripping, message chunking, context formatting, and emoji resolution.
"""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Union

import discord

_TAMAGOTCHI_FOOTER_RE = re.compile(r"\n?> -# \*\*.*?\*\*(?:\n|$)", re.DOTALL)


@dataclass
class ContextEntry:
    timestamp: datetime
    display_name: str
    user_id: int
    content: str


def strip_mention(text: str, bot_id: int) -> str:
    """Remove the bot's mention tag(s) from the message text."""
    pattern = rf"<@!?{bot_id}>"
    return re.sub(pattern, "", text).strip()


def chunk_message(text: str, limit: int = 2000) -> List[str]:
    """
    Split *text* into chunks of at most *limit* characters.
    Prefers splitting at newlines, then spaces, to keep messages readable.
    """
    if not text:
        return []

    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break

        split_pos = text.rfind("\n", 0, limit)
        if split_pos == -1:
            split_pos = text.rfind(" ", 0, limit)
        if split_pos == -1:
            split_pos = limit

        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")

    return chunks


def strip_tamagotchi_footer(text: str) -> str:
    """Remove the compact visible tamagotchi footer from message text."""
    return _TAMAGOTCHI_FOOTER_RE.sub("\n", text).strip()


def _entry_content(entry: Union[discord.Message, ContextEntry]) -> str:
    if isinstance(entry, ContextEntry):
        return entry.content
    return entry.content


def _to_context_entry(entry: Union[discord.Message, ContextEntry]) -> ContextEntry:
    if isinstance(entry, ContextEntry):
        return entry
    return ContextEntry(
        timestamp=entry.created_at,
        display_name=entry.author.display_name,
        user_id=entry.author.id,
        content=strip_tamagotchi_footer(entry.content),
    )


async def collect_context_entries(
    channel: discord.abc.Messageable,
    limit: int,
    *,
    config: Optional[dict] = None,
    before: Optional[discord.Message] = None,
) -> List[Union[discord.Message, ContextEntry]]:
    fetch_limit = max(limit * 4, 120, 1)
    messages: List[discord.Message] = []
    try:
        async for msg in channel.history(limit=fetch_limit, before=before):
            messages.append(msg)
    except Exception as e:
        print(f"[Context] Failed to read channel history: {e}")
    messages.reverse()
    if len(messages) > limit:
        messages = messages[-limit:]
    return messages


def format_context(messages: List[Union[discord.Message, ContextEntry]], ce_enabled: bool = True) -> str:
    """
    Format a list of Discord messages into a rich context string.

    Each line:
        [YYYY-MM-DD HH:MM:SS] DisplayName (ID:123456789012345678): message content

    Including the user ID lets the LLM construct <@ID> mentions when instructed.
    Using raw `content` (not `clean_content`) preserves Discord formatting tokens
    such as <@id>, <:emoji:id>, etc. so the model sees how they actually appear.

    If *ce_enabled* is True, any message whose content is exactly "[ce]"
    (case-insensitive) acts as a context boundary - all messages before it
    (and the [ce] message itself) are discarded.
    """
    if ce_enabled:
        ce_index = None
        for i, msg in enumerate(messages):
            if _entry_content(msg).strip().lower() == "[ce]":
                ce_index = i
        if ce_index is not None:
            messages = messages[ce_index + 1:]

    lines: List[str] = [
        "[CONTEXT ORDER] Oldest to newest. The newest message is the final entry marked [LATEST]."
    ]
    for idx, msg in enumerate(messages):
        entry = _to_context_entry(msg)
        timestamp = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        latest_marker = "[LATEST] " if idx == len(messages) - 1 else ""
        lines.append(
            f"{latest_marker}[{timestamp}] {entry.display_name} (ID:{entry.user_id}): {entry.content}"
        )
    return "\n".join(lines)


def resolve_custom_emoji(text: str, guild: discord.Guild | None) -> str:
    """
    Replace custom emoji shortcodes in *text* with real Discord emoji markup.

    Scans for patterns like :emoji_name: and, if a matching custom emoji exists
    in the guild, replaces it with <:emoji_name:id> (or <a:emoji_name:id> for
    animated emoji). Standard Unicode emoji and unknown shortcodes are left
    untouched.

    If *guild* is None (e.g. DMs), the text is returned unchanged.
    """
    if guild is None or not guild.emojis:
        return text

    emoji_map = {e.name.lower(): e for e in guild.emojis}
    if not emoji_map:
        return text

    placeholder = "\x00EMOJI{}\x00"
    protected: list[str] = []

    def _protect(match: re.Match) -> str:
        protected.append(match.group(0))
        return placeholder.format(len(protected) - 1)

    text = re.sub(r"<a?:\w+:\d+>", _protect, text)

    def _replace(match: re.Match) -> str:
        name = match.group(1)
        if name.isdigit():
            return match.group(0)
        emoji = emoji_map.get(name.lower())
        if emoji is None:
            return match.group(0)
        if emoji.animated:
            return f"<a:{emoji.name}:{emoji.id}>"
        return f"<:{emoji.name}:{emoji.id}>"

    text = re.sub(r":([A-Za-z0-9_]{2,}):", _replace, text)

    for i, original in enumerate(protected):
        text = text.replace(placeholder.format(i), original)

    return text


def extract_thoughts(text: str) -> tuple[str, str | None]:
    """
    Extract content between <my-thoughts> and </my-thoughts> tags.

    Returns (clean_text, thoughts_text):
      - clean_text: visible response text with thought blocks removed
      - thoughts_text: concatenated inner content of all thought blocks
    """
    pattern = re.compile(
        r"<\s*my-thoughts\s*>(.*?)</\s*my-thoughts\s*>",
        re.DOTALL | re.IGNORECASE,
    )
    matches = pattern.findall(text)

    if not matches:
        return text, None

    thoughts_text = "\n".join(m.strip() for m in matches)
    clean_text = pattern.sub("", text).strip()
    return clean_text, thoughts_text


def extract_soul_updates(text: str) -> tuple[str, list[tuple[str, str, str]]]:
    """
    Extract soul tags directly from generated text.

    Returns:
      (clean_text, [(action, id, content), ...])
    """
    updates = []
    pattern = re.compile(
        r"\\?<\s*\\?!\s*"
        r"soul-(add-new|update|override|delete)"
        r"\s*\\?\[\s*(.+?)\s*\\?\]"
        r"(?:\s*:\s*(.*?))?"
        r"\s*(?:\\?!\s*)?\\?>",
        re.DOTALL | re.IGNORECASE,
    )

    for match in pattern.finditer(text):
        action = match.group(1).lower()
        entry_id = match.group(2).strip()
        content = match.group(3)
        updates.append((action, entry_id, content.strip() if content else ""))

    clean_text = pattern.sub("", text).strip()
    return clean_text, updates


def handle_soul_updates(response_text: str, config: dict) -> tuple[str, list[str]]:
    """
    Extract tags, enforce the soul size limit, and apply updates to soul.md.

    Returns (clean_text, logs).
    """
    clean_text, updates = extract_soul_updates(response_text)
    logs: list[str] = []

    if not config.get("soul_enabled", False) or not updates:
        return clean_text, logs

    soul_limit = config.get("soul_limit", 2000)
    soul_file = "soul.md"

    soul_data: Dict[str, str] = {}
    if os.path.exists(soul_file):
        try:
            with open(soul_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    soul_data = json.loads(content)
        except json.JSONDecodeError:
            print("[Soul] Converting legacy text to JSON entry '0'.")
            soul_data = {"0": content}
        except Exception as e:
            print(f"[Soul] Error reading soul file: {e}")

    made_changes = False
    for action, entry_id, content in updates:
        if not entry_id:
            continue

        previous_data = soul_data.copy()

        if action == "add-new":
            if entry_id in soul_data:
                soul_data[entry_id] += "\n" + content
                logs.append(f"**Appended to existing [{entry_id}] (via add-new)**:\n`{content}`")
            else:
                soul_data[entry_id] = content
                logs.append(f"**Added New [{entry_id}]**:\n`{content}`")
            made_changes = True

        elif action == "update":
            if entry_id in soul_data:
                soul_data[entry_id] += "\n" + content
                logs.append(f"**Updated [{entry_id}]**:\nAppended: `{content}`")
            else:
                soul_data[entry_id] = content
                logs.append(f"**Created [{entry_id}]**:\n`{content}`")
            made_changes = True

        elif action == "override":
            soul_data[entry_id] = content
            logs.append(f"**Overwrote [{entry_id}]**:\n`{content}`")
            made_changes = True

        elif action == "delete":
            if entry_id in soul_data:
                del soul_data[entry_id]
                logs.append(f"**Deleted [{entry_id}]**")
                made_changes = True

        if made_changes:
            new_json_str = json.dumps(soul_data, indent=2, ensure_ascii=False)
            if len(new_json_str) > soul_limit:
                soul_data = previous_data
                made_changes = False
                if logs:
                    logs.pop()
                print(f"[Soul] Update rejected: {len(new_json_str)} chars > {soul_limit} limit.")
                from config import save_config

                config["soul_error_turn"] = (
                    f"System Error: Failed to apply soul action '{action}' on ID '{entry_id}' because it exceeded the {soul_limit} "
                    f"character JSON file limit (attempted {len(new_json_str)} chars). "
                    "Faulty output rejected."
                )
                save_config(config)

    if made_changes:
        new_json_str = json.dumps(soul_data, indent=2, ensure_ascii=False)
        try:
            with open(soul_file, "w", encoding="utf-8") as f:
                f.write(new_json_str)
            print(f"[Soul] Updated soul.md ({len(new_json_str)} chars JSON).")
        except Exception as e:
            print(f"[Soul] Failed to write soul.md: {e}")

    return clean_text, logs


def extract_reminder_commands(text: str) -> tuple[str, list[tuple[str, str, str]]]:
    """
    Extract reminder and wake-time command tags from generated text.

    Recognised tag patterns:
        <!add-reminder : [datetime] [prompt]!>
        <!delete-reminder : [datetime] [prompt]!>
        <!add-auto-wake-time : [datetime] [prompt]!>
        <!delete-auto-wake-time : [datetime] [prompt]!>

    Markdown-escaped variants such as \\<\\! ... \\!\\> are also supported.
    """
    commands: list[tuple[str, str, str]] = []

    actions = r"(add-reminder|delete-reminder|add-auto-wake-time|delete-auto-wake-time)"
    dt_part = r"([\d]{2,4}[-/.][\d]{2}[-/.][\d]{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?)"
    prompt_part = r"(.+?)"

    pattern = re.compile(
        r"\\?<\s*\\?!\s*"
        + actions
        + r"\s*:?\s*"
        + r"\\?\[?\s*"
        + dt_part
        + r"\s*\\?\]?\s+"
        + r"\\?\[?\s*"
        + prompt_part
        + r"\s*\\?\]?"
        + r"\s*\\?!\s*\\?>",
        re.IGNORECASE | re.DOTALL,
    )

    for match in pattern.finditer(text):
        commands.append(
            (
                match.group(1).lower(),
                match.group(2).strip(),
                match.group(3).strip(),
            )
        )

    leftover = re.compile(
        r"\\?<\s*\\?!\s*(?:add-reminder|delete-reminder|add-auto-wake-time|delete-auto-wake-time)"
        r"[\s\S]*?\\?!\s*\\?>",
        re.IGNORECASE | re.DOTALL,
    )
    clean_text = leftover.sub("", pattern.sub("", text)).strip()
    return clean_text, commands
