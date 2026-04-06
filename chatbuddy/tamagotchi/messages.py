"""Prompt and footer rendering helpers for the Tamagotchi feature."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .state import _discord_relative_epoch, _fs, happiness_emoji, is_sleeping

if TYPE_CHECKING:
    from .runtime import TamagotchiManager


def build_tamagotchi_system_prompt(config: dict) -> str:
    """Build the system-prompt injection describing current Tamagotchi state."""
    if not config.get("tama_enabled", False):
        return ""

    hunger = config.get("tama_hunger", 0)
    thirst = config.get("tama_thirst", 0)
    happiness = config.get("tama_happiness", 0)
    health = config.get("tama_health", 0)
    energy = config.get("tama_energy", 0)
    dirt = config.get("tama_dirt", 0)
    sick = config.get("tama_sick", False)
    sleeping = is_sleeping(config)

    max_hunger = config.get("tama_hunger_max", 100)
    max_thirst = config.get("tama_thirst_max", 100)
    max_happy = config.get("tama_happiness_max", 100)
    max_health = config.get("tama_health_max", 100)
    max_energy = config.get("tama_energy_max", 100)
    max_dirt = config.get("tama_dirt_max", 4)

    lines = [
        "[TAMAGOTCHI STATUS - Your virtual pet stats. "
        "These are managed by script; you cannot change them yourself.",
        f"Hunger: {_fs(hunger)}/{max_hunger}",
        f"Thirst: {_fs(thirst)}/{max_thirst}",
        f"Happiness: {_fs(happiness)}/{max_happy}",
        f"Health: {_fs(health)}/{max_health}",
        f"Energy: {_fs(energy)}/{max_energy}",
        f"Dirtiness (poop): {dirt}/{max_dirt}",
        f"Sick: {'YES' if sick else 'No'}",
        f"Sleeping: {'YES' if sleeping else 'No'}",
        "Users interact via buttons (inventory, chatter, play, medicate, clean). "
        "Hunger and thirst drop when you spend energy. Happiness drops from loneliness over time without interaction. "
        "When energy hits 0 you automatically go to sleep before acting again, and all energy-linked stat loss is doubled until that happens. "
        "If your health reaches 0, you die - your soul is wiped and stats reset.]",
    ]
    return "\n".join(lines)


def build_tamagotchi_message_footer(
    config: dict,
    manager: TamagotchiManager | None = None,
) -> str:
    """Compact mobile-friendly footer appended to public messages."""
    if not config.get("tama_enabled", False):
        return ""

    parts = [
        f"🍔 {_fs(config.get('tama_hunger', 0))}/{config.get('tama_hunger_max', 100)}",
        f"🥤 {_fs(config.get('tama_thirst', 0))}/{config.get('tama_thirst_max', 100)}",
        f"{happiness_emoji(config)} {_fs(config.get('tama_happiness', 0))}/{config.get('tama_happiness_max', 100)}",
        f"❤️ {_fs(config.get('tama_health', 0))}/{config.get('tama_health_max', 100)}",
        f"⚡ {_fs(config.get('tama_energy', 0))}/{config.get('tama_energy_max', 100)}",
        f"💩 {config.get('tama_dirt', 0)}/{config.get('tama_dirt_max', 4)}",
    ]

    if config.get("tama_sick", False):
        parts.append("💀 Sick")
    if manager and manager.sleeping:
        parts.append(f"💤 {_discord_relative_epoch(manager._sleep_expiry)}")

    return "\n> -# **" + " | ".join(parts) + "**"


def append_tamagotchi_footer(
    text: str,
    config: dict,
    manager: TamagotchiManager | None = None,
) -> str:
    footer = build_tamagotchi_message_footer(config, manager)
    if not footer:
        return text
    if not text:
        return footer.lstrip("\n")
    return text.rstrip() + footer


__all__ = [
    "append_tamagotchi_footer",
    "build_tamagotchi_message_footer",
    "build_tamagotchi_system_prompt",
]
