"""Dirt grace and poop timer behavior for the Tamagotchi manager."""

from __future__ import annotations

import asyncio
import random
import time

from config import save_config

from .messages import append_tamagotchi_footer
from .runtime_support import build_tamagotchi_view


class _TamagotchiCleanupMixin:
    def _clear_dirt_grace(self, *, save: bool = True):
        self.config["tama_dirt_grace_until"] = 0.0
        if save:
            save_config(self.config)
        if self._dirt_task and not self._dirt_task.done():
            self._dirt_task.cancel()

    def _start_dirt_task(self):
        if self._dirt_task and not self._dirt_task.done():
            self._dirt_task.cancel()
        self._dirt_task = asyncio.create_task(self._dirt_grace_loop())

    def _sync_dirt_grace(self):
        if not self.config.get("tama_enabled", False):
            self._clear_dirt_grace(save=False)
            return

        dirt = int(self.config.get("tama_dirt", 0) or 0)
        if dirt <= 0 or self.config.get("tama_sick", False):
            self._clear_dirt_grace()
            return

        grace_until = float(self.config.get("tama_dirt_grace_until", 0.0) or 0.0)
        now = time.time()
        if grace_until <= 0.0:
            interval = max(10, int(self.config.get("tama_dirt_damage_interval", 600)))
            self.config["tama_dirt_grace_until"] = now + interval
            save_config(self.config)
        elif grace_until <= now:
            self.config["tama_sick"] = True
            self.config["tama_dirt_grace_until"] = 0.0
            save_config(self.config)
            if self._dirt_task and not self._dirt_task.done():
                self._dirt_task.cancel()
            return

        self._start_dirt_task()

    async def _dirt_grace_loop(self):
        try:
            grace_until = float(self.config.get("tama_dirt_grace_until", 0.0) or 0.0)
            remaining = max(0.0, grace_until - time.time())
            if remaining > 0:
                await asyncio.sleep(remaining)
            if not self.config.get("tama_enabled", False):
                return
            if int(self.config.get("tama_dirt", 0) or 0) <= 0:
                self.config["tama_dirt_grace_until"] = 0.0
                save_config(self.config)
                return
            if self.config.get("tama_sick", False):
                self.config["tama_dirt_grace_until"] = 0.0
                save_config(self.config)
                return
            self.config["tama_sick"] = True
            self.config["tama_dirt_grace_until"] = 0.0
            save_config(self.config)
        except asyncio.CancelledError:
            return

    def queue_poop_timer(self, channel_id: int | str | None):
        max_minutes = max(1, int(self.config.get("tama_dirt_poop_timer_max_minutes", 5)))
        delay_seconds = random.randint(1, max_minutes) * 60
        task = asyncio.create_task(self._poop_countdown(channel_id, delay_seconds))
        self._poop_tasks.add(task)
        task.add_done_callback(self._poop_tasks.discard)

    def clear_poop_timers(self):
        for task in list(self._poop_tasks):
            task.cancel()
        self._poop_tasks.clear()

    async def _poop_countdown(self, channel_id: int | str | None, delay_seconds: int):
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return

        if not self.config.get("tama_enabled", False):
            return

        max_dirt = int(self.config.get("tama_dirt_max", 4))
        self.config["tama_dirt"] = min(max_dirt, int(self.config.get("tama_dirt", 0)) + 1)
        save_config(self.config)
        self._sync_dirt_grace()

        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            return

        message = self.config.get("tama_resp_poop", "oops i pooped")
        try:
            await channel.send(
                append_tamagotchi_footer(message, self.config, self),
                view=build_tamagotchi_view(self.config, self),
            )
        except Exception as exc:
            print(f"[Tamagotchi] Failed to send poop message to channel {channel_id}: {exc}")


__all__ = ["_TamagotchiCleanupMixin"]
