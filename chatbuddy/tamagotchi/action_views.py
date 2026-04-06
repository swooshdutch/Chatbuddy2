"""Primary action buttons for the Tamagotchi Discord UI."""

from __future__ import annotations

import discord
from discord import ui

from config import save_config

from .game_views import GameSelectView
from .messages import append_tamagotchi_footer
from .runtime_support import build_tamagotchi_view
from .state import can_use_energy
from .view_helpers import build_cooldown_message, no_energy_message, public_action_message, send_sleep_block


class ChatterButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="Chatter",
            emoji="💬",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_chatter",
            row=0,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await send_sleep_block(interaction, self.config)
            return

        remaining = self.manager.check_cooldown("chatter")
        if remaining > 0:
            await interaction.response.send_message(build_cooldown_message(self.config, remaining), ephemeral=True)
            return

        self.manager.set_cooldown("chatter", int(self.config.get("tama_chatter_cooldown", 30)))
        await interaction.response.send_message("💬 Letting the bot jump into the conversation...", ephemeral=True)
        if interaction.channel is not None:
            await self.manager.run_chatter_prompt(interaction.channel)


class PlayButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="🎮 Play",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_play",
            row=0,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await send_sleep_block(interaction, self.config)
            return

        if not can_use_energy(self.config):
            await interaction.response.send_message(no_energy_message(self.config), ephemeral=True)
            return

        await interaction.response.send_message(
            "🎮 Choose a game to play.",
            view=GameSelectView(self.config, self.manager, interaction.user.id),
            ephemeral=True,
        )


class MedicateButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="💉 Medicate",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_medicate",
            row=0,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await send_sleep_block(interaction, self.config)
            return

        remaining = self.manager.check_cooldown("medicate")
        if remaining > 0:
            await interaction.response.send_message(build_cooldown_message(self.config, remaining), ephemeral=True)
            return

        max_health = float(self.config.get("tama_health_max", 100))
        current_health = float(self.config.get("tama_health", 0))
        is_sick = self.config.get("tama_sick", False)
        dirt = int(self.config.get("tama_dirt", 0) or 0)
        threshold = float(self.config.get("tama_health_threshold", 20.0))
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
            message = self.config.get("tama_resp_medicate_healthy", "I'm not sick!")
            await interaction.response.send_message(message, ephemeral=True)
            return

        heal_amount = max(0.0, float(self.config.get("tama_medicate_health_heal", 20.0)))
        happiness_cost = max(0.0, float(self.config.get("tama_medicate_happiness_cost", 3.0)))
        self.config["tama_sick"] = False
        self.config["tama_health"] = min(max_health, round(current_health + heal_amount, 2))
        self.config["tama_happiness"] = max(
            0.0,
            round(float(self.config.get("tama_happiness", 0)) - happiness_cost, 2),
        )
        save_config(self.config)
        self.manager.set_cooldown("medicate", self.config.get("tama_cd_medicate", 60))
        message = self.config.get("tama_resp_medicate", "💊 Feeling better!")
        message = public_action_message(
            interaction,
            message,
            action_summary="gave **{bot_name}** medicine",
        )
        await interaction.response.send_message(
            append_tamagotchi_footer(message, self.config, self.manager),
            view=build_tamagotchi_view(self.config, self.manager),
        )


class CleanButton(ui.Button):
    def __init__(self, config, manager):
        super().__init__(
            label="🚿 Clean",
            style=discord.ButtonStyle.secondary,
            custom_id="tama_clean",
            row=0,
        )
        self.config = config
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await send_sleep_block(interaction, self.config)
            return

        remaining = self.manager.check_cooldown("clean")
        if remaining > 0:
            await interaction.response.send_message(build_cooldown_message(self.config, remaining), ephemeral=True)
            return

        if self.config.get("tama_dirt", 0) <= 0:
            message = self.config.get("tama_resp_clean_none", "Already clean!")
            await interaction.response.send_message(message, ephemeral=True)
            return

        self.config["tama_dirt"] = 0
        self.config["tama_dirt_grace_until"] = 0.0
        save_config(self.config)
        self.manager._clear_dirt_grace(save=False)
        self.manager.set_cooldown("clean", self.config.get("tama_cd_clean", 60))
        message = self.config.get("tama_resp_clean", "🚿 Squeaky clean!")
        message = public_action_message(
            interaction,
            message,
            action_summary="gave **{bot_name}** a shower",
        )
        await interaction.response.send_message(
            append_tamagotchi_footer(message, self.config, self.manager),
            view=build_tamagotchi_view(self.config, self.manager),
        )


__all__ = [
    "ChatterButton",
    "CleanButton",
    "MedicateButton",
    "PlayButton",
]
