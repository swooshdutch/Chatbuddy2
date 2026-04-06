"""
heartbeat.py - Periodic heartbeat background task for ChatBuddy.

Unlike auto-chat, heartbeat has no idle timer and always fires on the
configured interval unless it is inside the configured quiet window.
"""

import io
import re
from datetime import datetime, timedelta

import discord
from discord.ext import tasks

from bot_helpers import read_soc_context, send_soul_logs
from tamagotchi import TamagotchiView, append_tamagotchi_footer, is_hatching, is_sleeping
from utils import (
    chunk_message,
    collect_context_entries,
    extract_thoughts,
    format_context,
    resolve_custom_emoji,
)


def normalize_heartbeat_rest_time(value: str) -> str | None:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def heartbeat_rest_active(config: dict, *, now: datetime | None = None) -> bool:
    if not config.get("heartbeat_rest_enabled", True):
        return False

    duration_minutes = int(config.get("heartbeat_rest_duration_minutes", 480) or 0)
    if duration_minutes <= 0:
        return False

    normalized = normalize_heartbeat_rest_time(config.get("heartbeat_rest_start_time", "00:00"))
    if normalized is None:
        return False

    now = (now or datetime.now()).astimezone()
    hour, minute = map(int, normalized.split(":"))
    today_start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    window = timedelta(minutes=duration_minutes)

    for start in (today_start, today_start - timedelta(days=1)):
        if start <= now < start + window:
            return True
    return False


def wake_auto_chat_from_heartbeat(bot, config: dict) -> bool:
    """Reset or wake auto-chat after a heartbeat cycle when auto-chat is enabled."""
    if not config.get("auto_chat_enabled"):
        return False

    auto_chat_manager = getattr(bot, "auto_chat_manager", None)
    if not auto_chat_manager:
        return False

    auto_chat_manager.note_activity("heartbeat")
    return True


class HeartbeatManager:
    """Fires a generate() call every N minutes."""

    def __init__(self, bot, config: dict):
        self.bot = bot
        self.config = config
        self._task: tasks.Loop | None = None
        self._last_non_bot_message_id: int | None = None

    def start(self):
        """Start (or restart) the heartbeat loop."""
        self.stop()
        if not self.config.get("heartbeat_enabled"):
            return

        interval = max(1, self.config.get("heartbeat_interval_minutes", 60))

        @tasks.loop(minutes=interval)
        async def _heartbeat_loop():
            await self._tick()

        @_heartbeat_loop.before_loop
        async def _before():
            await self.bot.wait_until_ready()

        self._task = _heartbeat_loop
        self._task.start()

    def stop(self):
        """Cancel the running loop if any."""
        if self._task and self._task.is_running():
            self._task.cancel()
        self._task = None

    async def _tick(self):
        if not self.config.get("heartbeat_enabled"):
            return
        if heartbeat_rest_active(self.config):
            return
        if self.config.get("tama_enabled", False) and (is_sleeping(self.config) or is_hatching(self.config)):
            return

        channel_id = self.config.get("heartbeat_channel_id")
        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            return

        prompt = self.config.get("heartbeat_prompt", "")
        if not prompt:
            return

        try:
            from gemini_api import generate

            history_limit = self.config.get("chat_history_limit", 30)
            history_messages = await collect_context_entries(
                channel,
                history_limit,
                config=self.config,
            )
            tama_manager = getattr(self.bot, "tama_manager", None)
            latest_non_bot_message = next(
                (msg for msg in reversed(history_messages) if msg.author != self.bot.user),
                None,
            )
            has_new_user_activity = (
                latest_non_bot_message is not None
                and latest_non_bot_message.id != self._last_non_bot_message_id
            )
            if self.config.get("tama_enabled", False) and tama_manager and has_new_user_activity:
                tama_manager.record_interaction()
            if latest_non_bot_message is not None:
                self._last_non_bot_message_id = latest_non_bot_message.id

            ce_channels = self.config.get("ce_channels", {})
            ce_enabled = ce_channels.get(str(channel.id), True)
            context = format_context(history_messages, ce_enabled=ce_enabled)
            soc_channel_id = self.config.get("soc_channel_id")
            context += await read_soc_context(self.bot, self.config)

            heartbeat_meta = []
            if latest_non_bot_message is None:
                heartbeat_meta.append(
                    "No non-bot messages are present in the recent channel context."
                )
            elif not has_new_user_activity:
                heartbeat_meta.append(
                    "No new user messages have appeared since the previous heartbeat. "
                    "Treat repeated context as ongoing background, not as a new repeated event."
                )

            full_prompt = "[HEARTBEAT]\n"
            if heartbeat_meta:
                full_prompt += "[HEARTBEAT META]\n" + "\n".join(heartbeat_meta) + "\n\n"
            full_prompt += prompt

            response_text, audio_bytes, soul_logs, reminder_cmds = await generate(
                prompt=full_prompt,
                context=context,
                config=self.config,
            )

            is_dead = False
            if self.config.get("tama_enabled", False):
                from tamagotchi import broadcast_death, deplete_stats

                death_msg = deplete_stats(self.config)
                if death_msg:
                    response_text = (response_text + "\n\n" + death_msg) if response_text else death_msg
                    is_dead = True

            if reminder_cmds:
                from reminders import ReminderManager

                rm = ReminderManager(self.bot, self.config)
                await rm._apply_commands(reminder_cmds, source_channel_id=str(channel.id))

            soc_enabled = self.config.get("soc_enabled", False)
            clean_text, thoughts_text = extract_thoughts(response_text)
            if thoughts_text and soc_enabled and soc_channel_id:
                thought_ch = self.bot.get_channel(int(soc_channel_id))
                if thought_ch is not None:
                    for chunk in chunk_message(thoughts_text):
                        await thought_ch.send(chunk)
            response_text = clean_text.strip()

            visible_response_text = resolve_custom_emoji(response_text, channel.guild).strip()

            if audio_bytes:
                audio_file = discord.File(
                    fp=io.BytesIO(audio_bytes), filename="heartbeat.wav"
                )
                await channel.send(file=audio_file)

            if visible_response_text:
                tama_view = None
                tama_manager = getattr(self.bot, "tama_manager", None)
                if self.config.get("tama_enabled", False) and tama_manager:
                    tama_view = TamagotchiView(self.config, tama_manager)
                    visible_response_text = append_tamagotchi_footer(visible_response_text, self.config, tama_manager)
                chunks = chunk_message(visible_response_text)
                for i, chunk in enumerate(chunks):
                    await channel.send(chunk, view=tama_view if i == len(chunks) - 1 else None)

            await send_soul_logs(self.bot, self.config, soul_logs)

            if is_dead:
                await broadcast_death(self.bot, self.config)
            wake_auto_chat_from_heartbeat(self.bot, self.config)
            print(f"[Heartbeat] Fired at {datetime.now().strftime('%H:%M:%S')}.")

        except Exception as e:
            print(f"[Heartbeat] Error: {e}")
