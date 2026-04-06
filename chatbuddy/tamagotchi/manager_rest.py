"""Sleep and automated prompt behavior for the Tamagotchi runtime manager."""

from __future__ import annotations

import asyncio
import io
import time

import discord

from config import save_config

from .messages import append_tamagotchi_footer
from .runtime_support import build_tamagotchi_view, send_soul_logs
from .state import _discord_relative_time, should_auto_sleep
from .stats import broadcast_death, deplete_stats


class _TamagotchiRestMixin:
    @property
    def sleeping(self) -> bool:
        return self._sleep_expiry > time.time()

    @property
    def sleep_remaining(self) -> float:
        return max(0.0, self._sleep_expiry - time.time())

    def _resume_sleep_state(self):
        expiry = float(self.config.get("tama_sleep_until", 0.0) or 0.0)
        self._sleep_expiry = expiry
        if expiry <= time.time():
            if self.config.get("tama_sleeping", False) or expiry:
                self.finish_rest()
            return
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        self._sleep_task = asyncio.create_task(self._sleep_countdown(self.sleep_remaining))

    def begin_rest(self, channel_id: int | str | None = None):
        duration = max(1, int(self.config.get("tama_rest_duration", 300)))
        started_at = time.time()
        self._sleep_expiry = started_at + duration
        self.config["tama_sleeping"] = True
        self.config["tama_sleep_until"] = self._sleep_expiry
        self.config["tama_sleep_started_at"] = started_at
        self.config["tama_sleep_channel_id"] = str(channel_id or "")
        self.config["tama_sleep_message_id"] = ""
        save_config(self.config)
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        self._sleep_task = asyncio.create_task(self._sleep_countdown(duration))

    def finish_rest(self):
        self._sleep_expiry = 0.0
        self.config["tama_sleeping"] = False
        self.config["tama_sleep_until"] = 0.0
        self.config["tama_sleep_started_at"] = 0.0
        self.config["tama_energy"] = float(self.config.get("tama_energy_max", 100))
        self.config["tama_sleep_channel_id"] = ""
        self.config["tama_sleep_message_id"] = ""
        save_config(self.config)

    async def send_sleep_announcement(self, channel_id: int | str | None = None):
        channel_id = self._resolve_main_channel_id(channel_id or self.config.get("tama_sleep_channel_id"))
        channel = await self._resolve_channel(channel_id)
        if channel is None:
            return

        message = self.config.get("tama_resp_rest", "💤 Tucking in for a recharge. See you soon!")
        message += f"\n⏳ {_discord_relative_time(self.sleep_remaining)}"
        try:
            response_message = await channel.send(
                append_tamagotchi_footer(message, self.config, self),
                view=build_tamagotchi_view(self.config, self),
            )
            self.config["tama_sleep_message_id"] = str(response_message.id)
            save_config(self.config)
        except Exception as exc:
            print(f"[Tamagotchi] Failed to post sleep announcement in channel {channel_id}: {exc}")

    async def _sleep_countdown(self, duration: float):
        try:
            await asyncio.sleep(duration)
        except asyncio.CancelledError:
            return
        channel_id = self.config.get("tama_sleep_channel_id")
        sleep_started_at = float(self.config.get("tama_sleep_started_at", 0.0) or 0.0)
        self.finish_rest()
        await self._announce_rest_complete(channel_id, sleep_started_at)

    async def _announce_rest_complete(self, channel_id: int | str | None, sleep_started_at: float):
        channel = await self._resolve_channel(channel_id)
        if channel is None:
            return
        await self._run_wake_prompt(channel, sleep_started_at)

    async def _run_wake_prompt(self, channel, sleep_started_at: float):
        prompt = self.config.get(
            "tama_wake_prompt",
            "This is an automated system message: you have just woken up from taking a nap. "
            "Let the chat know you are awake again. Review any messages sent after you fell asleep "
            "and decide whether you want to respond to anyone.",
        )
        await self._run_automated_prompt_turn(channel, prompt, sleep_started_at=sleep_started_at)

    async def run_chatter_prompt(self, channel) -> None:
        prompt = self.config.get(
            "tama_chatter_prompt",
            "This is an automated system message: you are free to speak in chat as you please "
            "by taking chat history into consideration.",
        )
        await self._run_automated_prompt_turn(channel, prompt)

    async def _run_automated_prompt_turn(
        self,
        channel,
        prompt: str,
        *,
        sleep_started_at: float | None = None,
    ):
        from gemini_api import generate
        from reminders import ReminderManager
        from utils import (
            chunk_message,
            collect_context_entries,
            extract_thoughts,
            format_context,
            resolve_custom_emoji,
        )

        history_limit = max(1, int(self.config.get("chat_history_limit", 40) or 40))
        history_messages = await collect_context_entries(
            channel,
            history_limit,
            config=self.config,
        )
        if sleep_started_at is not None and sleep_started_at > 0.0:
            history_messages = [
                message
                for message in history_messages
                if message.created_at.timestamp() >= sleep_started_at
            ]

        ce_channels = self.config.get("ce_channels", {})
        ce_enabled = ce_channels.get(str(channel.id), True)
        context = format_context(history_messages, ce_enabled=ce_enabled)

        response_text, audio_bytes, soul_logs, reminder_cmds = await generate(
            prompt=prompt,
            context=context,
            config=self.config,
            speaker_name="System",
            speaker_id="system",
        )
        clean_text, thoughts_text = extract_thoughts(response_text)
        response_text = clean_text.strip()

        soc_channel_id = str(self.config.get("soc_channel_id", "") or "").strip()
        if thoughts_text and self.config.get("soc_enabled", False) and soc_channel_id:
            thought_channel = await self._resolve_channel(soc_channel_id)
            if thought_channel is not None:
                for chunk in chunk_message(thoughts_text):
                    await thought_channel.send(chunk)

        if reminder_cmds:
            reminder_manager = ReminderManager(self.bot, self.config)
            await reminder_manager._apply_commands(reminder_cmds, source_channel_id=str(channel.id))

        death_msg = deplete_stats(self.config)
        started_sleep = False
        if not death_msg and should_auto_sleep(self.config):
            self.begin_rest(channel.id)
            started_sleep = True
        if death_msg:
            response_text = (response_text + "\n\n" + death_msg) if response_text else death_msg

        response_text = resolve_custom_emoji(response_text, getattr(channel, "guild", None))
        if response_text and self.config.get("tama_enabled", False):
            response_text = append_tamagotchi_footer(response_text, self.config, self)
            wake_view = build_tamagotchi_view(self.config, self)
        else:
            wake_view = None
        chunks = chunk_message(response_text)

        if audio_bytes:
            audio_file = discord.File(fp=io.BytesIO(audio_bytes), filename="wake.wav")
            await channel.send(file=audio_file)

        for index, chunk in enumerate(chunks):
            view = wake_view if index == len(chunks) - 1 else None
            await channel.send(chunk, view=view)

        await send_soul_logs(self.bot, self.config, soul_logs)
        if death_msg:
            await broadcast_death(self.bot, self.config)
        if started_sleep:
            await self.send_sleep_announcement(channel.id)


__all__ = ["_TamagotchiRestMixin"]
