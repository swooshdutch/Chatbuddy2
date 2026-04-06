"""Minigame Discord views for the Tamagotchi feature."""

from __future__ import annotations

import asyncio
import random

import discord
from discord import ui

from config import save_config

from .messages import append_tamagotchi_footer
from .runtime_support import build_tamagotchi_view
from .state import (
    _bot_display_name,
    _fs,
    _log_tamagotchi_action,
    apply_direct_energy_delta,
    apply_direct_happiness_delta,
    apply_rps_happiness_reward,
    can_use_energy,
    resolve_rps_outcome,
    should_auto_sleep,
)
from .stats import deplete_energy_game
from .view_helpers import build_cooldown_message, no_energy_message, send_sleep_block
from tamagotchi_inventory import _coerce_item_amount, get_inventory_items

_RPS_EMOJI = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}


def _lucky_gift_pool(config: dict) -> list[dict]:
    return [item for item in get_inventory_items(config, visible_only=False) if item.get("lucky_gift_prize")]


def _lucky_gift_countdown_text(
    config: dict,
    giver_name: str,
    bot_name: str,
    seconds_remaining: float,
) -> str:
    return (
        "🎁 **Lucky Gift**\n"
        f"**{giver_name}** is opening a present for **{bot_name}**.\n"
        "The ribbon is rustling... something fun is hiding inside.\n"
        f"Reveal in **{max(1, int(seconds_remaining + 0.999))}s**."
    )


def _apply_lucky_gift_reward(config: dict, item: dict) -> tuple[float, float, int, bool]:
    items = config.setdefault("tama_inventory_items", {})
    item_entry = items.get(item["id"])
    stored_in_inventory = bool(item.get("store_in_inventory", True))
    if stored_in_inventory and isinstance(item_entry, dict):
        current_amount = _coerce_item_amount(item_entry.get("amount", 0))
        if current_amount >= 0:
            item_entry["amount"] = current_amount + 1

    happiness_delta = round(float(item.get("happiness_delta", 0.0) or 0.0), 2)
    energy_delta = round(float(item.get("energy_delta", 0.0) or 0.0), 2)
    if not stored_in_inventory and happiness_delta:
        max_happy = float(config.get("tama_happiness_max", 100))
        previous_happiness = float(config.get("tama_happiness", 0.0) or 0.0)
        new_happiness = min(
            max_happy,
            max(0.0, round(previous_happiness + happiness_delta, 2)),
        )
        config["tama_happiness"] = new_happiness
        happiness_delta = round(new_happiness - previous_happiness, 2)
    if not stored_in_inventory and energy_delta:
        energy_delta = apply_direct_energy_delta(config, energy_delta)
    save_config(config)
    awarded_amount = 1 if stored_in_inventory and not item.get("is_unlimited") else 0
    return happiness_delta, energy_delta, awarded_amount, stored_in_inventory


def _lucky_gift_reveal_text(
    giver_name: str,
    bot_name: str,
    item: dict,
    happiness_delta: float,
    energy_delta: float,
    stored_in_inventory: bool,
) -> str:
    parts = [
        "🎁 **Lucky Gift Opened!**",
        (
            f"**{giver_name}** gifted **{bot_name}** a lucky gift, "
            f"**{giver_name}** received {item.get('emoji', '🎁')} **{item.get('name', 'a prize')}**."
        ),
    ]
    if item.get("item_type") in {"food", "drink"} and float(item.get("multiplier", 0.0) or 0.0) > 0:
        parts.append(f"Fill multiplier: x{item.get('multiplier', 1.0)}.")
    if stored_in_inventory:
        parts.append("Added to chat inventory.")
    if energy_delta > 0:
        parts.append(f"Energy +{_fs(energy_delta)} {'applied now' if not stored_in_inventory else 'when used'}.")
    elif energy_delta < 0:
        parts.append(f"Energy {_fs(energy_delta)} {'applied now' if not stored_in_inventory else 'when used'}.")
    if happiness_delta > 0:
        parts.append(f"Happiness +{_fs(happiness_delta)} {'applied now' if not stored_in_inventory else 'when used'}.")
    elif happiness_delta < 0:
        parts.append(f"Happiness {_fs(happiness_delta)} {'applied now' if not stored_in_inventory else 'when used'}.")
    return "\n".join(parts)


class GameSelectView(ui.View):
    def __init__(self, config: dict, manager, owner_id: int):
        super().__init__(timeout=300)
        self.config = config
        self.manager = manager
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This game menu belongs to someone else.", ephemeral=True)
            return False
        return True

    @ui.button(label="RPS", emoji="✂️", style=discord.ButtonStyle.secondary, row=0)
    async def rps_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await send_sleep_block(interaction, self.config)
            return
        if not can_use_energy(self.config):
            await interaction.response.send_message(no_energy_message(self.config), ephemeral=True)
            return
        remaining = self.manager.check_cooldown("rps")
        if remaining > 0:
            await interaction.response.send_message(build_cooldown_message(self.config, remaining), ephemeral=True)
            return

        happy_gain = float(self.config.get("tama_play_happiness", 0.0) or 0.0)
        if happy_gain:
            apply_direct_happiness_delta(self.config, happy_gain)

        deplete_energy_game(self.config)
        started_sleep = False
        if should_auto_sleep(self.config):
            self.manager.begin_rest(interaction.channel_id)
            started_sleep = True
        self.manager.set_cooldown("rps", self.config.get("tama_cd_rps", 60))

        bot_choice = random.choice(["rock", "paper", "scissors"])
        message = self.config.get("tama_resp_play", "🎮 Let's play!")
        rps_view = RPSView(self.config, self.manager, bot_choice)
        await interaction.response.edit_message(
            content=f"{message}\n**Rock, Paper, Scissors - pick your move!**",
            view=rps_view,
        )
        if started_sleep:
            await self.manager.send_sleep_announcement(interaction.channel_id)

    @ui.button(label="Lucky Gift", emoji="🎁", style=discord.ButtonStyle.secondary, row=0)
    async def lucky_gift_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.manager.record_interaction()
        if self.manager.sleeping:
            await send_sleep_block(interaction, self.config)
            return
        if not can_use_energy(self.config):
            await interaction.response.send_message(no_energy_message(self.config), ephemeral=True)
            return
        remaining = self.manager.check_cooldown("lucky_gift")
        if remaining > 0:
            await interaction.response.send_message(build_cooldown_message(self.config, remaining), ephemeral=True)
            return

        pool = _lucky_gift_pool(self.config)
        if not pool:
            await interaction.response.send_message("🎁 The lucky gift pool is empty right now.", ephemeral=True)
            return

        deplete_energy_game(self.config)
        started_sleep = False
        if should_auto_sleep(self.config):
            self.manager.begin_rest(interaction.channel_id)
            started_sleep = True
        self.manager.set_cooldown("lucky_gift", self.config.get("tama_cd_lucky_gift", 600))

        if interaction.channel is None:
            await interaction.response.send_message("🎁 I couldn't find a channel to open the gift in.", ephemeral=True)
            return

        duration = max(1, int(self.config.get("tama_lucky_gift_duration", 30)))
        giver_name = interaction.user.display_name
        bot_name = _bot_display_name(interaction)
        await interaction.response.defer()
        countdown_message = await interaction.channel.send(
            _lucky_gift_countdown_text(self.config, giver_name, bot_name, duration)
        )

        for seconds_left in range(duration - 1, 0, -1):
            await asyncio.sleep(1)
            try:
                await countdown_message.edit(
                    content=_lucky_gift_countdown_text(self.config, giver_name, bot_name, seconds_left),
                )
            except Exception:
                break

        prize = random.choice(pool)
        happiness_delta, energy_delta, _, stored_in_inventory = _apply_lucky_gift_reward(self.config, prize)
        reveal = _lucky_gift_reveal_text(
            giver_name,
            bot_name,
            prize,
            happiness_delta,
            energy_delta,
            stored_in_inventory,
        )
        try:
            await countdown_message.edit(
                content=append_tamagotchi_footer(reveal, self.config, self.manager),
                view=build_tamagotchi_view(self.config, self.manager),
            )
        except Exception:
            countdown_message = await interaction.channel.send(
                append_tamagotchi_footer(reveal, self.config, self.manager),
                view=build_tamagotchi_view(self.config, self.manager),
            )
        _log_tamagotchi_action(
            self.config,
            interaction,
            "lucky_gift",
            countdown_message.id,
            item_id=prize["id"],
            item_name=prize["name"],
            item_emoji=prize["emoji"],
        )
        if started_sleep:
            await self.manager.send_sleep_announcement(interaction.channel_id)


class RPSView(ui.View):
    def __init__(self, config: dict, manager, bot_choice: str):
        super().__init__(timeout=300)
        self.config = config
        self.manager = manager
        self.bot_choice = bot_choice

    async def _finish_round(self, interaction: discord.Interaction, user_choice: str) -> None:
        user_name = interaction.user.display_name
        bot_name = _bot_display_name(interaction)
        user_emoji = _RPS_EMOJI.get(user_choice, "🎮")
        bot_emoji = _RPS_EMOJI.get(self.bot_choice, "🎮")

        outcome_key = resolve_rps_outcome(user_choice, self.bot_choice)
        if outcome_key == "draw":
            outcome = "It's a draw."
        elif outcome_key == "user_win":
            outcome = f"**{user_name}** wins."
        else:
            outcome = f"**{bot_name}** wins."

        happiness_delta = apply_rps_happiness_reward(self.config, outcome_key)
        if happiness_delta:
            save_config(self.config)

        public_result = (
            "🎮 **Rock, Paper, Scissors**\n"
            f"**{user_name}** chose {user_emoji} **{user_choice.title()}**.\n"
            f"**{bot_name}** chose {bot_emoji} **{self.bot_choice.title()}**.\n"
            f"{outcome}"
        )
        if happiness_delta > 0:
            public_result += f"\n😊 Happiness +{_fs(happiness_delta)}."
        elif happiness_delta < 0:
            public_result += f"\n☹️ Happiness {_fs(happiness_delta)}."

        await interaction.response.edit_message(
            content=f"You picked {user_emoji} **{user_choice.title()}**. Result posted publicly.",
            view=None,
        )

        if interaction.channel is None:
            return

        result_message = await interaction.channel.send(
            append_tamagotchi_footer(public_result, self.config, self.manager),
            view=build_tamagotchi_view(self.config, self.manager),
        )
        _log_tamagotchi_action(
            self.config,
            interaction,
            "play",
            result_message.id,
        )

    @ui.button(label="Rock", emoji="🪨", style=discord.ButtonStyle.secondary, row=0)
    async def rock_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._finish_round(interaction, "rock")

    @ui.button(label="Paper", emoji="📄", style=discord.ButtonStyle.secondary, row=0)
    async def paper_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._finish_round(interaction, "paper")

    @ui.button(label="Scissors", emoji="✂️", style=discord.ButtonStyle.secondary, row=0)
    async def scissors_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._finish_round(interaction, "scissors")


__all__ = [
    "GameSelectView",
    "RPSView",
]
