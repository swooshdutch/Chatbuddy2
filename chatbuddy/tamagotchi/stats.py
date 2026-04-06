"""Stat depletion, reset, and death broadcast helpers for Tamagotchi."""

from __future__ import annotations

from config import save_config

from .messages import append_tamagotchi_footer
from .runtime_support import build_tamagotchi_view
from .state import (
    apply_loneliness,
    apply_low_energy_happiness_penalty,
    apply_need_depletion_from_energy,
    reset_tamagotchi_state,
    wipe_soul_file,
)


def deplete_stats(config: dict) -> str | None:
    """
    Called after every LLM inference. Applies time-based loneliness,
    depletes energy for the inference, converts that energy loss into
    hunger/thirst loss, applies health damage, and checks for death.

    Returns None normally, or a death-message string if death occurred.
    """
    if not config.get("tama_enabled", False):
        return None

    multiplier = 2.0 if float(config.get("tama_energy", 0.0) or 0.0) <= 0.0 else 1.0

    apply_loneliness(config)

    energy_loss = float(config.get("tama_energy_depletion_api", 1.0) or 0.0) * multiplier
    config["tama_energy"] = max(
        0.0,
        round(
            config.get("tama_energy", 0) - energy_loss,
            2,
        ),
    )
    apply_need_depletion_from_energy(config, energy_loss)
    apply_low_energy_happiness_penalty(config)

    threshold = float(config.get("tama_health_threshold", 20.0))
    low_hunger = float(config.get("tama_hunger", 0) or 0) < threshold
    low_thirst = float(config.get("tama_thirst", 0) or 0) < threshold
    if low_hunger or low_thirst:
        config["tama_sick"] = True

    dmg_per = config.get("tama_health_damage_per_stat", 10.0) * multiplier
    health_loss = 0.0
    for stat_key in ("tama_hunger", "tama_thirst", "tama_happiness"):
        if config.get(stat_key, 0) < threshold:
            health_loss += dmg_per

    if config.get("tama_sick", False):
        health_loss += config.get("tama_sick_health_damage", 5.0) * multiplier
        dirt = int(config.get("tama_dirt", 0) or 0)
        if dirt > 0:
            health_loss += float(config.get("tama_dirt_health_damage", 5.0)) * dirt * multiplier

    if health_loss > 0:
        config["tama_health"] = max(
            0.0, round(config.get("tama_health", 0) - health_loss, 2)
        )

    if config.get("tama_sick", False):
        config["tama_dirt_grace_until"] = 0.0

    save_config(config)

    if config["tama_health"] <= 0:
        return trigger_death(config)

    return None


def deplete_energy_game(config: dict):
    """Called when a game is played; deducts game energy cost."""
    if not config.get("tama_enabled", False):
        return
    multiplier = 2.0 if float(config.get("tama_energy", 0.0) or 0.0) <= 0.0 else 1.0
    energy_loss = float(config.get("tama_energy_depletion_game", 5.0) or 0.0) * multiplier
    config["tama_energy"] = max(
        0.0,
        round(
            config.get("tama_energy", 0) - energy_loss,
            2,
        ),
    )
    apply_need_depletion_from_energy(config, energy_loss)
    save_config(config)


def trigger_death(config: dict) -> str:
    """
    Wipe soul.md, reset all stats to max, clear sickness.
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
    """Send [ce] to every allowed channel plus the SoC channel."""
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
        channel = bot.get_channel(ch_id)
        if channel is not None:
            try:
                await channel.send("[ce]")
            except Exception as exc:
                print(f"[Tamagotchi] Failed to send [ce] to channel {ch_id}: {exc}")
    if tama_manager and config.get("tama_enabled", False):
        await tama_manager.start_egg_cycle(
            wipe_soul=False,
            reset_stats=False,
            send_ce=False,
        )


async def _broadcast_death_and_message(bot, config: dict, death_msg: str):
    """Post a death message in all allowed channels, then broadcast [ce]."""
    tama_view = None
    tama_manager = getattr(bot, "tama_manager", None)
    if config.get("tama_enabled", False) and tama_manager:
        tama_manager.clear_poop_timers()
        tama_view = build_tamagotchi_view(config, tama_manager)
    for ch_id_str, enabled in config.get("allowed_channels", {}).items():
        if enabled:
            try:
                channel = bot.get_channel(int(ch_id_str))
                if channel:
                    await channel.send(
                        append_tamagotchi_footer(death_msg, config, tama_manager),
                        view=tama_view,
                    )
            except Exception:
                pass
    await broadcast_death(bot, config)


__all__ = [
    "_broadcast_death_and_message",
    "broadcast_death",
    "deplete_energy_game",
    "deplete_stats",
    "trigger_death",
]
