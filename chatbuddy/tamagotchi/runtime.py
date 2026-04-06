"""Runtime compatibility surface for the Tamagotchi feature."""

from __future__ import annotations

import asyncio
import time

import discord

from config import save_config

from .manager_cleanup import _TamagotchiCleanupMixin
from .manager_hatching import _TamagotchiHatchingMixin
from .manager_rest import _TamagotchiRestMixin
from .messages import *  # noqa: F401,F403
from .runtime_support import build_tamagotchi_view as _build_tama_view_impl
from .runtime_support import send_soul_logs as _send_soul_logs_impl
from .state import *  # noqa: F401,F403
from .stats import *  # noqa: F401,F403


def _build_tama_view(config: dict, manager):
    return _build_tama_view_impl(config, manager)


async def _send_soul_logs(bot_ref, config: dict, soul_logs: list[str]) -> None:
    await _send_soul_logs_impl(bot_ref, config, soul_logs)


class TamagotchiManager(
    _TamagotchiRestMixin,
    _TamagotchiHatchingMixin,
    _TamagotchiCleanupMixin,
):
    """Manages ephemeral runtime state that does not belong in config.json."""

    def __init__(self, bot: discord.Client, config: dict):
        self.bot = bot
        self.config = config
        self._cooldowns: dict[str, float] = {}
        self._dirt_task: asyncio.Task | None = None
        self._energy_task: asyncio.Task | None = None
        self._energy_expiry: float = 0.0
        self._lonely_task: asyncio.Task | None = None
        self._sleep_task: asyncio.Task | None = None
        self._sleep_expiry: float = 0.0
        self._hatch_task: asyncio.Task | None = None
        self._hatch_expiry: float = 0.0
        self._poop_tasks: set[asyncio.Task] = set()
        self._rps_games: dict[int, str] = {}

    def start(self):
        """Start background tasks if Tamagotchi is enabled."""
        if self.config.get("tama_enabled", False):
            self._resume_sleep_state()
            self._resume_hatching_state()
            self._sync_dirt_grace()
            apply_loneliness(self.config, save=True)
            now = time.time()
            if float(self.config.get("tama_last_interaction_at", 0.0) or 0.0) <= 0.0:
                self.config["tama_last_interaction_at"] = now
                self.config["tama_lonely_last_update_at"] = now
                save_config(self.config)
            self._start_energy_task()
            self._start_lonely_task()

    def stop(self):
        if self._dirt_task and not self._dirt_task.done():
            self._dirt_task.cancel()
        if self._energy_task and not self._energy_task.done():
            self._energy_task.cancel()
        if self._lonely_task and not self._lonely_task.done():
            self._lonely_task.cancel()
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        if self._hatch_task and not self._hatch_task.done():
            self._hatch_task.cancel()
        for task in list(self._poop_tasks):
            task.cancel()
        self._poop_tasks.clear()

    def check_cooldown(self, action: str) -> float:
        expiry = self._cooldowns.get(action, 0.0)
        remaining = expiry - time.time()
        return max(0.0, remaining)

    def set_cooldown(self, action: str, seconds: int):
        self._cooldowns[action] = time.time() + seconds

    def record_interaction(self, *, save: bool = True):
        if not self.config.get("tama_enabled", False):
            return
        now = time.time()
        self.config["tama_last_interaction_at"] = now
        self.config["tama_lonely_last_update_at"] = now
        if save:
            save_config(self.config)
        self._start_energy_task()
        self._start_lonely_task()

    def _start_energy_task(self):
        interval = max(1, int(self.config.get("tama_energy_recharge_interval", 300)))
        self._energy_expiry = time.time() + interval
        if self._energy_task and not self._energy_task.done():
            self._energy_task.cancel()
        self._energy_task = asyncio.create_task(self._energy_recharge_loop())

    async def _energy_recharge_loop(self):
        try:
            while True:
                interval = max(1, int(self.config.get("tama_energy_recharge_interval", 300)))
                self._energy_expiry = time.time() + interval
                await asyncio.sleep(interval)
                current = float(self.config.get("tama_energy", 0))
                maximum = float(self.config.get("tama_energy_max", 100))
                recharge = max(0.0, float(self.config.get("tama_energy_recharge_amount", 5.0)))
                self.config["tama_energy"] = min(maximum, round(current + recharge, 2))
                save_config(self.config)
        except asyncio.CancelledError:
            return

    def _start_lonely_task(self):
        if self._lonely_task and not self._lonely_task.done():
            self._lonely_task.cancel()
        self._lonely_task = asyncio.create_task(self._lonely_loop())

    async def _lonely_loop(self):
        try:
            while True:
                last_update = max(
                    float(self.config.get("tama_last_interaction_at", 0.0) or 0.0),
                    float(self.config.get("tama_lonely_last_update_at", 0.0) or 0.0),
                )
                if last_update <= 0.0:
                    last_update = time.time()
                    self.config["tama_last_interaction_at"] = last_update
                    self.config["tama_lonely_last_update_at"] = last_update
                    save_config(self.config)
                next_due_at = loneliness_next_due_at(self.config)
                if next_due_at == float("inf"):
                    await asyncio.sleep(60)
                    continue
                sleep_for = max(1.0, next_due_at - time.time())
                await asyncio.sleep(sleep_for)
                apply_loneliness(self.config, save=True)
        except asyncio.CancelledError:
            return


__all__ = [name for name in globals() if not name.startswith("__")]
