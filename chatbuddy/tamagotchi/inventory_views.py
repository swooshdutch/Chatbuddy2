"""Inventory-specific Discord views and item consumption helpers."""

from __future__ import annotations

import discord
from discord import ui

from config import save_config

from .messages import append_tamagotchi_footer
from .runtime_support import build_tamagotchi_view
from .state import (
    _apply_item_emoji_to_response,
    _fs,
    _item_action_name,
    _log_tamagotchi_action,
    apply_direct_energy_delta,
)
from .view_helpers import build_cooldown_message, public_action_message, send_sleep_block
from tamagotchi_inventory import get_inventory_item, get_inventory_items, inventory_button_style, inventory_message_text


async def _refresh_inventory_message(
    interaction: discord.Interaction,
    config: dict,
    manager,
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
    manager,
    item_id: str,
) -> None:
    manager.record_interaction()
    item = get_inventory_item(config, item_id)
    if not item or not (item["is_unlimited"] or item["amount"] > 0):
        await interaction.response.send_message("⚠️ That item is not in the inventory right now.", ephemeral=True)
        await _refresh_inventory_message(interaction, config, manager)
        return

    if manager.sleeping:
        await send_sleep_block(interaction, config)
        return

    action = _item_action_name(item)
    remaining = manager.check_cooldown(action)
    if remaining > 0:
        await interaction.response.send_message(build_cooldown_message(config, remaining), ephemeral=True)
        return

    multiplier = max(0.0, float(item.get("multiplier", 1.0) or 0.0))

    if action == "feed":
        max_hunger = float(config.get("tama_hunger_max", 100))
        fill = float(config.get("tama_feed_amount", 10.0)) * multiplier
        config["tama_hunger"] = min(max_hunger, round(float(config.get("tama_hunger", 0)) + fill, 2))

        food_energy_counter = int(config.get("tama_feed_energy_counter", 0)) + 1
        food_energy_every = max(1, int(config.get("tama_feed_energy_every", 1)))
        config["tama_feed_energy_counter"] = food_energy_counter
        if food_energy_counter >= food_energy_every:
            config["tama_feed_energy_counter"] = 0
            energy_multiplier = max(0.0, float(item.get("energy_multiplier", 1.0) or 0.0))
            energy_gain = max(0.0, float(config.get("tama_feed_energy_gain", 1.0))) * energy_multiplier
            apply_direct_energy_delta(config, energy_gain)

        config["tama_dirt_food_counter"] = int(config.get("tama_dirt_food_counter", 0)) + 1
        poop_threshold = max(1, int(config.get("tama_dirt_food_threshold", 5)))
        while config["tama_dirt_food_counter"] >= poop_threshold:
            config["tama_dirt_food_counter"] -= poop_threshold
            manager.queue_poop_timer(interaction.channel_id)
        response_key = "tama_resp_feed"
        cooldown_key = "tama_cd_feed"
    elif action == "drink":
        max_thirst = float(config.get("tama_thirst_max", 100))
        fill = float(config.get("tama_drink_amount", 10.0)) * multiplier
        config["tama_thirst"] = min(max_thirst, round(float(config.get("tama_thirst", 0)) + fill, 2))

        drink_energy_counter = int(config.get("tama_drink_energy_counter", 0)) + 1
        drink_energy_every = max(1, int(config.get("tama_drink_energy_every", 1)))
        config["tama_drink_energy_counter"] = drink_energy_counter
        if drink_energy_counter >= drink_energy_every:
            config["tama_drink_energy_counter"] = 0
            energy_multiplier = max(0.0, float(item.get("energy_multiplier", 1.0) or 0.0))
            energy_gain = max(0.0, float(config.get("tama_drink_energy_gain", 1.0))) * energy_multiplier
            apply_direct_energy_delta(config, energy_gain)
        response_key = "tama_resp_drink"
        cooldown_key = "tama_cd_drink"
    else:
        happiness_delta = round(float(item.get("happiness_delta", 0.0) or 0.0), 2)
        max_happy = float(config.get("tama_happiness_max", 100))
        config["tama_happiness"] = min(
            max_happy,
            max(0.0, round(float(config.get("tama_happiness", 0)) + happiness_delta, 2)),
        )
        response_key = None
        cooldown_key = "tama_cd_other"

    direct_energy_delta = apply_direct_energy_delta(config, float(item.get("energy_delta", 0.0) or 0.0))

    if not item["is_unlimited"]:
        config["tama_inventory_items"][item_id]["amount"] = max(0, item["amount"] - 1)

    save_config(config)
    manager.set_cooldown(action, int(config.get(cooldown_key, 60)))

    if action == "feed":
        default_response = "*nom nom* 🍔 Thanks for the food!"
        message = config.get(response_key, default_response)
        message = _apply_item_emoji_to_response(message, item)
        message = public_action_message(
            interaction,
            message,
            action_summary="fed **{bot_name}**",
            item=item,
        )
    elif action == "drink":
        default_response = "*gulp gulp* 🥤 That hit the spot!"
        message = config.get(response_key, default_response)
        message = _apply_item_emoji_to_response(message, item)
        message = public_action_message(
            interaction,
            message,
            action_summary="gave **{bot_name}** a drink",
            item=item,
        )
    else:
        happiness_delta = round(float(item.get("happiness_delta", 0.0) or 0.0), 2)
        message = f"{item.get('emoji', '🎁')} Used **{item.get('name', 'item')}**."
        if direct_energy_delta > 0:
            message += f"\n⚡ Energy +{_fs(direct_energy_delta)}."
        elif direct_energy_delta < 0:
            message += f"\n⚡ Energy {_fs(direct_energy_delta)}."
        if happiness_delta > 0:
            message += f"\n😊 Happiness +{_fs(happiness_delta)}."
        elif happiness_delta < 0:
            message += f"\n☹️ Happiness {_fs(happiness_delta)}."
        message = public_action_message(
            interaction,
            message,
            action_summary="used {item_emoji} **{item_name}** on **{bot_name}**".format(
                item_emoji=item.get("emoji", "🎁"),
                item_name=item.get("name", "item"),
                bot_name="{bot_name}",
            ),
            item=item,
        )
    await interaction.response.send_message(
        append_tamagotchi_footer(message, config, manager),
        view=build_tamagotchi_view(config, manager),
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
    def __init__(self, config: dict, manager, owner_id: int):
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
    def __init__(self, config: dict, manager, item: dict, row: int = 0):
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


__all__ = [
    "InventoryButton",
    "InventoryItemButton",
    "InventoryView",
]
