"""
tamagotchi.py â€” Gamified Tamagotchi system for ChatBuddy.

Handles all Tamagotchi stats, Discord button UI (stat display + action
buttons), cooldowns, satiation timer, poop background damage, the
Rock-Paper-Scissors minigame, death/reset, and system-prompt injection.

All stat changes are managed here so the LLM cannot cheat.
"""

import asyncio
import random
import re
import time
import io
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


def _discord_relative_time(seconds: float) -> str:
    target = int(time.time() + max(0.0, seconds))
    return f"<t:{target}:R>"


def _discord_relative_epoch(epoch: float) -> str:
    return f"<t:{max(0, int(epoch))}:R>"


def _log_tamagotchi_action(
    config: dict,
    interaction: discord.Interaction,
    action: str,
    message_id: int,
    *,
    item_id: str = "",
    item_name: str = "",
    item_emoji: str = "",
) -> None:
    action_log = list(config.get("tama_action_log", []))
    action_log.append(
        {
            "action": action,
            "channel_id": str(interaction.channel_id or ""),
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.display_name,
            "message_id": str(message_id),
            "timestamp": time.time(),
            "item_id": item_id,
            "item_name": item_name,
            "item_emoji": item_emoji,
        }
    )
    config["tama_action_log"] = action_log[-200:]
    save_config(config)


DEFAULT_TAMA_INVENTORY_ITEMS = {
    "unlimited_hamburger": {
        "name": "Hamburger",
        "emoji": "🍔",
        "item_type": "food",
        "multiplier": 1.0,
        "button_style": "success",
        "amount": -1,
    },
    "unlimited_water": {
        "name": "Cup of Water",
        "emoji": "🥤",
        "item_type": "drink",
        "multiplier": 1.0,
        "button_style": "primary",
        "amount": -1,
    },
}

BUTTON_STYLE_BY_NAME = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}

BUTTON_STYLE_LABELS = {
    "primary": "blue",
    "secondary": "gray",
    "success": "green",
    "danger": "red",
}


def inventory_item_id_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug[:48] or "item"


def ensure_inventory_defaults(config: dict) -> bool:
    items = config.get("tama_inventory_items")
    if not isinstance(items, dict):
        items = {}
        config["tama_inventory_items"] = items

    initialized = bool(config.get("tama_inventory_initialized", False))

    changed = False
    if not initialized:
        for item_id, defaults in DEFAULT_TAMA_INVENTORY_ITEMS.items():
            stored = items.get(item_id)
            if not isinstance(stored, dict):
                items[item_id] = dict(defaults)
                changed = True
                continue
            for key, value in defaults.items():
                if key not in stored:
                    stored[key] = value
                    changed = True
        config["tama_inventory_initialized"] = True
        changed = True

    config["tama_inventory_items"] = items
    return changed


def _coerce_item_amount(value) -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return 0
    return amount if amount < 0 else max(0, amount)


def _normalize_inventory_item(item_id: str, raw_item: dict) -> dict:
    item_type = str(raw_item.get("item_type", "food")).strip().lower()
    if item_type not in {"food", "drink"}:
        item_type = "food"

    button_style = str(raw_item.get("button_style", "secondary")).strip().lower()
    if button_style not in BUTTON_STYLE_BY_NAME:
        button_style = "secondary"

    multiplier = max(0.0, float(raw_item.get("multiplier", 1.0) or 0.0))
    amount = _coerce_item_amount(raw_item.get("amount", 0))
    emoji = str(raw_item.get("emoji", "🍔" if item_type == "food" else "🥤")).strip() or (
        "🍔" if item_type == "food" else "🥤"
    )

    return {
        "id": item_id,
        "name": str(raw_item.get("name", item_id)).strip() or item_id,
        "emoji": emoji,
        "item_type": item_type,
        "multiplier": multiplier,
        "button_style": button_style,
        "amount": amount,
        "is_unlimited": amount < 0,
        "stock_text": "∞" if amount < 0 else str(amount),
    }


def get_inventory_items(
    config: dict,
    *,
    visible_only: bool = False,
    item_type: str | None = None,
) -> list[dict]:
    ensure_inventory_defaults(config)
    items: list[dict] = []
    for item_id, raw_item in config.get("tama_inventory_items", {}).items():
        if not isinstance(raw_item, dict):
            continue
        item = _normalize_inventory_item(item_id, raw_item)
        if item_type and item["item_type"] != item_type:
            continue
        if visible_only and not (item["is_unlimited"] or item["amount"] > 0):
            continue
        items.append(item)
    order = {"food": 0, "drink": 1}
    items.sort(key=lambda item: (order.get(item["item_type"], 9), item["name"].lower(), item["id"]))
    return items


def get_inventory_item(config: dict, item_id: str) -> dict | None:
    ensure_inventory_defaults(config)
    raw_item = config.get("tama_inventory_items", {}).get(item_id)
    if not isinstance(raw_item, dict):
        return None
    return _normalize_inventory_item(item_id, raw_item)


def inventory_button_style(item: dict) -> discord.ButtonStyle:
    return BUTTON_STYLE_BY_NAME.get(item.get("button_style", "secondary"), discord.ButtonStyle.secondary)


def inventory_message_text(config: dict) -> str:
    visible_items = get_inventory_items(config, visible_only=True)
    if not visible_items:
        return "🎒 Inventory is empty right now."
    return "🎒 Choose an item from the inventory."


def _item_action_name(item: dict) -> str:
    return "feed" if item.get("item_type") == "food" else "drink"


def _item_default_icon(action: str) -> str:
    return "🍔" if action == "feed" else "🥤"


def _apply_item_emoji_to_response(message: str, item: dict) -> str:
    action = _item_action_name(item)
    chosen_emoji = item.get("emoji", "").strip() or _item_default_icon(action)
    default_icon = _item_default_icon(action)
    if "{item}" in message:
        return message.replace("{item}", chosen_emoji)
    if default_icon in message:
        return message.replace(default_icon, chosen_emoji)
    if chosen_emoji in message:
        return message
    return f"{chosen_emoji} {message}".strip()


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
    return template.replace("{time}", _discord_relative_time(sleeping_remaining(config)))


def is_hatching(config: dict) -> bool:
    hatch_until = float(config.get("tama_hatch_until", 0.0) or 0.0)
    return bool(config.get("tama_hatching", False)) and hatch_until > time.time()


def hatching_remaining(config: dict) -> float:
    return max(0.0, float(config.get("tama_hatch_until", 0.0) or 0.0) - time.time())


def build_hatching_message(config: dict) -> str:
    remaining = max(1, int(hatching_remaining(config) + 0.999))
    return f"🥚 I'm about to hatch... life begins in **{remaining}s**. Please wait for me to hatch first."


def can_use_energy(config: dict) -> bool:
    return float(config.get("tama_energy", 0.0) or 0.0) > 0.0


def _stat_ratio(current: float, maximum: float) -> float:
    if maximum <= 0:
        return 0.0
    return max(0.0, min(1.0, float(current) / float(maximum)))


def happiness_emoji(config: dict) -> str:
    percent = _stat_ratio(
        float(config.get("tama_happiness", 0)),
        float(config.get("tama_happiness_max", 10)),
    ) * 100
    if percent >= 80:
        return "😁"
    if percent >= 60:
        return "😀"
    if percent >= 40:
        return "🙂"
    if percent >= 20:
        return "😕"
    return "😠"


def wipe_soul_file() -> None:
    try:
        with open("soul.md", "w", encoding="utf-8") as f:
            f.write("{}")
        print("[Tamagotchi] soul.md wiped.")
    except Exception as e:
        print(f"[Tamagotchi] Failed to wipe soul.md: {e}")


def reset_tamagotchi_state(config: dict) -> None:
    config["tama_hunger"] = round(float(config.get("tama_hunger_max", 10)) * 0.5, 2)
    config["tama_thirst"] = round(float(config.get("tama_thirst_max", 10)) * 0.5, 2)
    config["tama_happiness"] = round(float(config.get("tama_happiness_max", 10)) * 0.5, 2)
    config["tama_health"] = float(config.get("tama_health_max", 10))
    config["tama_energy"] = float(config.get("tama_energy_max", 10))
    config["tama_satiation"] = 0.0
    config["tama_dirt"] = 0
    config["tama_dirt_food_counter"] = 0
    config["tama_dirt_grace_until"] = 0.0
    config["tama_feed_energy_counter"] = 0
    config["tama_drink_energy_counter"] = 0
    config["tama_sick"] = False
    config["tama_sleeping"] = False
    config["tama_sleep_until"] = 0.0


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TamagotchiManager  â€” runtime state that doesn't belong in config.json
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TamagotchiManager:
    """
    Manages ephemeral runtime state:
      â€¢ Global button cooldowns  (dict[str, float] â€” action â†’ timestamp)
      â€¢ Satiation timer           (asyncio.Task or None)
      â€¢ Satiation expiry epoch    (float â€” 0.0 if inactive)
      â€¢ Poop grace timer          (asyncio.Task or None)
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
        self._hatch_task: asyncio.Task | None = None
        self._hatch_expiry: float = 0.0
        self._poop_tasks: set[asyncio.Task] = set()
        self._rps_games: dict[int, str] = {}        # msg_id -> bot_choice

    # â”€â”€ lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def start(self):
        """Start background tasks if tama is enabled."""
        if self.config.get("tama_enabled", False):
            self._resume_sleep_state()
            self._resume_hatching_state()
            if self.config.get("tama_satiation", 0) >= self.config.get("tama_satiation_max", 10):
                self.start_satiation_timer()
            self._sync_dirt_grace()
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
        if self._hatch_task and not self._hatch_task.done():
            self._hatch_task.cancel()
        for task in list(self._poop_tasks):
            task.cancel()
        self._poop_tasks.clear()

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

    @property
    def hatching(self) -> bool:
        return self._hatch_expiry > time.time()

    @property
    def hatch_remaining(self) -> float:
        return max(0.0, self._hatch_expiry - time.time())

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
        for ch_id, enabled in self.config.get("allowed_channels", {}).items():
            if enabled:
                return str(ch_id)
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

    async def _send_ce_to_primary_channels(self):
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
            except Exception as e:
                print(f"[Tamagotchi] Failed to send primary [ce] to channel {channel_id}: {e}")

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
    ):
        if self._hatch_task and not self._hatch_task.done():
            self._hatch_task.cancel()
        self.clear_poop_timers()
        self.clear_satiation_timer()
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        self._sleep_expiry = 0.0

        if wipe_soul:
            wipe_soul_file()
        if reset_stats:
            reset_tamagotchi_state(self.config)

        hatch_channel_id = self._resolve_main_channel_id(channel_id)
        duration = max(1, int(self.config.get("tama_egg_hatch_time", 30)))
        self._hatch_expiry = time.time() + duration
        self.config["tama_hatching"] = True
        self.config["tama_hatch_until"] = self._hatch_expiry
        self.config["tama_hatch_channel_id"] = hatch_channel_id
        self.config["tama_hatch_message_id"] = ""
        save_config(self.config)

        if send_ce:
            await self._send_ce_to_primary_channels()

        channel = await self._resolve_channel(hatch_channel_id)
        if channel is not None:
            try:
                msg = await channel.send(build_hatching_message(self.config))
                self.config["tama_hatch_message_id"] = str(msg.id)
                save_config(self.config)
            except Exception as e:
                print(f"[Tamagotchi] Failed to post hatch message in channel {hatch_channel_id}: {e}")

        if self._hatch_task and not self._hatch_task.done():
            self._hatch_task.cancel()
        self._hatch_task = asyncio.create_task(self._hatch_loop())

    async def _update_hatch_message(self, channel) -> None:
        message_id = str(self.config.get("tama_hatch_message_id", "") or "").strip()
        content = build_hatching_message(self.config)
        if channel is None:
            return
        if not message_id:
            try:
                msg = await channel.send(content)
                self.config["tama_hatch_message_id"] = str(msg.id)
                save_config(self.config)
            except Exception as e:
                print(f"[Tamagotchi] Failed to create hatch message: {e}")
            return
        try:
            message = await channel.fetch_message(int(message_id))
            if message.content != content:
                await message.edit(content=content)
        except Exception:
            try:
                msg = await channel.send(content)
                self.config["tama_hatch_message_id"] = str(msg.id)
                save_config(self.config)
            except Exception as e:
                print(f"[Tamagotchi] Failed to refresh hatch message: {e}")

    async def _complete_hatching(self):
        channel_id = self._resolve_main_channel_id(self.config.get("tama_hatch_channel_id"))
        channel = await self._resolve_channel(channel_id)
        message_id = str(self.config.get("tama_hatch_message_id", "") or "").strip()
        self._clear_hatch_state()
        save_config(self.config)

        if channel is not None and message_id:
            try:
                message = await channel.fetch_message(int(message_id))
                await message.edit(content="🐣 The egg has hatched!")
            except Exception:
                pass

        if channel is None:
            return

        from gemini_api import generate
        from utils import chunk_message, resolve_custom_emoji, extract_thoughts

        prompt = self.config.get(
            "tama_hatch_prompt",
            "You have just hatched in this Discord server. Your life has begun right now. Send your very first message to the server.",
        )
        response_text, audio_bytes, soul_logs, _ = await generate(
            prompt=prompt,
            context="",
            config=self.config,
            speaker_name="System",
            speaker_id="system",
        )
        clean_text, thoughts_text = extract_thoughts(response_text)
        response_text = clean_text

        soc_channel_id = str(self.config.get("soc_channel_id", "") or "").strip()
        if thoughts_text and self.config.get("soc_enabled", False) and soc_channel_id:
            thought_channel = await self._resolve_channel(soc_channel_id)
            if thought_channel is not None:
                for chunk in chunk_message(thoughts_text):
                    await thought_channel.send(chunk)

        response_text = resolve_custom_emoji(response_text, getattr(channel, "guild", None))
        if self.config.get("tama_enabled", False):
            response_text = append_tamagotchi_footer(response_text, self.config, self)
            hatch_view = TamagotchiView(self.config, self)
        else:
            hatch_view = None
        chunks = chunk_message(response_text) if response_text else []

        if audio_bytes:
            audio_file = discord.File(fp=io.BytesIO(audio_bytes), filename="hatch.wav")
            await channel.send(file=audio_file)

        for i, chunk in enumerate(chunks):
            view = hatch_view if i == len(chunks) - 1 else None
            await channel.send(chunk, view=view)

        if soul_logs and self.config.get("soul_channel_enabled"):
            soul_channel_id = str(self.config.get("soul_channel_id", "") or "").strip()
            soul_channel = await self._resolve_channel(soul_channel_id)
            if soul_channel is not None:
                joined_logs = "\n".join(soul_logs)
                for log_chunk in chunk_message(joined_logs, limit=1900):
                    await soul_channel.send(f"**🧠 Soul Updates:**\n{log_chunk}")

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

        msg = self.config.get("tama_resp_poop", "oops i pooped")
        try:
            await channel.send(
                append_tamagotchi_footer(msg, self.config, self),
                view=TamagotchiView(self.config, self),
            )
        except Exception as e:
            print(f"[Tamagotchi] Failed to send poop message to channel {channel_id}: {e}")


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

    # Deplete hunger / thirst
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

    low_need_threshold = float(config.get("tama_happiness_low_need_threshold", 5.0))
    low_need_penalty = max(0.0, float(config.get("tama_happiness_low_need_penalty", 0.1)))
    low_need_count = 0
    for stat_key in ("tama_hunger", "tama_thirst"):
        if float(config.get(stat_key, 0) or 0) < low_need_threshold:
            low_need_count += 1

    happiness_loss = (
        float(config.get("tama_happiness_depletion", 0.1)) + (low_need_count * low_need_penalty)
    ) * multiplier
    if config.get("tama_sick", False):
        happiness_loss *= max(1.0, float(config.get("tama_sick_happiness_multiplier", 2.0)))

    config["tama_happiness"] = max(
        0.0,
        round(float(config.get("tama_happiness", 0)) - happiness_loss, 2),
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

    threshold = float(config.get("tama_health_threshold", 2.0))
    low_hunger = float(config.get("tama_hunger", 0) or 0) < threshold
    low_thirst = float(config.get("tama_thirst", 0) or 0) < threshold
    if low_hunger or low_thirst:
        config["tama_sick"] = True

    # â”€â”€ Health damage from stats below threshold â”€â”€
    dmg_per = config.get("tama_health_damage_per_stat", 1.0) * multiplier
    health_loss = 0.0
    for stat_key in ("tama_hunger", "tama_thirst", "tama_happiness"):
        if config.get(stat_key, 0) < threshold:
            health_loss += dmg_per

    # â”€â”€ Sickness damage â”€â”€
    if config.get("tama_sick", False):
        health_loss += config.get("tama_sick_health_damage", 0.5) * multiplier
        dirt = int(config.get("tama_dirt", 0) or 0)
        if dirt > 0:
            health_loss += float(config.get("tama_dirt_health_damage", 0.5)) * dirt * multiplier

    if health_loss > 0:
        config["tama_health"] = max(
            0.0, round(config.get("tama_health", 0) - health_loss, 2)
        )

    if config.get("tama_sick", False):
        config["tama_dirt_grace_until"] = 0.0

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
    wipe_soul_file()
    reset_tamagotchi_state(config)
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
    tama_manager = getattr(bot, "tama_manager", None)
    if tama_manager:
        tama_manager.clear_poop_timers()

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
    if tama_manager and config.get("tama_enabled", False):
        await tama_manager.start_egg_cycle(
            wipe_soul=False,
            reset_stats=False,
            send_ce=False,
        )


async def _broadcast_death_and_message(bot, config: dict, death_msg: str):
    """Post death message in all allowed channels, then broadcast [ce]."""
    tama_view = None
    tama_manager = getattr(bot, "tama_manager", None)
    if config.get("tama_enabled", False) and tama_manager:
        tama_manager.clear_poop_timers()
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
        "Users interact via buttons (inventory, play, medicate, clean). "
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
        sat_text = f"🤰 {_discord_relative_epoch(manager._satiation_expiry)}"

    parts = [
        f"🍔 {_fs(config.get('tama_hunger', 0))}/{config.get('tama_hunger_max', 10)}",
        f"🥤 {_fs(config.get('tama_thirst', 0))}/{config.get('tama_thirst_max', 10)}",
        f"{happiness_emoji(config)} {_fs(config.get('tama_happiness', 0))}/{config.get('tama_happiness_max', 10)}",
        f"❤️ {_fs(config.get('tama_health', 0))}/{config.get('tama_health_max', 10)}",
        sat_text,
        f"⚡ {_fs(config.get('tama_energy', 0))}/{config.get('tama_energy_max', 10)}",
        f"💩 {config.get('tama_dirt', 0)}/{config.get('tama_dirt_max', 4)}",
    ]

    if config.get("tama_sick", False):
        parts.append("💀 Sick")
    if manager and manager.sleeping:
        parts.append(f"💤 {_discord_relative_epoch(manager._sleep_expiry)}")

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
        energy    = self.config.get("tama_energy", 0)
        # â”€â”€ Row 0: Action buttons only â”€â”€
        self.add_item(InventoryButton(self.config, self.manager))
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


async def _refresh_inventory_message(
    interaction: discord.Interaction,
    config: dict,
    manager: TamagotchiManager,
) -> None:
    if not interaction.message:
        return
    try:
        visible_items = get_inventory_items(config, visible_only=True)
        await interaction.message.edit(
            content=inventory_message_text(config),
            view=InventoryView(config, manager, owner_id=interaction.user.id) if visible_items else None,
        )
    except Exception:
        return


async def _consume_inventory_item(
    interaction: discord.Interaction,
    config: dict,
    manager: TamagotchiManager,
    item_id: str,
) -> None:
    manager.record_interaction()
    item = get_inventory_item(config, item_id)
    if not item or not (item["is_unlimited"] or item["amount"] > 0):
        await interaction.response.send_message("⚠️ That item is not in the inventory right now.", ephemeral=True)
        await _refresh_inventory_message(interaction, config, manager)
        return

    if manager.sleeping:
        await _send_sleep_block(interaction, config)
        return

    action = _item_action_name(item)
    remaining = manager.check_cooldown(action)
    if remaining > 0:
        msg = config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
            "{time}", _discord_relative_time(remaining)
        )
        await interaction.response.send_message(msg, ephemeral=True)
        return

    if manager.satiation_active:
        msg = config.get("tama_resp_full", "🤰 I'm stuffed!")
        remaining_sat = manager.satiation_remaining
        msg += f"\n⏳ Wait **{_discord_relative_time(remaining_sat)}**."
        await interaction.response.send_message(msg, ephemeral=True)
        return

    multiplier = max(0.0, float(item.get("multiplier", 1.0) or 0.0))
    max_sat = float(config.get("tama_satiation_max", 10))

    if action == "feed":
        max_hunger = float(config.get("tama_hunger_max", 10))
        fill = float(config.get("tama_feed_amount", 1.0)) * multiplier
        config["tama_hunger"] = min(max_hunger, round(float(config.get("tama_hunger", 0)) + fill, 2))

        sat_inc = float(config.get("tama_satiation_food_increase", 1.0)) * multiplier
        config["tama_satiation"] = min(max_sat, round(float(config.get("tama_satiation", 0)) + sat_inc, 2))

        food_energy_counter = int(config.get("tama_feed_energy_counter", 0)) + 1
        food_energy_every = max(1, int(config.get("tama_feed_energy_every", 3)))
        config["tama_feed_energy_counter"] = food_energy_counter
        if food_energy_counter >= food_energy_every:
            config["tama_feed_energy_counter"] = 0
            energy_gain = max(0.0, float(config.get("tama_feed_energy_gain", 0.2)))
            max_energy = float(config.get("tama_energy_max", 10))
            config["tama_energy"] = min(
                max_energy,
                round(float(config.get("tama_energy", 0)) + energy_gain, 2),
            )

        config["tama_dirt_food_counter"] = int(config.get("tama_dirt_food_counter", 0)) + 1
        poop_threshold = max(1, int(config.get("tama_dirt_food_threshold", 5)))
        while config["tama_dirt_food_counter"] >= poop_threshold:
            config["tama_dirt_food_counter"] -= poop_threshold
            manager.queue_poop_timer(interaction.channel_id)
        response_key = "tama_resp_feed"
        cooldown_key = "tama_cd_feed"
    else:
        max_thirst = float(config.get("tama_thirst_max", 10))
        fill = float(config.get("tama_drink_amount", 1.0)) * multiplier
        config["tama_thirst"] = min(max_thirst, round(float(config.get("tama_thirst", 0)) + fill, 2))

        sat_inc = float(config.get("tama_satiation_drink_increase", 1.0)) * multiplier
        config["tama_satiation"] = min(max_sat, round(float(config.get("tama_satiation", 0)) + sat_inc, 2))

        drink_energy_counter = int(config.get("tama_drink_energy_counter", 0)) + 1
        drink_energy_every = max(1, int(config.get("tama_drink_energy_every", 3)))
        config["tama_drink_energy_counter"] = drink_energy_counter
        if drink_energy_counter >= drink_energy_every:
            config["tama_drink_energy_counter"] = 0
            energy_gain = max(0.0, float(config.get("tama_drink_energy_gain", 0.1)))
            max_energy = float(config.get("tama_energy_max", 10))
            config["tama_energy"] = min(
                max_energy,
                round(float(config.get("tama_energy", 0)) + energy_gain, 2),
            )
        response_key = "tama_resp_drink"
        cooldown_key = "tama_cd_drink"

    if not item["is_unlimited"]:
        config["tama_inventory_items"][item_id]["amount"] = max(0, item["amount"] - 1)

    manager.sync_satiation_timer()
    save_config(config)
    manager.set_cooldown(action, int(config.get(cooldown_key, 60)))

    default_response = "*nom nom* 🍔 Thanks for the food!" if action == "feed" else "*gulp gulp* 🥤 That hit the spot!"
    msg = config.get(response_key, default_response)
    msg = _apply_item_emoji_to_response(msg, item)
    await interaction.response.send_message(
        append_tamagotchi_footer(msg, config, manager),
        view=TamagotchiView(config, manager),
    )
    response_message = await interaction.original_response()
    _log_tamagotchi_action(
        config,
        interaction,
        action,
        response_message.id,
        item_id=item["id"],
        item_name=item["name"],
        item_emoji=item["emoji"],
    )
    await _refresh_inventory_message(interaction, config, manager)


class InventoryButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="Inventory",
            emoji="🎒",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_inventory",
            row=0,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        await interaction.response.send_message(
            inventory_message_text(self.config),
            ephemeral=True,
            view=InventoryView(self.config, self.manager, owner_id=interaction.user.id),
        )


class InventoryView(ui.View):
    def __init__(self, config: dict, manager: TamagotchiManager, owner_id: int):
        super().__init__(timeout=300)
        self.config = config
        self.manager = manager
        self.owner_id = owner_id
        self._build()

    def _build(self):
        visible_items = get_inventory_items(self.config, visible_only=True)
        for idx, item in enumerate(visible_items[:25]):
            self.add_item(InventoryItemButton(self.config, self.manager, item, row=idx // 5))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This inventory menu belongs to someone else.", ephemeral=True)
            return False
        return True


class InventoryItemButton(ui.Button):
    def __init__(self, config: dict, manager: TamagotchiManager, item: dict, row: int = 0):
        label = f"{item['name']} x{item['stock_text']}"
        if len(label) > 80:
            label = label[:77] + "..."
        super().__init__(
            label=label,
            emoji=item.get("emoji"),
            style=inventory_button_style(item),
            row=row,
        )
        self.config = config
        self.manager = manager
        self.item_id = item["id"]

    async def callback(self, interaction: discord.Interaction):
        await _consume_inventory_item(interaction, self.config, self.manager, self.item_id)


class PlayButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="🎮 Play",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_play",
            row=0,
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
                "{time}", _discord_relative_time(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if not can_use_energy(self.config):
            await interaction.response.send_message(_no_energy_message(self.config), ephemeral=True)
            return

        if self.manager.satiation_active:
            msg = self.config.get("tama_resp_full", "🤰 I'm stuffed!")
            remaining_sat = self.manager.satiation_remaining
            msg += f"\n⏳ Wait **{_discord_relative_time(remaining_sat)}** before playing again."
            await interaction.response.send_message(msg, ephemeral=True)
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
            row=0,
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
                "{time}", _discord_relative_time(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        max_health = float(self.config.get("tama_health_max", 10))
        current_health = float(self.config.get("tama_health", 0))
        is_sick = self.config.get("tama_sick", False)
        dirt = int(self.config.get("tama_dirt", 0) or 0)
        threshold = float(self.config.get("tama_health_threshold", 2.0))
        low_hunger = float(self.config.get("tama_hunger", 0) or 0) < threshold
        low_thirst = float(self.config.get("tama_thirst", 0) or 0) < threshold

        if dirt > 0:
            await interaction.response.send_message(
                "🚿 Clean the bot before medicating it.",
                ephemeral=True,
            )
            return

        if is_sick and (low_hunger or low_thirst):
            needs = []
            if low_hunger:
                needs.append("hunger")
            if low_thirst:
                needs.append("thirst")
            needs_text = " and ".join(needs)
            await interaction.response.send_message(
                f"🍔🥤 {needs_text.capitalize()} must be above {threshold:g} before you can medicate the bot.",
                ephemeral=True,
            )
            return

        if not is_sick and current_health >= max_health:
            msg = self.config.get("tama_resp_medicate_healthy", "I'm not sick!")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        heal_amount = max(0.0, float(self.config.get("tama_medicate_health_heal", 2.0)))
        happiness_cost = max(0.0, float(self.config.get("tama_medicate_happiness_cost", 0.3)))
        self.config["tama_sick"] = False
        self.config["tama_health"] = min(max_health, round(current_health + heal_amount, 2))
        self.config["tama_happiness"] = max(
            0.0,
            round(float(self.config.get("tama_happiness", 0)) - happiness_cost, 2),
        )
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
            row=0,
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
                "{time}", _discord_relative_time(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if self.config.get("tama_dirt", 0) <= 0:
            msg = self.config.get("tama_resp_clean_none", "Already clean!")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        self.config["tama_dirt"] = 0
        self.config["tama_dirt_grace_until"] = 0.0
        save_config(self.config)
        self.manager._clear_dirt_grace(save=False)
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
            row=1,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        remaining = self.manager.check_cooldown("rest")
        if remaining > 0:
            msg = self.config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
                "{time}", _discord_relative_time(remaining)
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if self.manager.sleeping:
            await _send_sleep_block(interaction, self.config)
            return

        self.manager.begin_rest()
        self.manager.set_cooldown("rest", self.config.get("tama_cd_rest", 60))
        msg = self.config.get("tama_resp_rest", "💤 Tucking in for a recharge. See you soon!")
        msg += f"\n⏳ {_discord_relative_time(self.manager.sleep_remaining)}"
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

