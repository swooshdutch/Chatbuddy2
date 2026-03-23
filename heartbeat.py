"""
heartbeat.py — Periodic heartbeat background task for ChatBuddy.

Unlike auto-chat, heartbeat has NO idle timer and always fires on the
configured interval regardless of who posted the last message.  It
simply calls generate() with the configured heartbeat prompt and posts
the response in the designated channel.
"""

import io
from datetime import datetime

import discord
from discord.ext import tasks

from utils import (
    format_context,
    chunk_message,
    resolve_custom_emoji,
    extract_thoughts,
    extract_reminder_commands,
    collect_context_entries,
)
from tamagotchi import TamagotchiView, append_tamagotchi_footer, is_sleeping


class HeartbeatManager:
    """Fires a generate() call every N minutes, unconditionally."""

    def __init__(self, bot, config: dict):
        self.bot = bot
        self.config = config
        self._task: tasks.Loop | None = None

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(self):
        """Start (or restart) the heartbeat loop."""
        self.stop()
        if not self.config.get("heartbeat_enabled"):
            return
        if self.config.get("tama_enabled", False) and is_sleeping(self.config):
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

    # ── core tick ──────────────────────────────────────────────────────

    async def _tick(self):
        if not self.config.get("heartbeat_enabled"):
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
            from gemini_api import generate  # lazy to avoid circular import
            tama_manager = getattr(self.bot, "tama_manager", None)
            if self.config.get("tama_enabled", False) and tama_manager:
                tama_manager.record_interaction()

            # Gather recent channel context
            history_limit = self.config.get("chat_history_limit", 30)
            history_messages = await collect_context_entries(
                channel,
                history_limit,
                config=self.config,
            )

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

            full_prompt = f"[HEARTBEAT]\n{prompt}"

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

            # Process reminder tags
            response_text, new_cmds = extract_reminder_commands(response_text)
            if new_cmds:
                from reminders import ReminderManager
                rm = ReminderManager(self.bot, self.config)
                await rm._apply_commands(new_cmds, source_channel_id=str(channel.id))

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
                    fp=io.BytesIO(audio_bytes), filename="heartbeat.wav"
                )
                await channel.send(file=audio_file)

            # Send text response
            if response_text:
                chunks = chunk_message(response_text)
                tama_view = None
                tama_manager = getattr(self.bot, "tama_manager", None)
                if self.config.get("tama_enabled", False) and tama_manager:
                    tama_view = TamagotchiView(self.config, tama_manager)
                    response_text = append_tamagotchi_footer(response_text, self.config, tama_manager)
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
            print(f"[Heartbeat] Fired at {datetime.now().strftime('%H:%M:%S')}.")

        except Exception as e:
            print(f"[Heartbeat] Error: {e}")
