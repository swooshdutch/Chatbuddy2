"""Tamagotchi item and action configuration commands."""

from ..common import *

@bot.tree.command(name="set-tama-feed", description="Configure the feed button")
@app_commands.describe(
    amount="Hunger restored per feed",
    cooldown="Cooldown in seconds",
    energy_every="Grant energy on every Nth feed",
    energy_gain="Energy granted when the Nth feed is reached",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_feed(
    interaction: discord.Interaction,
    amount: float,
    cooldown: int,
    energy_every: int,
    energy_gain: float,
):
    if cooldown < 0:
        await interaction.response.send_message("⚠️ Cooldown must be ≥ 0.", ephemeral=True)
        return
    if energy_every < 1:
        await interaction.response.send_message("⚠️ Energy trigger must be at least every 1 feed.", ephemeral=True)
        return
    if energy_gain < 0:
        await interaction.response.send_message("⚠️ Energy gain must be ≥ 0.", ephemeral=True)
        return
    bot_config["tama_feed_amount"] = amount
    bot_config["tama_cd_feed"] = cooldown
    bot_config["tama_feed_energy_every"] = energy_every
    bot_config["tama_feed_energy_gain"] = energy_gain
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Feed: +**{amount}** hunger, **{cooldown}s** cooldown, "
        f"+**{energy_gain}** energy every **{energy_every}** feeds.",
        ephemeral=True,
    )


@bot.tree.command(name="set-tama-drink", description="Configure the drink button")
@app_commands.describe(
    amount="Thirst restored per drink",
    cooldown="Cooldown in seconds",
    energy_every="Grant energy on every Nth drink",
    energy_gain="Energy granted when the Nth drink is reached",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_drink(
    interaction: discord.Interaction,
    amount: float,
    cooldown: int,
    energy_every: int,
    energy_gain: float,
):
    if cooldown < 0:
        await interaction.response.send_message("⚠️ Cooldown must be ≥ 0.", ephemeral=True)
        return
    if energy_every < 1:
        await interaction.response.send_message("⚠️ Energy trigger must be at least every 1 drink.", ephemeral=True)
        return
    if energy_gain < 0:
        await interaction.response.send_message("⚠️ Energy gain must be ≥ 0.", ephemeral=True)
        return
    bot_config["tama_drink_amount"] = amount
    bot_config["tama_cd_drink"] = cooldown
    bot_config["tama_drink_energy_every"] = energy_every
    bot_config["tama_drink_energy_gain"] = energy_gain
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Drink: +**{amount}** thirst, **{cooldown}s** cooldown, "
        f"+**{energy_gain}** energy every **{energy_every}** drinks.",
        ephemeral=True,
    )


@bot.tree.command(name="add-tama-item", description="Add or update a Tamagotchi inventory item")
@app_commands.describe(
    name="Display name for the inventory item",
    item_type="Whether this item is food, drink, or misc",
    emoji="Emoji shown on the inventory button and public response",
    multiplier="Fill multiplier based on the configured feed/drink amount",
    energy_multiplier="Energy multiplier based on the configured feed/drink energy gain",
    happiness_amount="Happiness granted or removed when this item is won from Lucky Gift",
    button_color="Discord button color for the inventory item",
    energy_amount="Direct energy granted or removed when the item is used or applied instantly",
    amount="Starting amount for limited items",
    unlimited="Set true for infinite stock",
    lucky_gift_prize="Whether this item can be won from Lucky Gift",
    store_in_inventory="True = reward becomes an inventory item, False = apply effect instantly when won",
)
@app_commands.choices(
    item_type=[
        app_commands.Choice(name="food", value="food"),
        app_commands.Choice(name="drink", value="drink"),
        app_commands.Choice(name="misc", value="misc"),
    ],
    button_color=[
        app_commands.Choice(name="blue", value="primary"),
        app_commands.Choice(name="gray", value="secondary"),
        app_commands.Choice(name="green", value="success"),
        app_commands.Choice(name="red", value="danger"),
    ],
)
@app_commands.default_permissions(administrator=True)
async def add_tama_item(
    interaction: discord.Interaction,
    name: str,
    item_type: app_commands.Choice[str],
    emoji: str,
    multiplier: float,
    energy_multiplier: float,
    happiness_amount: float,
    button_color: app_commands.Choice[str],
    energy_amount: float = 0.0,
    amount: int = 0,
    unlimited: bool = False,
    lucky_gift_prize: bool = False,
    store_in_inventory: bool = True,
):
    ensure_inventory_defaults(bot_config)
    if multiplier < 0:
        await interaction.response.send_message("⚠️ Multiplier must be ≥ 0.", ephemeral=True)
        return
    if energy_multiplier < 0:
        await interaction.response.send_message("⚠️ Energy multiplier must be ≥ 0.", ephemeral=True)
        return
    if not unlimited and amount < 0:
        await interaction.response.send_message("⚠️ Limited items must start with 0 or more in stock.", ephemeral=True)
        return

    item_id = inventory_item_id_from_name(name)
    bot_config.setdefault("tama_inventory_items", {})
    bot_config["tama_inventory_items"][item_id] = {
        "name": name.strip() or "Item",
        "emoji": emoji.strip() or ("🍔" if item_type.value == "food" else ("🥤" if item_type.value == "drink" else "🎁")),
        "item_type": item_type.value,
        "multiplier": round(multiplier, 2),
        "energy_multiplier": round(energy_multiplier, 2),
        "energy_delta": round(energy_amount, 2),
        "happiness_delta": round(happiness_amount, 2),
        "button_style": button_color.value,
        "amount": -1 if unlimited else amount,
        "lucky_gift_prize": lucky_gift_prize,
        "store_in_inventory": store_in_inventory,
    }
    save_config(bot_config)
    stored_item = next((item for item in get_inventory_items(bot_config, visible_only=False) if item["id"] == item_id), None)
    await interaction.response.send_message(
        "✅ Tamagotchi inventory item saved:\n" + _format_tama_item_summary(stored_item or {"id": item_id, "name": name}),
        ephemeral=True,
    )


@bot.tree.command(name="show-tama-items", description="Show all Tamagotchi inventory items")
@app_commands.default_permissions(administrator=True)
async def show_tama_items(interaction: discord.Interaction):
    ensure_inventory_defaults(bot_config)
    items = get_inventory_items(bot_config, visible_only=False)
    visible_count = len(get_inventory_items(bot_config, visible_only=True))
    lines = ["🎒 **Tamagotchi Inventory Items**"]
    if items:
        lines.extend(_format_tama_item_summary(item) for item in items)
        lines.append(f"\nVisible in inventory right now: **{visible_count}**")
    else:
        lines.append("No items are configured.")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="remove-tama-item", description="Remove a Tamagotchi inventory item")
@app_commands.describe(name_or_id="Item name or item id shown by /show-tama-items")
@app_commands.default_permissions(administrator=True)
async def remove_tama_item(interaction: discord.Interaction, name_or_id: str):
    ensure_inventory_defaults(bot_config)
    item_id = _resolve_tama_item_id(name_or_id)
    if not item_id:
        await interaction.response.send_message("⚠️ I couldn't find that item.", ephemeral=True)
        return
    removed = bot_config.get("tama_inventory_items", {}).pop(item_id, None)
    save_config(bot_config)
    removed_name = (removed or {}).get("name", item_id)
    await interaction.response.send_message(
        f"✅ Removed Tamagotchi inventory item **{removed_name}** (`{item_id}`).",
        ephemeral=True,
    )


@bot.tree.command(name="set-tama-play", description="Configure the play button")
@app_commands.describe(
    base_happiness="Base happiness gained when a play session starts",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_play(
    interaction: discord.Interaction,
    base_happiness: float,
):
    if base_happiness < 0:
        await interaction.response.send_message("⚠️ Base happiness must be ≥ 0.", ephemeral=True)
        return
    bot_config["tama_play_happiness"] = round(base_happiness, 2)
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Play: base +**{base_happiness:g}** happiness per session. "
        "The Play button is just the game menu, so it has no cooldown. "
        "RPS is configured separately with `/set-rps-rewards` and `/set-rps-cooldown`.",
        ephemeral=True,
    )


@bot.tree.command(name="set-rps-cooldown", description="Configure the Rock-Paper-Scissors cooldown")
@app_commands.describe(cooldown="Cooldown in seconds between RPS games")
@app_commands.default_permissions(administrator=True)
async def set_rps_cooldown(
    interaction: discord.Interaction,
    cooldown: int,
):
    if cooldown < 0:
        await interaction.response.send_message("⚠️ Cooldown must be ≥ 0.", ephemeral=True)
        return
    bot_config["tama_cd_rps"] = cooldown
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ RPS cooldown: **{cooldown}s**. The Play button itself stays cooldown-free.",
        ephemeral=True,
    )


@bot.tree.command(name="set-rps-rewards", description="Configure Rock-Paper-Scissors happiness rewards")
@app_commands.describe(
    user_wins="Happiness gained when the user wins and the bot loses",
    draw="Happiness gained when the round ends in a draw",
    bot_wins="Happiness gained when the bot wins and the user loses",
)
@app_commands.default_permissions(administrator=True)
async def set_rps_rewards(
    interaction: discord.Interaction,
    user_wins: float,
    draw: float,
    bot_wins: float,
):
    if user_wins < 0 or draw < 0 or bot_wins < 0:
        await interaction.response.send_message("⚠️ RPS rewards must be ≥ 0.", ephemeral=True)
        return
    bot_config["tama_rps_reward_user_win"] = round(user_wins, 2)
    bot_config["tama_rps_reward_draw"] = round(draw, 2)
    bot_config["tama_rps_reward_bot_win"] = round(bot_wins, 2)
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ RPS rewards: user win +**{user_wins:g}**, draw +**{draw:g}**, bot win +**{bot_wins:g}** happiness.",
        ephemeral=True,
    )


@bot.tree.command(name="set-tama-lucky-gift", description="Configure Lucky Gift cooldown and reveal timer")
@app_commands.describe(
    cooldown="How long Lucky Gift stays on cooldown in seconds",
    reveal_time="How long the gift countdown lasts before revealing the prize",
    other_item_cooldown="Cooldown in seconds for using misc inventory items like teddy bears",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_lucky_gift(
    interaction: discord.Interaction,
    cooldown: int,
    reveal_time: int,
    other_item_cooldown: int = 60,
):
    if cooldown < 0:
        await interaction.response.send_message("⚠️ Cooldown must be ≥ 0.", ephemeral=True)
        return
    if reveal_time < 1:
        await interaction.response.send_message("⚠️ Reveal time must be at least 1 second.", ephemeral=True)
        return
    if other_item_cooldown < 0:
        await interaction.response.send_message("⚠️ Other item cooldown must be ≥ 0.", ephemeral=True)
        return
    bot_config["tama_cd_lucky_gift"] = cooldown
    bot_config["tama_lucky_gift_duration"] = reveal_time
    bot_config["tama_cd_other"] = other_item_cooldown
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Lucky Gift: cooldown **{cooldown}s**, reveal timer **{reveal_time}s**, other-item cooldown **{other_item_cooldown}s**.",
        ephemeral=True,
    )


@bot.tree.command(name="set-tama-medicate", description="Configure the medicate button")
@app_commands.describe(
    cooldown="Cooldown in seconds",
    heal_amount="Health restored by medicine",
    happiness_cost="Happiness lost when medicine is used",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_medicate(
    interaction: discord.Interaction,
    cooldown: int,
    heal_amount: float,
    happiness_cost: float,
):
    if cooldown < 0:
        await interaction.response.send_message("⚠️ Cooldown must be ≥ 0.", ephemeral=True)
        return
    if heal_amount < 0 or happiness_cost < 0:
        await interaction.response.send_message("⚠️ Heal amount and happiness cost must be ≥ 0.", ephemeral=True)
        return
    bot_config["tama_cd_medicate"] = cooldown
    bot_config["tama_medicate_health_heal"] = heal_amount
    bot_config["tama_medicate_happiness_cost"] = happiness_cost
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Medicate: cooldown **{cooldown}s**, heal **{heal_amount}** HP, cost **{happiness_cost}** happiness.",
        ephemeral=True
    )


@bot.tree.command(name="set-tama-clean", description="Configure the clean button")
@app_commands.describe(cooldown="Cooldown in seconds")
@app_commands.default_permissions(administrator=True)
async def set_tama_clean(interaction: discord.Interaction, cooldown: int):
    if cooldown < 0:
        await interaction.response.send_message("⚠️ Cooldown must be ≥ 0.", ephemeral=True)
        return
    bot_config["tama_cd_clean"] = cooldown
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Clean cooldown: **{cooldown}s**.", ephemeral=True
    )


@bot.tree.command(name="set-tama-rip-message", description="Set the death message (empty = default)")
@app_commands.describe(message="Custom death message text")
@app_commands.default_permissions(administrator=True)
async def set_tama_rip_message(interaction: discord.Interaction, message: str):
    bot_config["tama_rip_message"] = message.strip()
    save_config(bot_config)
    if message.strip():
        await interaction.response.send_message(
            f"✅ Death message set:\n{message.strip()}", ephemeral=True
        )
    else:
        await interaction.response.send_message("✅ Death message reset to default.", ephemeral=True)



