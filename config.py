"""
config.py â€” Persistent configuration manager for ChatBuddy.
Reads/writes a config.json file so settings survive Discloud restarts.
"""

import json
import math
import os

CONFIG_FILE = "config.json"

DEFAULTS = {
    "api_key": None,
    "system_prompt": "You are a helpful Discord chatbot called ChatBuddy.",
    "multimodal_enabled": False,
    "web_search_enabled": False,
    "duck_search_enabled": False,
    "api_context_enabled": False,
    "api_context_limit": 500,
    "api_context_reset_time": "00:00",
    "api_context_current_usage": 0,
    "api_context_last_reset_date": "",
    # Dual model endpoints â€” one for each mode
    "model_endpoint_gemini": "gemini-2.0-flash",
    "model_endpoint_gemma": "",
    # Custom (non-Google) model support
    "api_key_custom": "",
    "model_endpoint_custom": "",
    "temperature": 0.7,
    "chat_history_limit": 30,
    # Text model mode: "gemini" | "gemma" | "custom"
    "model_mode": "gemini",
    # Audio clip mode
    "audio_enabled": False,
    "audio_endpoint": "",
    "audio_settings": {"voice": "Aoede"},
    "ce_channels": {},        # {str(channel_id): bool}
    "allowed_channels": {},   # {str(channel_id): bool}
    "chat_revival": None,
    "cr_leave_message": "Ok nice chatting to you all, see you later",
    "cr_active_minutes": 5,
    "cr_check_seconds": 30,
    # Stream of Consciousness (SoC)
    "soc_channel_id": None,
    "soc_enabled": False,
    "soc_context_enabled": False,
    "soc_context_count": 10,
    # Dynamic system prompt â€” appended after main prompt when enabled
    "dynamic_prompt": "",
    "dynamic_prompt_enabled": False,
    # Word game
    "word_game_prompt": "",         # prompt text with {secret-word} placeholder
    "word_game_enabled": False,
    "word_game_selector_prompt": "",  # system prompt for hidden word-selection turn
    "secret_word": "",
    "secret_word_allowed_roles": [],  # role IDs allowed to use /set-secret-word
    # Soul (dynamic auto-updating memory)
    "soul_enabled": False,
    "soul_limit": 2000,
    "soul_error_turn": "",
    "soul_channel_enabled": False,
    "soul_channel_id": "",  # stores 1-turn error message if update fails
    # Auto-chat mode
    "auto_chat_enabled": False,
    "auto_chat_channel_id": None,
    "auto_chat_interval": 30,        # seconds between checks
    "auto_chat_idle_minutes": 10,    # idle timeout
    "auto_chat_idle_message": "Going afk, ping me if you need me",
    # Reminders & auto-wake
    "reminders_enabled": False,
    "reminders_channel_id": None,
    "reminder_log_channel_id": None,
    # Bot-to-bot response
    "respond_to_bot": False,
    "respond_bot_limit": 3,        # 1-9: stop if last N messages are all bots
    # Heartbeat
    "heartbeat_enabled": False,
    "heartbeat_interval_minutes": 60,
    "heartbeat_channel_id": None,
    "heartbeat_prompt": "",
    # â”€â”€ Tamagotchi (unified gamified system) â”€â”€
    "tama_enabled": False,
    "tama_stat_scale_version": 2,
    # Hunger
    "tama_hunger": 100.0,
    "tama_hunger_max": 100,
    "tama_hunger_depletion": 1.0,
    # Thirst
    "tama_thirst": 100.0,
    "tama_thirst_max": 100,
    "tama_thirst_depletion": 1.0,
    # Happiness
    "tama_happiness": 100.0,
    "tama_happiness_max": 100,
    "tama_happiness_depletion": 1.0,
    "tama_happiness_depletion_interval": 600,
    "tama_lonely_last_update_at": 0.0,
    # Health (counts down â€” death at 0)
    "tama_health": 100.0,
    "tama_health_max": 100,
    "tama_health_damage_per_stat": 10.0,
    "tama_health_threshold": 20.0,
    # Energy
    "tama_energy": 100.0,
    "tama_energy_max": 100,
    "tama_energy_depletion_api": 1.0,
    "tama_energy_depletion_game": 5.0,
    "tama_needs_depletion_per_energy": 1.0,
    "tama_energy_recharge_interval": 300,
    "tama_energy_recharge_amount": 5.0,
    "tama_last_interaction_at": 0.0,
    "tama_rest_duration": 300,
    "tama_cd_rest": 60,
    "tama_sleeping": False,
    "tama_sleep_until": 0.0,
    "tama_hatching": False,
    "tama_hatch_until": 0.0,
    "tama_hatch_channel_id": "",
    "tama_hatch_message_id": "",
    "tama_egg_hatch_time": 30,
    "tama_hatch_prompt": (
        "You have just hatched in this Discord server. Your life has begun right now. "
        "Send your very first message to the server."
    ),
    "tama_action_log": [],
    "tama_inventory_initialized": False,
    "tama_inventory_defaults_version": 5,
    "tama_inventory_items": {
        "unlimited_hamburger": {
            "name": "Hamburger",
            "emoji": "🍔",
            "item_type": "food",
            "multiplier": 1.0,
            "energy_multiplier": 1.0,
            "happiness_delta": 0.0,
            "button_style": "success",
            "amount": -1,
            "lucky_gift_prize": False,
            "store_in_inventory": True,
        },
        "unlimited_water": {
            "name": "Cup of Water",
            "emoji": "🥤",
            "item_type": "drink",
            "multiplier": 1.0,
            "energy_multiplier": 1.0,
            "happiness_delta": 0.0,
            "button_style": "primary",
            "amount": -1,
            "lucky_gift_prize": False,
            "store_in_inventory": True,
        },
        "teddy_bear": {
            "name": "Teddy Bear",
            "emoji": "🧸",
            "item_type": "misc",
            "multiplier": 0.0,
            "energy_multiplier": 0.0,
            "happiness_delta": 10.0,
            "button_style": "success",
            "amount": 0,
            "lucky_gift_prize": True,
            "store_in_inventory": True,
        },
        "sushi": {
            "name": "Sushi",
            "emoji": "🍣",
            "item_type": "food",
            "multiplier": 2.0,
            "energy_multiplier": 2.0,
            "happiness_delta": 0.0,
            "button_style": "primary",
            "amount": 0,
            "lucky_gift_prize": True,
            "store_in_inventory": True,
        },
        "meat_on_bone": {
            "name": "Meat on Bone",
            "emoji": "🍖",
            "item_type": "food",
            "multiplier": 3.0,
            "energy_multiplier": 3.0,
            "happiness_delta": 0.0,
            "button_style": "danger",
            "amount": 0,
            "lucky_gift_prize": True,
            "store_in_inventory": True,
        },
        "lump_of_coal": {
            "name": "Lump of Coal",
            "emoji": "⚫",
            "item_type": "misc",
            "multiplier": 0.0,
            "energy_multiplier": 0.0,
            "happiness_delta": -10.0,
            "button_style": "secondary",
            "amount": 0,
            "lucky_gift_prize": True,
            "store_in_inventory": False,
        },
    },
    # Dirtiness / poop
    "tama_dirt": 0,
    "tama_dirt_max": 4,
    "tama_dirt_food_threshold": 5,
    "tama_dirt_food_counter": 0,
    "tama_dirt_health_damage": 5.0,
    "tama_dirt_damage_interval": 600,
    "tama_dirt_grace_until": 0.0,
    "tama_dirt_poop_timer_max_minutes": 5,
    # Sickness (boolean flag)
    "tama_sick": False,
    "tama_sick_health_damage": 5.0,
    # Button actions - fill / effect amounts
    "tama_feed_amount": 10.0,
    "tama_feed_energy_every": 1,
    "tama_feed_energy_gain": 1.0,
    "tama_feed_energy_counter": 0,
    "tama_drink_amount": 10.0,
    "tama_drink_energy_every": 1,
    "tama_drink_energy_gain": 1.0,
    "tama_drink_energy_counter": 0,
    "tama_play_happiness": 10.0,
    "tama_lucky_gift_duration": 30,
    "tama_cd_lucky_gift": 600,
    "tama_medicate_health_heal": 20.0,
    "tama_medicate_happiness_cost": 3.0,
    # Button cooldowns (seconds, global)
    "tama_cd_feed": 60,
    "tama_cd_drink": 60,
    "tama_cd_other": 60,
    "tama_cd_play": 60,
    "tama_cd_medicate": 60,
    "tama_cd_clean": 60,
    # Configurable response messages
    "tama_resp_feed": "*nom nom* 🍔 Thanks for the food!",
    "tama_resp_drink": "*gulp gulp* 🥤 That hit the spot!",
    "tama_resp_play": "🎮 Let's play!",
    "tama_resp_medicate": "💊 Ahhh... feeling better already!",
    "tama_resp_medicate_healthy": "I'm not sick! No medicine needed.",
    "tama_resp_clean": "🚿 Squeaky clean!",
    "tama_resp_clean_none": "Already clean! No mess to tidy.",
    "tama_resp_poop": "oops i pooped",
    "tama_resp_cooldown": "⏳ Hold on! You can use this again in {time}.",
    "tama_resp_rest": "💤 Tucking in for a recharge. See you soon!",
    "tama_resp_sleeping": "I am sleeping come back in {time}",
    "tama_resp_no_energy": "⚡ I'm out of energy and need a rest first!",
    "tama_rip_message": "",
    # Command access
    "bot_owner_id": "",
    "command_allowed_user_ids": [],
    "main_chat_channel_id": "",
}


def _scaled_whole_number(value, *, minimum: float | None = None) -> float:
    scaled = math.ceil(max(0.0, float(value or 0.0)) * 10.0 - 1e-9)
    if minimum is not None:
        scaled = max(float(minimum), float(scaled))
    return float(scaled)


def _migrate_tamagotchi_scale(config: dict, stored: dict | None = None) -> bool:
    stored = stored or {}
    stored_version = int(stored.get("tama_stat_scale_version", 0) or 0)
    if stored_version >= 2:
        config["tama_stat_scale_version"] = 2
        return False

    should_scale_existing = any(
        key in stored
        for key in (
            "tama_hunger_max",
            "tama_thirst_max",
            "tama_happiness_max",
            "tama_health_max",
            "tama_energy_max",
        )
    )
    if not should_scale_existing:
        config["tama_stat_scale_version"] = 2
        return False

    for key in (
        "tama_hunger",
        "tama_hunger_max",
        "tama_thirst",
        "tama_thirst_max",
        "tama_happiness",
        "tama_happiness_max",
        "tama_health",
        "tama_health_max",
        "tama_energy",
        "tama_energy_max",
    ):
        config[key] = round(float(config.get(key, 0.0) or 0.0) * 10.0, 2)

    config["tama_hunger_depletion"] = 1.0
    config["tama_thirst_depletion"] = 1.0
    config["tama_happiness_depletion"] = _scaled_whole_number(config.get("tama_happiness_depletion", 0.1), minimum=1.0)
    config["tama_health_damage_per_stat"] = _scaled_whole_number(config.get("tama_health_damage_per_stat", 1.0), minimum=1.0)
    config["tama_health_threshold"] = _scaled_whole_number(config.get("tama_health_threshold", 2.0), minimum=1.0)
    config["tama_energy_depletion_api"] = _scaled_whole_number(config.get("tama_energy_depletion_api", 0.1), minimum=1.0)
    config["tama_energy_depletion_game"] = _scaled_whole_number(config.get("tama_energy_depletion_game", 0.5), minimum=1.0)
    config["tama_energy_recharge_amount"] = _scaled_whole_number(config.get("tama_energy_recharge_amount", 0.5), minimum=1.0)
    config["tama_dirt_health_damage"] = _scaled_whole_number(config.get("tama_dirt_health_damage", 0.5), minimum=1.0)
    config["tama_sick_health_damage"] = _scaled_whole_number(config.get("tama_sick_health_damage", 0.5), minimum=1.0)
    config["tama_feed_amount"] = _scaled_whole_number(config.get("tama_feed_amount", 1.0), minimum=1.0)
    config["tama_feed_energy_gain"] = _scaled_whole_number(config.get("tama_feed_energy_gain", 0.1), minimum=1.0)
    config["tama_drink_amount"] = _scaled_whole_number(config.get("tama_drink_amount", 1.0), minimum=1.0)
    config["tama_drink_energy_gain"] = _scaled_whole_number(config.get("tama_drink_energy_gain", 0.05), minimum=1.0)
    config["tama_play_happiness"] = _scaled_whole_number(config.get("tama_play_happiness", 1.0), minimum=1.0)
    config["tama_medicate_health_heal"] = _scaled_whole_number(config.get("tama_medicate_health_heal", 2.0), minimum=1.0)
    config["tama_medicate_happiness_cost"] = _scaled_whole_number(config.get("tama_medicate_happiness_cost", 0.3), minimum=1.0)

    items = config.get("tama_inventory_items", {})
    if isinstance(items, dict):
        teddy = items.get("teddy_bear")
        if isinstance(teddy, dict):
            teddy["happiness_delta"] = 10.0
        sushi = items.get("sushi")
        if isinstance(sushi, dict):
            sushi["multiplier"] = 2.0
            sushi["energy_multiplier"] = 2.0
        meat = items.get("meat_on_bone")
        if isinstance(meat, dict):
            meat["multiplier"] = 3.0
            meat["energy_multiplier"] = 3.0
        coal = items.get("lump_of_coal")
        if isinstance(coal, dict):
            coal["happiness_delta"] = -10.0

    config["tama_stat_scale_version"] = 2
    return True


def load_config() -> dict:
    """Load config from disk, falling back to defaults for any missing keys."""
    config = dict(DEFAULTS)
    stored: dict | None = None
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            config.update(stored)
        except (json.JSONDecodeError, OSError):
            pass  # Corrupted file â€” use defaults
    if _migrate_tamagotchi_scale(config, stored):
        save_config(config)
    return config


def save_config(config: dict) -> None:
    """Atomically write the config dict to disk."""
    tmp_path = CONFIG_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, CONFIG_FILE)

