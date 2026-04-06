"""Egg hatching and channel resolution behavior for the Tamagotchi manager."""

from __future__ import annotations

import asyncio
import io
import time

import discord

from config import save_config

from .messages import append_tamagotchi_footer
from .runtime_support import build_tamagotchi_view, send_soul_logs
from .state import build_hatching_message


class _TamagotchiHatchingMixin:
    @property
    def hatching(self) -> bool:
        return self._hatch_expiry > time.time()

    @property
    def hatch_remaining(self) -> float:
        return max(0.0, self._hatch_expiry - time.time())

    def _resume_hatching_state(self):
        expiry = float(self.config.get("tama_hatch_until", 0.0) or 0.0)
        self._hatch_expiry = expiry
        if not self.config.get("tama_hatching", False):
            return
        if self._hatch_task and not self._hatch_task.done():
            self._hatch_task.cancel()
        self._hatch_task = asyncio.create_task(self._hatch_loop())

    def _resolve_main_channel_id(self, preferred_channel_id: int | str | None = None) -> str:
        if preferred_channel_id:
            return str(preferred_channel_id)
        for key in ("main_chat_channel_id", "tama_hatch_channel_id", "reminders_channel_id"):
            value = str(self.config.get(key, "") or "").strip()
            if value:
                return value
        for channel_id, enabled in self.config.get("allowed_channels", {}).items():
            if enabled:
                return str(channel_id)
        return ""

    async def _resolve_channel(self, channel_id: int | str | None):
        if not channel_id:
            return None
        try:
            numeric = int(channel_id)
        except (TypeError, ValueError):
            return None
        channel = self.bot.get_channel(numeric)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(numeric)
            except Exception:
                channel = None
        return channel

    @staticmethod
    def _channel_type_name(channel) -> str:
        if channel is None:
            return "unknown"
        return type(channel).__name__

    async def _send_ce_to_primary_channels(self) -> set[int]:
        channel_ids: set[int] = set()
        main_channel_id = self._resolve_main_channel_id()
        if main_channel_id:
            channel_ids.add(int(main_channel_id))
        soc_id = str(self.config.get("soc_channel_id", "") or "").strip()
        if soc_id:
            channel_ids.add(int(soc_id))
        for channel_id in channel_ids:
            channel = await self._resolve_channel(channel_id)
            if channel is None:
                continue
            try:
                await channel.send("[ce]")
            except Exception as exc:
                print(f"[Tamagotchi] Failed to send primary [ce] to channel {channel_id}: {exc}")
        return channel_ids

    def _clear_hatch_state(self):
        self._hatch_expiry = 0.0
        self.config["tama_hatching"] = False
        self.config["tama_hatch_until"] = 0.0
        self.config["tama_hatch_message_id"] = ""

    async def start_egg_cycle(
        self,
        channel_id: int | str | None = None,
        *,
        wipe_soul: bool,
        reset_stats: bool,
        send_ce: bool,
        fallback_channel_ids: list[int | str] | tuple[int | str, ...] | None = None,
    ) -> dict:
        result = {
            "soul_wiped": False,
            "stats_reset": False,
            "ce_channel_ids": [],
            "hatch_channel_id": "",
            "hatch_message_posted": False,
            "hatch_attempted_channel_ids": [],
            "hatch_failure_reason": "",
        }
        if self._hatch_task and not self._hatch_task.done():
            self._hatch_task.cancel()
        self.clear_poop_timers()
        if self._lonely_task and not self._lonely_task.done():
            self._lonely_task.cancel()
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        self._sleep_expiry = 0.0

        if wipe_soul:
            from .state import wipe_soul_file

            wipe_soul_file()
            result["soul_wiped"] = True
        if reset_stats:
            from .state import reset_tamagotchi_state

            reset_tamagotchi_state(self.config)
            result["stats_reset"] = True

        hatch_channel_id = self._resolve_main_channel_id(channel_id)
        candidate_channel_ids: list[str] = []
        for raw_channel_id in [hatch_channel_id, *(fallback_channel_ids or [])]:
            normalized_channel_id = str(raw_channel_id or "").strip()
            if normalized_channel_id and normalized_channel_id not in candidate_channel_ids:
                candidate_channel_ids.append(normalized_channel_id)

        result["hatch_channel_id"] = hatch_channel_id
        result["hatch_attempted_channel_ids"] = list(candidate_channel_ids)
        duration = max(1, int(self.config.get("tama_egg_hatch_time", 30)))
        self._hatch_expiry = time.time() + duration
        self.config["tama_hatching"] = True
        self.config["tama_hatch_until"] = self._hatch_expiry
        self.config["tama_hatch_channel_id"] = hatch_channel_id
        self.config["tama_hatch_message_id"] = ""
        save_config(self.config)

        if send_ce:
            ce_ids = await self._send_ce_to_primary_channels()
            result["ce_channel_ids"] = sorted(ce_ids)

        if not candidate_channel_ids:
            result["hatch_failure_reason"] = "No hatch channel was configured or supplied."

        for candidate_channel_id in candidate_channel_ids:
            channel = await self._resolve_channel(candidate_channel_id)
            if channel is None:
                result["hatch_failure_reason"] = (
                    f"Channel {candidate_channel_id} was not found or is not accessible to the bot."
                )
                continue
            if not hasattr(channel, "send"):
                result["hatch_failure_reason"] = (
                    f"Channel {candidate_channel_id} resolved to unsupported type "
                    f"{self._channel_type_name(channel)}."
                )
                continue
            try:
                message = await channel.send(build_hatching_message(self.config))
                self.config["tama_hatch_channel_id"] = str(candidate_channel_id)
                self.config["tama_hatch_message_id"] = str(message.id)
                save_config(self.config)
                result["hatch_channel_id"] = str(candidate_channel_id)
                result["hatch_message_posted"] = True
                result["hatch_failure_reason"] = ""
                break
            except Exception as exc:
                result["hatch_failure_reason"] = f"Channel {candidate_channel_id} rejected the hatch message: {exc}"
                print(f"[Tamagotchi] Failed to post hatch message in channel {candidate_channel_id}: {exc}")

        if self._hatch_task and not self._hatch_task.done():
            self._hatch_task.cancel()
        self._hatch_task = asyncio.create_task(self._hatch_loop())
        return result

    async def _update_hatch_message(self, channel) -> None:
        message_id = str(self.config.get("tama_hatch_message_id", "") or "").strip()
        content = build_hatching_message(self.config)
        if channel is None:
            return
        if not message_id:
            try:
                message = await channel.send(content)
                self.config["tama_hatch_message_id"] = str(message.id)
                save_config(self.config)
            except Exception as exc:
                print(f"[Tamagotchi] Failed to create hatch message: {exc}")
            return
        try:
            message = await channel.fetch_message(int(message_id))
            if message.content != content:
                await message.edit(content=content)
        except Exception:
            try:
                message = await channel.send(content)
                self.config["tama_hatch_message_id"] = str(message.id)
                save_config(self.config)
            except Exception as exc:
                print(f"[Tamagotchi] Failed to refresh hatch message: {exc}")

    async def _complete_hatching(self):
        channel_id = self._resolve_main_channel_id(self.config.get("tama_hatch_channel_id"))
        channel = await self._resolve_channel(channel_id)
        message_id = str(self.config.get("tama_hatch_message_id", "") or "").strip()
        self.config["tama_birth_at"] = time.time()
        self._clear_hatch_state()
        save_config(self.config)
        if self.config.get("tama_enabled", False):
            self._start_lonely_task()

        if channel is not None and message_id:
            try:
                message = await channel.fetch_message(int(message_id))
                await message.edit(content="🐣 The egg has hatched!")
            except Exception:
                pass

        if channel is None:
            return

        from gemini_api import generate
        from reminders import ReminderManager
        from utils import chunk_message, extract_thoughts, resolve_custom_emoji

        prompt = self.config.get(
            "tama_hatch_prompt",
            "You have just hatched in this Discord server. Your life has begun right now. Send your very first message to the server.",
        )
        response_text, audio_bytes, soul_logs, reminder_cmds = await generate(
            prompt=prompt,
            context="",
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

        response_text = resolve_custom_emoji(response_text, getattr(channel, "guild", None))
        if response_text and self.config.get("tama_enabled", False):
            response_text = append_tamagotchi_footer(response_text, self.config, self)
            hatch_view = build_tamagotchi_view(self.config, self)
        else:
            hatch_view = None
        chunks = chunk_message(response_text)

        if audio_bytes:
            audio_file = discord.File(fp=io.BytesIO(audio_bytes), filename="hatch.wav")
            await channel.send(file=audio_file)

        for index, chunk in enumerate(chunks):
            view = hatch_view if index == len(chunks) - 1 else None
            await channel.send(chunk, view=view)

        await send_soul_logs(self.bot, self.config, soul_logs)

    async def _hatch_loop(self):
        channel_id = self._resolve_main_channel_id(self.config.get("tama_hatch_channel_id"))
        channel = await self._resolve_channel(channel_id)
        try:
            while self.config.get("tama_hatching", False):
                if self.hatching:
                    await self._update_hatch_message(channel)
                    await asyncio.sleep(1)
                    continue
                break
        except asyncio.CancelledError:
            return
        if self.config.get("tama_hatching", False):
            await self._complete_hatching()


__all__ = ["_TamagotchiHatchingMixin"]
