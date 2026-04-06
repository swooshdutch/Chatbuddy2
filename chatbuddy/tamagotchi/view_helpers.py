"""Shared helpers used by the split Tamagotchi Discord views."""

from __future__ import annotations

import discord

from .state import (
    _actor_display_name,
    _bot_display_name,
    _discord_relative_time,
    build_sleeping_message,
    render_tamagotchi_action_message,
)


async def send_sleep_block(interaction: discord.Interaction, config: dict):
    await interaction.response.send_message(build_sleeping_message(config), ephemeral=True)


def no_energy_message(config: dict) -> str:
    return config.get("tama_resp_no_energy", "⚡ I'm out of energy and need a rest first!")


def build_cooldown_message(config: dict, remaining: float) -> str:
    return config.get("tama_resp_cooldown", "⏳ Wait {time}.").replace(
        "{time}", _discord_relative_time(remaining)
    )


def interaction_actor_name(interaction: discord.Interaction) -> str:
    return _actor_display_name(interaction.user)


def public_action_message(
    interaction: discord.Interaction,
    message: str,
    *,
    action_summary: str,
    item: dict | None = None,
) -> str:
    bot_name = _bot_display_name(interaction)
    actor_name = interaction_actor_name(interaction)
    return render_tamagotchi_action_message(
        message,
        actor_name=actor_name,
        action_summary=action_summary.format(bot_name=bot_name),
        bot_name=bot_name,
        item_name=item.get("name", "") if item else "",
        item_emoji=item.get("emoji", "") if item else "",
    )


__all__ = [
    "build_cooldown_message",
    "interaction_actor_name",
    "no_energy_message",
    "public_action_message",
    "send_sleep_block",
]
