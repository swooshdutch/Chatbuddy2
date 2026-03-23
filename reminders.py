"""
reminders.py — Reminder & auto-wake background task for ChatBuddy.

Manages two kinds of scheduled entries stored in reminders.json:
  • reminders  — user- or bot-created, fire once and post the prompt into
                 the configured reminder channel as AI-generated input.
  • wake_times — bot-created self-prompts, behave identically but are
                 marked separately so the bot can distinguish them.

When an entry's datetime is reached the manager calls generate() with
the entry's prompt, posts the response, and deletes the entry.
"""

import asyncio
import io
import json
import os
import re
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import tasks

from config import save_config
from utils import (
    format_context,
    chunk_message,
    resolve_custom_emoji,
    extract_thoughts,
    extract_reminder_commands,
)
from tamagotchi import TamagotchiView, append_tamagotchi_footer

REMINDERS_FILE = "reminders.json"

# ── multi-format datetime parsing ─────────────────────────────────────────────

# Accepted formats (tried in order):
DT_FORMATS = [
    "%d-%m-%y %H:%M",       # dd-mm-yy HH:MM   (canonical)
    "%d-%m-%Y %H:%M",       # dd-mm-YYYY HH:MM
    "%Y-%m-%d %H:%M",       # YYYY-MM-DD HH:MM  (ISO)
    "%Y-%m-%d %H:%M:%S",    # YYYY-MM-DD HH:MM:SS (ISO with seconds)
    "%d/%m/%y %H:%M",       # dd/mm/yy HH:MM
    "%d/%m/%Y %H:%M",       # dd/mm/YYYY HH:MM
    "%d.%m.%y %H:%M",       # dd.mm.yy HH:MM
    "%d.%m.%Y %H:%M",       # dd.mm.YYYY HH:MM
]

# Canonical storage format — we normalise everything to this on save.
DT_STORAGE = "%d-%m-%y %H:%M"


def _parse_dt(dt_str: str) -> datetime | None:
    """Parse a datetime string in any of the accepted formats, or None."""
    cleaned = dt_str.strip()
    for fmt in DT_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _normalise_dt(dt_str: str) -> str:
    """Try to normalise *dt_str* to canonical dd-mm-yy HH:MM.  Passthrough on fail."""
    parsed = _parse_dt(dt_str)
    if parsed is None:
        return dt_str.strip()
    return parsed.strftime(DT_STORAGE)


# ── persistence helpers ───────────────────────────────────────────────────────

def _load_reminders() -> dict:
    """Read reminders.json from disk, returning a safe default if missing."""
    if not os.path.exists(REMINDERS_FILE):
        return {"reminders": {}, "wake_times": {}}
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("reminders", {})
        data.setdefault("wake_times", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"reminders": {}, "wake_times": {}}


def _save_reminders(data: dict) -> None:
    """Atomically write reminders.json to disk."""
    tmp = REMINDERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, REMINDERS_FILE)


# ── public data helpers (used by gemini_api for context injection) ─────────

def get_all_reminders_text() -> str:
    """
    Return a human-readable block listing every reminder and wake-time.
    Designed to be injected into the system prompt so the bot sees them.
    """
    data = _load_reminders()
    lines: list[str] = []

    reminders = data.get("reminders", {})
    wake_times = data.get("wake_times", {})

    if not reminders and not wake_times:
        return "(no reminders or wake-times set)"

    if reminders:
        lines.append("REMINDERS:")
        for name, entry in reminders.items():
            lines.append(f"  • [{name}] at {entry['datetime']} — {entry['prompt']}")

    if wake_times:
        lines.append("AUTO-WAKE TIMES:")
        for name, entry in wake_times.items():
            lines.append(f"  • [{name}] at {entry['datetime']} — {entry['prompt']}")

    return "\n".join(lines)


# ── manager class ─────────────────────────────────────────────────────────────

class ReminderManager:
    """Manages the reminder check loop and CRUD operations."""

    def __init__(self, bot, config: dict):
        self.bot = bot
        self.config = config
        self._task: tasks.Loop | None = None

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(self):
        """Start (or restart) the 30-second check loop."""
        self.stop()
        if not self.config.get("reminders_enabled"):
            return

        @tasks.loop(seconds=30)
        async def _reminder_loop():
            await self._tick()

        @_reminder_loop.before_loop
        async def _before():
            await self.bot.wait_until_ready()

        self._task = _reminder_loop
        self._task.start()

    def stop(self):
        """Cancel the running loop if any."""
        if self._task and self._task.is_running():
            self._task.cancel()
        self._task = None

    # ── CRUD ───────────────────────────────────────────────────────────

    def add_reminder(self, name: str, dt_str: str, prompt: str, channel_id: str = "") -> str | None:
        """
        Add a reminder.  Returns None on success or an error string.
        The datetime is normalised before storage.
        """
        parsed = _parse_dt(dt_str)
        if parsed is None:
            return f"Invalid date/time format: `{dt_str}`. Expected e.g. `dd-mm-yy HH:MM` or `YYYY-MM-DD HH:MM`."
        normalised = parsed.strftime(DT_STORAGE)

        data = _load_reminders()
        if name in data["reminders"]:
            return f"A reminder named **{name}** already exists. Delete it first or choose another name."
        entry = {"datetime": normalised, "prompt": prompt}
        if channel_id:
            entry["channel_id"] = channel_id
        data["reminders"][name] = entry
        _save_reminders(data)
        return None

    def delete_reminder(self, name: str) -> str | None:
        """Delete a reminder by name.  Returns None on success or an error string."""
        data = _load_reminders()
        if name not in data["reminders"]:
            return f"No reminder named **{name}** found."
        del data["reminders"][name]
        _save_reminders(data)
        return None

    def add_wake_time(self, name: str, dt_str: str, prompt: str, channel_id: str = "") -> str | None:
        """Add an auto-wake-time.  Returns None on success or an error string."""
        parsed = _parse_dt(dt_str)
        if parsed is None:
            return f"Invalid date/time format: `{dt_str}`. Expected e.g. `dd-mm-yy HH:MM` or `YYYY-MM-DD HH:MM`."
        normalised = parsed.strftime(DT_STORAGE)

        data = _load_reminders()
        if name in data["wake_times"]:
            return f"A wake-time named **{name}** already exists. Delete it first or choose another name."
        entry = {"datetime": normalised, "prompt": prompt}
        if channel_id:
            entry["channel_id"] = channel_id
        data["wake_times"][name] = entry
        _save_reminders(data)
        return None

    def delete_wake_time(self, name: str) -> str | None:
        """Delete an auto-wake-time by name.  Returns None on success or error."""
        data = _load_reminders()
        if name not in data["wake_times"]:
            return f"No wake-time named **{name}** found."
        del data["wake_times"][name]
        _save_reminders(data)
        return None

    # ── logging helper ────────────────────────────────────────────────

    async def _log(self, message: str):
        """Send a log message to the configured reminder log channel, if any."""
        log_ch_id = self.config.get("reminder_log_channel_id")
        if not log_ch_id:
            return
        ch = self.bot.get_channel(int(log_ch_id))
        if ch is not None:
            try:
                await ch.send(message)
            except Exception:
                pass  # don't crash the loop on log failures

    # ── core tick ──────────────────────────────────────────────────────

    async def _tick(self):
        """Check all reminders / wake-times and fire any that are due."""
        if not self.config.get("reminders_enabled"):
            return

        # We need at least a default output channel
        default_ch_id = self.config.get("reminders_channel_id")

        now = datetime.now()  # naive local time — matches the dd-mm-yy HH:MM input
        data = _load_reminders()
        fired_any = False

        # ── process reminders ─────────────────────────────────────────
        fired_reminders: list[str] = []
        for name, entry in list(data["reminders"].items()):
            dt = _parse_dt(entry["datetime"])
            if dt is None:
                continue
            if now >= dt:
                fired_reminders.append(name)
                output_ch_id = entry.get("channel_id") or default_ch_id
                if output_ch_id:
                    channel = self.bot.get_channel(int(output_ch_id))
                    if channel is not None:
                        await self._fire_entry(
                            channel, entry["prompt"], name, kind="reminder"
                        )
                fired_any = True

        for name in fired_reminders:
            data["reminders"].pop(name, None)

        # ── process wake-times ────────────────────────────────────────
        fired_wakes: list[str] = []
        for name, entry in list(data["wake_times"].items()):
            dt = _parse_dt(entry["datetime"])
            if dt is None:
                continue
            if now >= dt:
                fired_wakes.append(name)
                output_ch_id = entry.get("channel_id") or default_ch_id
                if output_ch_id:
                    channel = self.bot.get_channel(int(output_ch_id))
                    if channel is not None:
                        await self._fire_entry(
                            channel, entry["prompt"], name, kind="wake-time"
                        )
                fired_any = True

        for name in fired_wakes:
            data["wake_times"].pop(name, None)

        if fired_any:
            _save_reminders(data)

    # ── fire a single entry ───────────────────────────────────────────

    async def _fire_entry(
        self,
        channel: discord.TextChannel,
        prompt: str,
        entry_name: str,
        kind: str = "reminder",
    ):
        """
        Generate a bot response using *prompt* as input and post it into
        *channel*.  Mirrors the normal response flow (SoC, soul, emoji, audio).
        """
        try:
            from gemini_api import generate  # lazy to avoid circular import
            tama_manager = getattr(self.bot, "tama_manager", None)
            if self.config.get("tama_enabled", False) and tama_manager:
                tama_manager.record_interaction()

            # Gather recent channel context so the bot has conversational awareness
            history_limit = self.config.get("chat_history_limit", 30)
            history_messages: list[discord.Message] = []
            async for msg in channel.history(limit=history_limit):
                history_messages.append(msg)
            history_messages.reverse()

            context = format_context(history_messages, ce_enabled=True)

            # SoC context injection
            soc_context_enabled = self.config.get("soc_context_enabled", False)
            soc_channel_id = self.config.get("soc_channel_id")
            if soc_context_enabled and soc_channel_id:
                soc_count = self.config.get("soc_context_count", 10)
                soc_ch = self.bot.get_channel(int(soc_channel_id))
                if soc_ch is not None:
                    soc_msgs: list[discord.Message] = []
                    async for m in soc_ch.history(limit=soc_count):
                        soc_msgs.append(m)
                    soc_msgs.reverse()
                    # Apply [ce] cutoff
                    ce_idx = None
                    for i, m in enumerate(soc_msgs):
                        if m.content.strip().lower() == "[ce]":
                            ce_idx = i
                    if ce_idx is not None:
                        soc_msgs = soc_msgs[ce_idx + 1 :]
                    if soc_msgs:
                        soc_lines = []
                        for m in soc_msgs:
                            ts = m.created_at.strftime("%Y-%m-%d %H:%M:%S")
                            soc_lines.append(f"[{ts}] {m.content}")
                        context += (
                            "\n[YOUR PREVIOUS THOUGHTS]\n"
                            + "\n".join(soc_lines)
                            + "\n[END YOUR PREVIOUS THOUGHTS]\n"
                        )

            # Build the input prompt — tell the bot this is a triggered event
            if kind == "wake-time":
                full_prompt = (
                    f"[AUTO-WAKE TRIGGERED — entry '{entry_name}']\n{prompt}"
                )
            else:
                full_prompt = (
                    f"[REMINDER TRIGGERED — entry '{entry_name}']\n{prompt}"
                )

            response_text, audio_bytes, soul_logs, reminder_cmds = await generate(
                prompt=full_prompt,
                context=context,
                config=self.config,
            )

            # Tamagotchi: deplete stats after inference (no emoji consumption — bot-initiated)
            is_dead = False
            if self.config.get("tama_enabled", False):
                from tamagotchi import deplete_stats, broadcast_death
                death_msg = deplete_stats(self.config)
                if death_msg:
                    response_text = (response_text + "\n\n" + death_msg) if response_text else death_msg
                    is_dead = True

            # Process reminder/wake-time tags the bot may have included
            response_text, new_cmds = extract_reminder_commands(response_text)
            if new_cmds:
                await self._apply_commands(new_cmds, source_channel_id=str(channel.id))

            # SoC thought extraction
            soc_enabled = self.config.get("soc_enabled", False)
            clean_text, thoughts_text = extract_thoughts(response_text)
            if thoughts_text and soc_enabled and soc_channel_id:
                thought_ch = self.bot.get_channel(int(soc_channel_id))
                if thought_ch is not None:
                    for c in chunk_message(thoughts_text):
                        await thought_ch.send(c)
            response_text = clean_text

            # Resolve custom emoji
            response_text = resolve_custom_emoji(response_text, channel.guild)

            # Send audio if present
            if audio_bytes:
                audio_file = discord.File(
                    fp=io.BytesIO(audio_bytes), filename="reminder.wav"
                )
                await channel.send(file=audio_file)

            # Send text response
            if response_text:
                kind_label = "⏰ Reminder" if kind == "reminder" else "🔔 Auto-Wake"
                # Tamagotchi: append stats footer if there is visible text
                tama_view = None
                tama_manager = getattr(self.bot, "tama_manager", None)
                if self.config.get("tama_enabled", False) and tama_manager:
                    tama_view = TamagotchiView(self.config, tama_manager)
                    response_text = append_tamagotchi_footer(response_text, self.config, tama_manager)
                footer = f"\n-# {kind_label}: *{entry_name}*"
                chunks = chunk_message(response_text)
                chunks[-1] += footer
                for i, chunk in enumerate(chunks):
                    await channel.send(chunk, view=tama_view if i == len(chunks) - 1 else None)

            # Soul logs
            if soul_logs and self.config.get("soul_channel_enabled"):
                ch_id = self.config.get("soul_channel_id")
                if ch_id:
                    soul_ch = self.bot.get_channel(int(ch_id))
                    if soul_ch:
                        joined_logs = "\n".join(soul_logs)
                        for log_chunk in chunk_message(joined_logs, limit=1900):
                            await soul_ch.send(f"**🧠 Soul Updates:**\n{log_chunk}")

            if is_dead:
                await broadcast_death(self.bot, self.config)

            # Log the firing
            await self._log(f"🔔 **Fired {kind}** `{entry_name}` in {channel.mention}")

            print(f"[Reminders] Fired {kind} '{entry_name}'.")

        except Exception as e:
            print(f"[Reminders] Error firing {kind} '{entry_name}': {e}")

    # ── apply bot-generated reminder commands ─────────────────────────

    async def _apply_commands(self, commands: list[tuple[str, str, str]], source_channel_id: str = ""):
        """
        Process commands extracted from bot output tags.
        Each command is (action, datetime_str, prompt_str).
        Actions: add-reminder, delete-reminder, add-auto-wake-time, delete-auto-wake-time

        source_channel_id: the channel_id the bot was responding in, stored with new entries.
        """
        default_ch = source_channel_id or self.config.get("reminders_channel_id", "")

        for action, dt_str, prompt_str in commands:
            # Normalise datetime for storage
            normalised = _normalise_dt(dt_str)

            # Auto-generate a name from the datetime + first words of prompt
            auto_name = f"{normalised}_{prompt_str[:20]}".replace(" ", "_").replace(":", "-")

            if action == "add-reminder":
                err = self.add_reminder(auto_name, dt_str, prompt_str, channel_id=default_ch)
                if err:
                    print(f"[Reminders] Bot add-reminder failed: {err}")
                else:
                    print(f"[Reminders] Bot added reminder '{auto_name}'.")
                    await self._log(
                        f"📝 **Bot registered reminder** `{auto_name}`\n"
                        f"⏱️ Fires: `{normalised}`\n"
                        f"📋 Prompt: {prompt_str}"
                    )

            elif action == "delete-reminder":
                deleted_name = self._delete_by_match("reminders", dt_str, prompt_str)
                if deleted_name:
                    await self._log(f"🗑️ **Bot deleted reminder** `{deleted_name}`")

            elif action == "add-auto-wake-time":
                err = self.add_wake_time(auto_name, dt_str, prompt_str, channel_id=default_ch)
                if err:
                    print(f"[Reminders] Bot add-wake-time failed: {err}")
                else:
                    print(f"[Reminders] Bot added wake-time '{auto_name}'.")
                    await self._log(
                        f"📝 **Bot registered wake-time** `{auto_name}`\n"
                        f"⏱️ Fires: `{normalised}`\n"
                        f"📋 Self-prompt: {prompt_str}"
                    )

            elif action == "delete-auto-wake-time":
                deleted_name = self._delete_by_match("wake_times", dt_str, prompt_str)
                if deleted_name:
                    await self._log(f"🗑️ **Bot deleted wake-time** `{deleted_name}`")

    def _delete_by_match(self, bucket: str, dt_str: str, prompt_str: str) -> str | None:
        """
        Delete an entry from *bucket* ('reminders' or 'wake_times') whose
        datetime and prompt match the given values.  Falls back to matching
        by datetime only if the prompt doesn't match exactly.
        Returns the name of the deleted entry or None.
        """
        data = _load_reminders()
        entries = data.get(bucket, {})
        target_name = None

        # Normalise the incoming datetime for comparison
        normalised = _normalise_dt(dt_str)

        # Exact match first (normalised datetime + prompt)
        for name, entry in entries.items():
            entry_norm = _normalise_dt(entry["datetime"])
            if entry_norm == normalised and entry["prompt"].strip() == prompt_str.strip():
                target_name = name
                break

        # Fallback: match by datetime only
        if target_name is None:
            for name, entry in entries.items():
                entry_norm = _normalise_dt(entry["datetime"])
                if entry_norm == normalised:
                    target_name = name
                    break

        if target_name:
            del data[bucket][target_name]
            _save_reminders(data)
            print(f"[Reminders] Bot deleted {bucket} entry '{target_name}'.")
            return target_name
        else:
            print(f"[Reminders] Bot delete-{bucket}: no matching entry for dt={dt_str}.")
            return None
