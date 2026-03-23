"""
tamagotchi.py â€” Gamified Tamagotchi system for ChatBuddy.

Handles all Tamagotchi stats, Discord button UI (stat display + action
buttons), cooldowns, satiation timer, poop background damage, the
Rock-Paper-Scissors minigame, death/reset, and system-prompt injection.

All stat changes are managed here so the LLM cannot cheat.
"""

import asyncio
import random
import time
import discord
from discord import ui
from config import save_config


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Helpers
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _fs(val: float) -> str:
    """Format a stat value: integer if whole, else up to 2 decimals."""
    if val == int(val):
        return str(int(val))
    return f"{val:.2f}".rstrip("0").rstrip(".")


def _fmt_countdown(seconds: float) -> str:
    """Return a human-readable countdown string like '4m 32s'."""
    s = max(0, int(seconds))
    if s >= 60:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s}s"


def is_sleeping(config: dict) -> bool:
    """Return True while the rest timer is active."""
    sleep_until = float(config.get("tama_sleep_until", 0.0) or 0.0)
    if sleep_until <= time.time():
        if config.get("tama_sleeping", False) or sleep_until:
            config["tama_sleeping"] = False
            config["tama_sleep_until"] = 0.0
            save_config(config)
        return False
    return True


def sleeping_remaining(config: dict) -> float:
    return max(0.0, float(config.get("tama_sleep_until", 0.0) or 0.0) - time.time())


def build_sleeping_message(config: dict) -> str:
    template = config.get("tama_resp_sleeping", "I am sleeping come back in {time}")
    return template.replace("{time}", _fmt_countdown(sleeping_remaining(config)))


def can_use_energy(config: dict) -> bool:
    return float(config.get("tama_energy", 0.0) or 0.0) > 0.0


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TamagotchiManager  â€” runtime state that doesn't belong in config.json
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TamagotchiManager:
    """
    Manages ephemeral runtime state:
      â€¢ Global button cooldowns  (dict[str, float] â€” action â†’ timestamp)
      â€¢ Satiation timer           (asyncio.Task or None)
      â€¢ Satiation expiry epoch    (float â€” 0.0 if inactive)
      â€¢ Poop-damage background    (asyncio.Task or None)
      â€¢ RPS pending games         (dict[int, str] â€” message_id â†’ bot_choice)
    """

    def __init__(self, bot: discord.Client, config: dict):
        self.bot = bot
        self.config = config
        self._cooldowns: dict[str, float] = {}     # action -> expiry epoch
        self._satiation_task: asyncio.Task | None = None
        self._satiation_expiry: float = 0.0
        self._dirt_task: asyncio.Task | None = None
        self._energy_task: asyncio.Task | None = None
        self._energy_expiry: float = 0.0
        self._sleep_task: asyncio.Task | None = None
        self._sleep_expiry: float = 0.0
        self._rps_games: dict[int, str] = {}        # msg_id -> bot_choice

    # â”€â”€ lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def start(self):
        """Start background tasks if tama is enabled."""
        if self.config.get("tama_enabled", False):
            self._resume_sleep_state()
            if self.config.get("tama_satiation", 0) >= self.config.get("tama_satiation_max", 10):
                self.start_satiation_timer()
            self._start_dirt_task()
            self.record_interaction(save=False)

    def stop(self):
        if self._satiation_task and not self._satiation_task.done():
            self._satiation_task.cancel()
        if self._dirt_task and not self._dirt_task.done():
            self._dirt_task.cancel()
        if self._energy_task and not self._energy_task.done():
            self._energy_task.cancel()
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()

    # â”€â”€ cooldowns â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def check_cooldown(self, action: str) -> float:
        """
        Return 0.0 if *action* is off cooldown.
        Otherwise return seconds remaining.
        """
        expiry = self._cooldowns.get(action, 0.0)
        remaining = expiry - time.time()
        return max(0.0, remaining)

    def set_cooldown(self, action: str, seconds: int):
        self._cooldowns[action] = time.time() + seconds

    # â€”â€” interaction / energy recharge â€”â€”â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“

    def record_interaction(self, *, save: bool = True):
        if not self.config.get("tama_enabled", False):
            return
        self.config["tama_last_interaction_at"] = time.time()
        if save:
            save_config(self.config)
        self._start_energy_task()

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
                maximum = float(self.config.get("tama_energy_max", 10))
                recharge = max(0.0, float(self.config.get("tama_energy_recharge_amount", 0.5)))
                self.config["tama_energy"] = min(maximum, round(current + recharge, 2))
                save_config(self.config)
        except asyncio.CancelledError:
            return

    # â€”â€” sleep / rest â€”â€”â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“â€“

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

    def begin_rest(self):
        duration = max(1, int(self.config.get("tama_rest_duration", 300)))
        self._sleep_expiry = time.time() + duration
        self.config["tama_sleeping"] = True
        self.config["tama_sleep_until"] = self._sleep_expiry
        save_config(self.config)
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        self._sleep_task = asyncio.create_task(self._sleep_countdown(duration))

    def finish_rest(self):
        self._sleep_expiry = 0.0
        self.config["tama_sleeping"] = False
        self.config["tama_sleep_until"] = 0.0
        self.config["tama_energy"] = float(self.config.get("tama_energy_max", 10))
        save_config(self.config)

    async def _sleep_countdown(self, duration: float):
        try:
            await asyncio.sleep(duration)
        except asyncio.CancelledError:
            return
        self.finish_rest()

    # â”€â”€ satiation timer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def satiation_active(self) -> bool:
        if self.config.get("tama_satiation", 0) < self.config.get("tama_satiation_max", 10):
            self.clear_satiation_timer()
            return False
        return self._satiation_expiry > time.time()

    @property
    def satiation_remaining(self) -> float:
        return max(0.0, self._satiation_expiry - time.time())

    def clear_satiation_timer(self):
        self._satiation_expiry = 0.0
        if self._satiation_task and not self._satiation_task.done():
            self._satiation_task.cancel()

    def sync_satiation_timer(self):
        if self.config.get("tama_satiation", 0) >= self.config.get("tama_satiation_max", 10):
            self.start_satiation_timer()
        else:
            self.clear_satiation_timer()

    def start_satiation_timer(self):
        interval = max(1, int(self.config.get("tama_satiation_timer", 300)))
        self._satiation_expiry = time.time() + interval
        self.clear_satiation_timer()
        self._satiation_expiry = time.time() + interval
        self._satiation_task = asyncio.create_task(self._satiation_countdown())

    async def _satiation_countdown(self):
        try:
            while self.config.get("tama_satiation", 0) >= self.config.get("tama_satiation_max", 10):
                interval = max(1, int(self.config.get("tama_satiation_timer", 300)))
                self._satiation_expiry = time.time() + interval
                await asyncio.sleep(interval)
                decrease = max(0.0, float(self.config.get("tama_satiation_timer_decrease", 1.0)))
                self.config["tama_satiation"] = max(
                    0.0, round(self.config.get("tama_satiation", 0) - decrease, 2)
                )
                save_config(self.config)
        except asyncio.CancelledError:
            return
        # Timer expired â€” reset satiation to 0
        self._satiation_expiry = 0.0

    # â”€â”€ poop damage background â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _start_dirt_task(self):
        if self._dirt_task and not self._dirt_task.done():
            self._dirt_task.cancel()
        self._dirt_task = asyncio.create_task(self._dirt_damage_loop())

    async def _dirt_damage_loop(self):
        try:
            while True:
                interval = self.config.get("tama_dirt_damage_interval", 600)
                await asyncio.sleep(interval)
                if not self.config.get("tama_enabled", False):
                    continue
                dirt = self.config.get("tama_dirt", 0)
                if dirt <= 0:
                    continue
                multiplier = 2.0 if float(self.config.get("tama_energy", 0.0) or 0.0) <= 0.0 else 1.0
                dmg = self.config.get("tama_dirt_health_damage", 0.5) * dirt * multiplier
                self.config["tama_health"] = max(
                    0.0, round(self.config.get("tama_health", 0) - dmg, 2)
                )
                save_config(self.config)
                # Check death
                if self.config["tama_health"] <= 0:
                    death_msg = trigger_death(self.config)
                    await _broadcast_death_and_message(self.bot, self.config, death_msg)
        except asyncio.CancelledError:
            return


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Stat Logic
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def deplete_stats(config: dict) -> str | None:
    """
    Called after every LLM inference.  Depletes hunger, thirst, happiness,
    energy (api), satiation.  Applies health damage from stats below
    threshold and from sickness.  Checks for death.

    Returns None normally, or a death-message string if death occurred.
    """
    if not config.get("tama_enabled", False):
        return None

    multiplier = 2.0 if float(config.get("tama_energy", 0.0) or 0.0) <= 0.0 else 1.0

    # Deplete hunger / thirst / happiness
    config["tama_hunger"] = max(
        0.0,
        round(
            config.get("tama_hunger", 0) - (config.get("tama_hunger_depletion", 0.2) * multiplier),
            2,
        ),
    )
    config["tama_thirst"] = max(
        0.0,
        round(
            config.get("tama_thirst", 0) - (config.get("tama_thirst_depletion", 0.3) * multiplier),
            2,
        ),
    )
    config["tama_happiness"] = max(
        0.0,
        round(
            config.get("tama_happiness", 0) - (config.get("tama_happiness_depletion", 0.1) * multiplier),
            2,
        ),
    )

    # Deplete energy (API call)
    config["tama_energy"] = max(
        0.0,
        round(
            config.get("tama_energy", 0) - (config.get("tama_energy_depletion_api", 0.1) * multiplier),
            2,
        ),
    )

    # Deplete satiation
    config["tama_satiation"] = max(
        0.0,
        round(
            config.get("tama_satiation", 0) - (config.get("tama_satiation_depletion", 0.1) * multiplier),
            2,
        ),
    )

    # â”€â”€ Health damage from stats below threshold â”€â”€
    threshold = config.get("tama_health_threshold", 2.0)
    dmg_per = config.get("tama_health_damage_per_stat", 1.0) * multiplier
    health_loss = 0.0
    for stat_key in ("tama_hunger", "tama_thirst", "tama_happiness"):
        if config.get(stat_key, 0) < threshold:
            health_loss += dmg_per

    # â”€â”€ Sickness damage â”€â”€
    if config.get("tama_sick", False):
        health_loss += config.get("tama_sick_health_damage", 0.5) * multiplier

    if health_loss > 0:
        config["tama_health"] = max(
            0.0, round(config.get("tama_health", 0) - health_loss, 2)
        )

    save_config(config)

    # Death check
    if config["tama_health"] <= 0:
        return trigger_death(config)

    return None


def deplete_energy_game(config: dict):
    """Called when a game (e.g. RPS) is played â€” deducts game energy cost."""
    if not config.get("tama_enabled", False):
        return
    multiplier = 2.0 if float(config.get("tama_energy", 0.0) or 0.0) <= 0.0 else 1.0
    config["tama_energy"] = max(
        0.0,
        round(
            config.get("tama_energy", 0) - (config.get("tama_energy_depletion_game", 0.2) * multiplier),
            2,
        ),
    )
    save_config(config)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Death / Reset
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def trigger_death(config: dict) -> str:
    """
    Wipe soul.md, reset ALL stats to max, clear sickness.
    Returns the death message string.
    """
    try:
        with open("soul.md", "w", encoding="utf-8") as f:
            f.write("{}")
        print("[Tamagotchi] DEATH â€” soul.md wiped.")
    except Exception as e:
        print(f"[Tamagotchi] DEATH â€” Failed to wipe soul.md: {e}")

    config["tama_hunger"] = float(config.get("tama_hunger_max", 10))
    config["tama_thirst"] = float(config.get("tama_thirst_max", 10))
    config["tama_happiness"] = float(config.get("tama_happiness_max", 10))
    config["tama_health"] = float(config.get("tama_health_max", 10))
    config["tama_energy"] = float(config.get("tama_energy_max", 10))
    config["tama_satiation"] = 0.0
    config["tama_dirt"] = 0
    config["tama_dirt_food_counter"] = 0
    config["tama_feed_energy_counter"] = 0
    config["tama_drink_energy_counter"] = 0
    config["tama_sick"] = False
    config["tama_sleeping"] = False
    config["tama_sleep_until"] = 0.0
    save_config(config)

    custom = config.get("tama_rip_message", "").strip()
    if custom:
        return custom
    return (
        "💀 **The Tamagotchi has died!** 💀\n"
        "Its soul has been wiped clean... all memories are gone.\n"
        "Stats have been reset. Take better care of it this time!"
    )


async def broadcast_death(bot, config: dict) -> None:
    """Send [ce] to every allowed channel + SoC channel."""
    channel_ids: set[int] = set()
    for ch_id_str, enabled in config.get("allowed_channels", {}).items():
        if enabled:
            try:
                channel_ids.add(int(ch_id_str))
            except (ValueError, TypeError):
                pass
    if config.get("soc_enabled", False):
        soc_id = config.get("soc_channel_id")
        if soc_id:
            try:
                channel_ids.add(int(soc_id))
            except (ValueError, TypeError):
                pass
    for ch_id in channel_ids:
        ch = bot.get_channel(ch_id)
        if ch is not None:
            try:
                await ch.send("[ce]")
            except Exception as e:
                print(f"[Tamagotchi] Failed to send [ce] to channel {ch_id}: {e}")


async def _broadcast_death_and_message(bot, config: dict, death_msg: str):
    """Post death message in all allowed channels, then broadcast [ce]."""
    tama_view = None
    tama_manager = getattr(bot, "tama_manager", None)
    if config.get("tama_enabled", False) and tama_manager:
        tama_view = TamagotchiView(config, tama_manager)
    for ch_id_str, enabled in config.get("allowed_channels", {}).items():
        if enabled:
            try:
                ch = bot.get_channel(int(ch_id_str))
                if ch:
                    await ch.send(append_tamagotchi_footer(death_msg, config, tama_manager), view=tama_view)
            except Exception:
                pass
    await broadcast_death(bot, config)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# System Prompt Injection
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def build_tamagotchi_system_prompt(config: dict) -> str:
    """Build the system-prompt injection describing current Tamagotchi state."""
    if not config.get("tama_enabled", False):
        return ""

    hunger     = config.get("tama_hunger", 0)
    thirst     = config.get("tama_thirst", 0)
    happiness  = config.get("tama_happiness", 0)
    health     = config.get("tama_health", 0)
    energy     = config.get("tama_energy", 0)
    satiation  = config.get("tama_satiation", 0)
    dirt       = config.get("tama_dirt", 0)
    sick       = config.get("tama_sick", False)
    sleeping   = is_sleeping(config)

    max_hunger  = config.get("tama_hunger_max", 10)
    max_thirst  = config.get("tama_thirst_max", 10)
    max_happy   = config.get("tama_happiness_max", 10)
    max_health  = config.get("tama_health_max", 10)
    max_energy  = config.get("tama_energy_max", 10)
    max_sat     = config.get("tama_satiation_max", 10)
    max_dirt    = config.get("tama_dirt_max", 4)

    lines = [
        "[TAMAGOTCHI STATUS â€” Your virtual pet stats. "
        "These are managed by script; you cannot change them yourself.",
        f"Hunger: {_fs(hunger)}/{max_hunger}",
        f"Thirst: {_fs(thirst)}/{max_thirst}",
        f"Happiness: {_fs(happiness)}/{max_happy}",
        f"Health: {_fs(health)}/{max_health}",
        f"Energy: {_fs(energy)}/{max_energy}",
        f"Satiation: {_fs(satiation)}/{max_sat}",
        f"Dirtiness (poop): {dirt}/{max_dirt}",
        f"Sick: {'YES' if sick else 'No'}",
        f"Sleeping: {'YES' if sleeping else 'No'}",
        "Users interact via buttons (feed, drink, play, medicate, clean). "
        "Your stats decrease each time you respond. "
        "When energy hits 0 you must rest before playing again, and all stat loss is doubled until you do. "
        "If your health reaches 0, you die — your soul is wiped and stats reset.]",
    ]
    return "\n".join(lines)


def build_tamagotchi_message_footer(config: dict, manager: TamagotchiManager | None = None) -> str:
    """Compact mobile-friendly footer appended to public messages."""
    if not config.get("tama_enabled", False):
        return ""

    sat_text = f"🤰 {_fs(config.get('tama_satiation', 0))}/{config.get('tama_satiation_max', 10)}"
    if manager and manager.satiation_active:
        sat_text = f"🤰 {_fmt_countdown(manager.satiation_remaining)}"

    parts = [
        f"🍔 {_fs(config.get('tama_hunger', 0))}/{config.get('tama_hunger_max', 10)}",
        f"🥤 {_fs(config.get('tama_thirst', 0))}/{config.get('tama_thirst_max', 10)}",
        f"😊 {_fs(config.get('tama_happiness', 0))}/{config.get('tama_happiness_max', 10)}",
        f"❤️ {_fs(config.get('tama_health', 0))}/{config.get('tama_health_max', 10)}",
        sat_text,
        f"⚡ {_fs(config.get('tama_energy', 0))}/{config.get('tama_energy_max', 10)}",
        f"💩 {config.get('tama_dirt', 0)}/{config.get('tama_dirt_max', 4)}",
    ]

    if config.get("tama_sick", False):
        parts.append("💀 Sick")
    if manager and manager.sleeping:
        parts.append(f"💤 {_fmt_countdown(manager.sleep_remaining)}")

    return "\n> -# **" + " | ".join(parts) + "**"


def append_tamagotchi_footer(text: str, config: dict, manager: TamagotchiManager | None = None) -> str:
    footer = build_tamagotchi_message_footer(config, manager)
    if not footer:
        return text
    if not text:
        return footer.lstrip("\n")
    return text.rstrip() + footer


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Discord UI â€” Stat Display Buttons (grey, non-interactive)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TamagotchiView(ui.View):
    """
    Persistent view with stat display (grey buttons) + action buttons.
    Attached to every bot response when tama_enabled is True.
    """

    def __init__(self, config: dict, manager: TamagotchiManager):
        # timeout=None makes the view persistent
        super().__init__(timeout=None)
        self.config = config
        self.manager = manager
        self._build()

    def _build(self):
        # â”€â”€ Row 0 + 1: Stat display buttons (grey, disabled) â”€â”€
        hunger    = self.config.get("tama_hunger", 0)
        thirst    = self.config.get("tama_thirst", 0)
        happiness = self.config.get("tama_happiness", 0)
        health    = self.config.get("tama_health", 0)
        energy    = self.config.get("tama_energy", 0)
        dirt      = self.config.get("tama_dirt", 0)
        sick      = self.config.get("tama_sick", False)
        sleeping  = self.manager.sleeping

        max_hunger  = self.config.get("tama_hunger_max", 10)
        max_thirst  = self.config.get("tama_thirst_max", 10)
        max_happy   = self.config.get("tama_happiness_max", 10)
        max_health  = self.config.get("tama_health_max", 10)
        max_energy  = self.config.get("tama_energy_max", 10)
        max_sat     = self.config.get("tama_satiation_max", 10)
        max_dirt    = self.config.get("tama_dirt_max", 4)

        # Satiation display: show countdown if timer active, else number
        if self.manager.satiation_active:
            sat_label = f"🤰 {_fmt_countdown(self.manager.satiation_remaining)}"
        else:
            satiation = self.config.get("tama_satiation", 0)
            sat_label = f"🤰 {_fs(satiation)}/{max_sat}"

        stat_items = [
            (f"🍔 {_fs(hunger)}/{max_hunger}", 0),
            (f"🥤 {_fs(thirst)}/{max_thirst}", 0),
            (f"😊 {_fs(happiness)}/{max_happy}", 0),
            (f"❤️ {_fs(health)}/{max_health}", 0),
            (sat_label, 0),
            # Row 1
            (f"⚡ {_fs(energy)}/{max_energy}", 1),
            (f"💩 {dirt}/{max_dirt}", 1),
        ]

        # Conditionally add sickness icon
        if sick:
            stat_items.append(("💀 Sick", 1))
        if sleeping:
            stat_items.append((f"💤 {_fmt_countdown(self.manager.sleep_remaining)}", 1))

        for label, row in []:
            btn = ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                disabled=True,
                row=row,
            )
            self.add_item(btn)

        # â”€â”€ Row 2: Action buttons â”€â”€
        self.add_item(FeedButton(self.config, self.manager))
        self.add_item(DrinkButton(self.config, self.manager))
        self.add_item(PlayButton(self.config, self.manager))
        self.add_item(MedicateButton(self.config, self.manager))
        self.add_item(CleanButton(self.config, self.manager))
        if energy < 1:
            self.add_item(RestButton(self.config, self.manager))


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Action Buttons
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def _send_sleep_block(interaction: discord.Interaction, config: dict):
    await interaction.response.send_message(build_sleeping_message(config), ephemeral=True)


def _no_energy_message(config: dict) -> str:
    return config.get("tama_resp_no_energy", "⚡ I'm out of energy and need a rest first!")


class FeedButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="🍔 Feed",
            style=discord.ButtonStyle.success,
            custom_id="tama_feed",
            row=2,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return

        # Cooldown check
        remaining = self.manager.check_cooldown("feed")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _fmt_countdown(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        # Satiation check
        if self.manager.satiation_active:
            msg = self.config.get("tama_resp_full", "🤰 I'm stuffed!")
            remaining_sat = self.manager.satiation_remaining
            msg += f"\n⏳ Wait **{_fmt_countdown(remaining_sat)}**."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        # Apply feed
        max_hunger = self.config.get("tama_hunger_max", 10)
        fill = self.config.get("tama_feed_amount", 1.0)
        self.config["tama_hunger"] = min(
            float(max_hunger), round(self.config.get("tama_hunger", 0) + fill, 2)
        )

        # Satiation increase
        sat_inc = self.config.get("tama_satiation_food_increase", 1.0)
        max_sat = self.config.get("tama_satiation_max", 10)
        self.config["tama_satiation"] = min(
            float(max_sat), round(self.config.get("tama_satiation", 0) + sat_inc, 2)
        )

        food_energy_counter = int(self.config.get("tama_feed_energy_counter", 0)) + 1
        food_energy_every = max(1, int(self.config.get("tama_feed_energy_every", 3)))
        self.config["tama_feed_energy_counter"] = food_energy_counter
        if food_energy_counter >= food_energy_every:
            self.config["tama_feed_energy_counter"] = 0
            energy_gain = max(0.0, float(self.config.get("tama_feed_energy_gain", 0.2)))
            max_energy = float(self.config.get("tama_energy_max", 10))
            self.config["tama_energy"] = min(
                max_energy,
                round(float(self.config.get("tama_energy", 0)) + energy_gain, 2),
            )

        # Poop counter
        self.config["tama_dirt_food_counter"] = self.config.get("tama_dirt_food_counter", 0) + 1
        poop_threshold = self.config.get("tama_dirt_food_threshold", 10)
        if self.config["tama_dirt_food_counter"] >= poop_threshold:
            max_dirt = self.config.get("tama_dirt_max", 4)
            self.config["tama_dirt"] = min(max_dirt, self.config.get("tama_dirt", 0) + 1)
            self.config["tama_dirt_food_counter"] = 0

        self.manager.sync_satiation_timer()

        save_config(self.config)
        self.manager.set_cooldown("feed", self.config.get("tama_cd_feed", 60))
        msg = self.config.get("tama_resp_feed", "*nom nom* 🍔 Thanks for the food!")
        await interaction.response.send_message(
            append_tamagotchi_footer(msg, self.config, self.manager),
            view=TamagotchiView(self.config, self.manager),
        )


class DrinkButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="🥤 Drink",
            style=discord.ButtonStyle.primary,
            custom_id="tama_drink",
            row=2,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return

        remaining = self.manager.check_cooldown("drink")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _fmt_countdown(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if self.manager.satiation_active:
            msg = self.config.get("tama_resp_full", "🤰 I'm stuffed!")
            remaining_sat = self.manager.satiation_remaining
            msg += f"\n⏳ Wait **{_fmt_countdown(remaining_sat)}**."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        max_thirst = self.config.get("tama_thirst_max", 10)
        fill = self.config.get("tama_drink_amount", 1.0)
        self.config["tama_thirst"] = min(
            float(max_thirst), round(self.config.get("tama_thirst", 0) + fill, 2)
        )

        sat_inc = self.config.get("tama_satiation_drink_increase", 1.0)
        max_sat = self.config.get("tama_satiation_max", 10)
        self.config["tama_satiation"] = min(
            float(max_sat), round(self.config.get("tama_satiation", 0) + sat_inc, 2)
        )

        drink_energy_counter = int(self.config.get("tama_drink_energy_counter", 0)) + 1
        drink_energy_every = max(1, int(self.config.get("tama_drink_energy_every", 3)))
        self.config["tama_drink_energy_counter"] = drink_energy_counter
        if drink_energy_counter >= drink_energy_every:
            self.config["tama_drink_energy_counter"] = 0
            energy_gain = max(0.0, float(self.config.get("tama_drink_energy_gain", 0.1)))
            max_energy = float(self.config.get("tama_energy_max", 10))
            self.config["tama_energy"] = min(
                max_energy,
                round(float(self.config.get("tama_energy", 0)) + energy_gain, 2),
            )

        self.manager.sync_satiation_timer()

        save_config(self.config)
        self.manager.set_cooldown("drink", self.config.get("tama_cd_drink", 60))
        msg = self.config.get("tama_resp_drink", "*gulp gulp* 🥤 That hit the spot!")
        await interaction.response.send_message(
            append_tamagotchi_footer(msg, self.config, self.manager),
            view=TamagotchiView(self.config, self.manager),
        )


class PlayButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="🎮 Play",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_play",
            row=2,
        )
        # Override secondary â†’ use blurple-ish. Discord doesn't have yellow,
        # so we use secondary (grey) with the emoji to distinguish.
        # Actually, let's explicitly set a style that is visually distinct.
        # Discord button styles: primary=blue, secondary=grey, success=green, danger=red.
        # No yellow exists. We'll keep secondary and rely on the emoji.
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return

        remaining = self.manager.check_cooldown("play")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _fmt_countdown(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if not can_use_energy(self.config):
            await interaction.response.send_message(_no_energy_message(self.config), ephemeral=True)
            return

        # Apply hunger/thirst loss for playing
        hunger_loss = self.config.get("tama_play_hunger_loss", 0.4)
        thirst_loss = self.config.get("tama_play_thirst_loss", 0.2)
        self.config["tama_hunger"] = max(
            0.0, round(self.config.get("tama_hunger", 0) - hunger_loss, 2)
        )
        self.config["tama_thirst"] = max(
            0.0, round(self.config.get("tama_thirst", 0) - thirst_loss, 2)
        )
        satiation_loss = self.config.get("tama_play_satiation_loss", 0.5)
        self.config["tama_satiation"] = max(
            0.0, round(self.config.get("tama_satiation", 0) - satiation_loss, 2)
        )
        self.manager.sync_satiation_timer()

        # Happiness increase
        happy_gain = self.config.get("tama_play_happiness", 1.0)
        max_happy = self.config.get("tama_happiness_max", 10)
        self.config["tama_happiness"] = min(
            float(max_happy), round(self.config.get("tama_happiness", 0) + happy_gain, 2)
        )

        # Energy cost for game
        deplete_energy_game(self.config)

        self.manager.set_cooldown("play", self.config.get("tama_cd_play", 60))

        # Start RPS minigame
        bot_choice = random.choice(["rock", "paper", "scissors"])
        msg = self.config.get("tama_resp_play", "🎮 Let's play!")
        rps_view = RPSView(self.config, self.manager, bot_choice)
        await interaction.response.send_message(
            f"{msg}\n**Rock, Paper, Scissors — pick your move!**",
            view=rps_view,
            ephemeral=True,
        )


class MedicateButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="💉 Medicate",
            style=discord.ButtonStyle.danger,
            custom_id="tama_medicate",
            row=2,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return

        remaining = self.manager.check_cooldown("medicate")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _fmt_countdown(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if not self.config.get("tama_sick", False):
            msg = self.config.get("tama_resp_medicate_healthy", "I'm not sick!")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        self.config["tama_sick"] = False
        save_config(self.config)
        self.manager.set_cooldown("medicate", self.config.get("tama_cd_medicate", 60))
        msg = self.config.get("tama_resp_medicate", "💊 Feeling better!")
        await interaction.response.send_message(
            append_tamagotchi_footer(msg, self.config, self.manager),
            view=TamagotchiView(self.config, self.manager),
        )


class CleanButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="🚿 Clean",
            style=discord.ButtonStyle.primary,
            custom_id="tama_clean",
            row=2,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return

        remaining = self.manager.check_cooldown("clean")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _fmt_countdown(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if self.config.get("tama_dirt", 0) <= 0:
            msg = self.config.get("tama_resp_clean_none", "Already clean!")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        self.config["tama_dirt"] = 0
        save_config(self.config)
        self.manager.set_cooldown("clean", self.config.get("tama_cd_clean", 60))
        msg = self.config.get("tama_resp_clean", "🚿 Squeaky clean!")
        await interaction.response.send_message(
            append_tamagotchi_footer(msg, self.config, self.manager),
            view=TamagotchiView(self.config, self.manager),
        )


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Rock-Paper-Scissors Minigame
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

_RPS_EMOJI = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}


class RestButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="💤 Rest",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_rest",
            row=3,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        remaining = self.manager.check_cooldown("rest")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _fmt_countdown(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return

        self.manager.begin_rest()
        self.manager.set_cooldown("rest", self.config.get("tama_cd_rest", 60))
        msg = self.config.get("tama_resp_rest", "💤 Tucking in for a recharge. See you soon!")
        msg += f"\n⏳ {_fmt_countdown(self.manager.sleep_remaining)}"
        await interaction.response.send_message(
            append_tamagotchi_footer(msg, self.config, self.manager),
            view=TamagotchiView(self.config, self.manager),
        )


class RPSView(ui.View):
    """Ephemeral view presented to the user to pick rock/paper/scissors."""

    def __init__(self, config, manager, bot_choice: str):
        super().__init__(timeout=60)
        self.config = config
        self.manager = manager
        self.bot_choice = bot_choice

    def _result(self, user_choice: str) -> str:
        b = self.bot_choice
        if user_choice == b:
            return "draw"
        wins = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
        return "win" if wins[user_choice] == b else "lose"

    async def _play(self, interaction: discord.Interaction, user_choice: str):
        result = self._result(user_choice)
        u_emoji = _RPS_EMOJI[user_choice]
        b_emoji = _RPS_EMOJI[self.bot_choice]

        if result == "win":
            text = f"You chose {u_emoji}, I chose {b_emoji} — **You win!** 🎉"
        elif result == "lose":
            text = f"You chose {u_emoji}, I chose {b_emoji} — **I win!** 😈"
        else:
            text = f"You chose {u_emoji}, I chose {b_emoji} — **It's a draw!** 🤝"

        # Edit the original ephemeral message to show the result privately
        await interaction.response.edit_message(content=text, view=None)

        # Post the final result publicly
        channel = interaction.channel
        if channel:
            public_text = (
                f"🎮 **Rock Paper Scissors** — {interaction.user.display_name} vs Bot\n"
                f"{text}"
            )
            await channel.send(
                append_tamagotchi_footer(public_text, self.config, self.manager),
                view=TamagotchiView(self.config, self.manager),
            )

        self.stop()

    @ui.button(label="Rock", emoji="🪨", style=discord.ButtonStyle.primary, row=0)
    async def rock_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._play(interaction, "rock")

    @ui.button(label="📄 Paper", style=discord.ButtonStyle.success, row=0)
    async def paper_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._play(interaction, "paper")

    @ui.button(label="✂️ Scissors", style=discord.ButtonStyle.danger, row=0)
    async def scissors_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._play(interaction, "scissors")

