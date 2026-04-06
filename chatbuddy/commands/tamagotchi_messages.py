"""Tamagotchi response and admin commands."""

from ..common import *
# â”€â”€ Response message commands â”€â”€

@bot.tree.command(name="set-resp-food", description="Set the response message for feeding")
@app_commands.describe(message="Message shown when someone feeds the bot")
@app_commands.default_permissions(administrator=True)
async def set_resp_food(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_feed"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ Feed response set.", ephemeral=True)


@bot.tree.command(name="set-resp-drink", description="Set the response message for drinking")
@app_commands.describe(message="Message shown when someone gives a drink")
@app_commands.default_permissions(administrator=True)
async def set_resp_drink(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_drink"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ Drink response set.", ephemeral=True)


@bot.tree.command(name="set-resp-play", description="Set the response message for playing")
@app_commands.describe(message="Message shown when starting a play session")
@app_commands.default_permissions(administrator=True)
async def set_resp_play(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_play"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ Play response set.", ephemeral=True)


@bot.tree.command(name="set-resp-medicate", description="Set the response message for medicating")
@app_commands.describe(message="Message shown when medication is given")
@app_commands.default_permissions(administrator=True)
async def set_resp_medicate(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_medicate"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ Medicate response set.", ephemeral=True)


@bot.tree.command(name="set-resp-medicate-healthy", description="Set the error message when medicating but not sick")
@app_commands.describe(message="Ephemeral message shown when trying to medicate a healthy bot")
@app_commands.default_permissions(administrator=True)
async def set_resp_medicate_healthy(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_medicate_healthy"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ Medicate-healthy response set.", ephemeral=True)


@bot.tree.command(name="set-resp-clean", description="Set the response message for cleaning")
@app_commands.describe(message="Message shown when cleaning poop")
@app_commands.default_permissions(administrator=True)
async def set_resp_clean(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_clean"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ Clean response set.", ephemeral=True)


@bot.tree.command(name="set-resp-clean-none", description="Set the error message when cleaning but already clean")
@app_commands.describe(message="Ephemeral message shown when there's nothing to clean")
@app_commands.default_permissions(administrator=True)
async def set_resp_clean_none(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_clean_none"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ Clean-none response set.", ephemeral=True)


@bot.tree.command(name="set-resp-poop", description="Set the script-only poop message")
@app_commands.describe(message="Message shown when a poop timer pops")
@app_commands.default_permissions(administrator=True)
async def set_resp_poop(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_poop"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ Poop response set.", ephemeral=True)


@bot.tree.command(name="set-resp-cooldown", description="Set the cooldown error message (use {time} placeholder)")
@app_commands.describe(message="Message shown on cooldown. Use {time} for countdown.")
@app_commands.default_permissions(administrator=True)
async def set_resp_cooldown(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_cooldown"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ Cooldown response set.", ephemeral=True)


# â”€â”€ Debug / admin â”€â”€

@bot.tree.command(name="set-resp-rest", description="Set the response message for starting a rest")
@app_commands.describe(message="Message shown when the bot starts resting")
@app_commands.default_permissions(administrator=True)
async def set_resp_rest(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_rest"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ Rest response set.", ephemeral=True)


@bot.tree.command(name="set-resp-sleeping", description="Set the sleeping auto-reply message (use {time})")
@app_commands.describe(message="Message shown when users talk to the bot while it is sleeping")
@app_commands.default_permissions(administrator=True)
async def set_resp_sleeping(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_sleeping"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ Sleeping response set.", ephemeral=True)


@bot.tree.command(name="set-resp-no-energy", description="Set the error message when the bot has no energy left")
@app_commands.describe(message="Ephemeral message shown when play is blocked by zero energy")
@app_commands.default_permissions(administrator=True)
async def set_resp_no_energy(interaction: discord.Interaction, message: str):
    bot_config["tama_resp_no_energy"] = message
    save_config(bot_config)
    await interaction.response.send_message("✅ No-energy response set.", ephemeral=True)


@bot.tree.command(name="show-tama-stats", description="View all current Tamagotchi stats and config")
@app_commands.default_permissions(administrator=True)
async def show_tama_stats(interaction: discord.Interaction):
    from tamagotchi import _fs, apply_loneliness
    c = bot_config
    apply_loneliness(c, save=True)
    ensure_inventory_defaults(c)
    inventory_items = get_inventory_items(c, visible_only=False)
    inventory_lines = "\n".join(f"• {_format_tama_item_summary(item)}" for item in inventory_items) if inventory_items else "• No items configured"

    enabled = "✅ Enabled" if c.get("tama_enabled", False) else "❌ Disabled"
    sick = "**YES** 💀" if c.get("tama_sick", False) else "No"
    hatching = f"**YES** 🥚 ({int(max(0.0, float(c.get('tama_hatch_until', 0.0) or 0.0) - time.time()))}s left)" if is_hatching(c) else "No"

    msg = (
        f"🐣 **Tamagotchi Status** — {enabled}\n\n"
        f"**Stats:**\n"
        f"• 🍔 Hunger: {_fs(c.get('tama_hunger', 0))}/{c.get('tama_hunger_max', 100)}"
        f"  (-{c.get('tama_hunger_depletion', 1.0)} per {c.get('tama_needs_depletion_per_energy', 1.0):g} energy)\n"
        f"• 🥤 Thirst: {_fs(c.get('tama_thirst', 0))}/{c.get('tama_thirst_max', 100)}"
        f"  (-{c.get('tama_thirst_depletion', 1.0)} per {c.get('tama_needs_depletion_per_energy', 1.0):g} energy)\n"
        f"• 😊 Happiness: {_fs(c.get('tama_happiness', 0))}/{c.get('tama_happiness_max', 100)}"
        f"  (-{c.get('tama_happiness_depletion', 1.0)} every {c.get('tama_happiness_depletion_interval', 600)}s without interaction, "
        f"-{c.get('tama_low_energy_happiness_loss', 1.0)} below {c.get('tama_low_energy_happiness_threshold_pct', 10.0):g}% energy per LLM turn, "
        f"paused during heartbeat quiet hours when enabled)\n"
        f"• ❤️ Health: {_fs(c.get('tama_health', 0))}/{c.get('tama_health_max', 100)}"
        f"  (threshold: {c.get('tama_health_threshold', 20.0)}, dmg/stat: {c.get('tama_health_damage_per_stat', 10.0)})\n"
        f"• ⚡ Energy: {_fs(c.get('tama_energy', 0))}/{c.get('tama_energy_max', 100)}"
        f"  (API: -{c.get('tama_energy_depletion_api', 1.0)}, game: -{c.get('tama_energy_depletion_game', 5.0)}, "
        f"recharge: +{c.get('tama_energy_recharge_amount', 5.0)} every {c.get('tama_energy_recharge_interval', 300)}s idle)\n"
        f"• 💩 Dirt: {c.get('tama_dirt', 0)}/{c.get('tama_dirt_max', 4)}"
        f"  (queue timer every {c.get('tama_dirt_food_threshold', 5)} food, counter: {c.get('tama_dirt_food_counter', 0)}, "
        f"timer max: {c.get('tama_dirt_poop_timer_max_minutes', 5)}m, "
        f"sick after {c.get('tama_dirt_damage_interval', 600)}s, "
        f"+{c.get('tama_dirt_health_damage', 5.0)} dmg/poop while sick)\n"
        f"• 💀 Sick: {sick} (dmg: {c.get('tama_sick_health_damage', 5.0)}/turn)\n"
        f"• 🥚 Hatching: {hatching} (duration: {c.get('tama_egg_hatch_time', 30)}s)\n\n"
        f"**Feed / Drink Energy:**\n"
        f"• Feed: +{c.get('tama_feed_energy_gain', 1.0)} energy every {c.get('tama_feed_energy_every', 1)} feeds "
        f"(counter: {c.get('tama_feed_energy_counter', 0)})\n"
        f"• Drink: +{c.get('tama_drink_energy_gain', 1.0)} energy every {c.get('tama_drink_energy_every', 1)} drinks "
        f"(counter: {c.get('tama_drink_energy_counter', 0)})\n\n"
        f"**Play Effects:**\n"
        f"• Base play happiness +{_fs(float(c.get('tama_play_happiness', 0.0) or 0.0))} when a game session starts\n"
        f"• RPS rewards: user win +{_fs(float(c.get('tama_rps_reward_user_win', 5.0) or 0.0))} | "
        f"draw +{_fs(float(c.get('tama_rps_reward_draw', 10.0) or 0.0))} | "
        f"bot win +{_fs(float(c.get('tama_rps_reward_bot_win', 20.0) or 0.0))}\n"
        f"• RPS cooldown: {c.get('tama_cd_rps', 60)}s | Play menu cooldown: none\n"
        f"**Chatter:**\n"
        f"• Enabled: {'yes' if c.get('tama_chatter_enabled', True) else 'no'} | Cooldown: {c.get('tama_chatter_cooldown', 30)}s\n"
        f"• Prompt: {c.get('tama_chatter_prompt', '') or '(default)'}\n"
        f"**Lucky Gift:**\n"
        f"• Cooldown: {c.get('tama_cd_lucky_gift', 600)}s | Reveal timer: {c.get('tama_lucky_gift_duration', 30)}s | Other-item cooldown: {c.get('tama_cd_other', 60)}s\n"
        f"**Medicine:**\n"
        f"• Heal +{c.get('tama_medicate_health_heal', 20.0)} HP | Happiness -{c.get('tama_medicate_happiness_cost', 3.0)}\n\n"
        f"**Rest:**\n"
        f"• Auto-sleep duration: {c.get('tama_rest_duration', 300)}s | Legacy cooldown: {c.get('tama_cd_rest', 60)}s\n"
        f"• Wake prompt: {c.get('tama_wake_prompt', '') or '(default)'}\n\n"
        f"**Button Cooldowns:**\n"
        f"• Feed: {c.get('tama_cd_feed', 60)}s | Drink: {c.get('tama_cd_drink', 60)}s | "
        f"Play menu: none | RPS: {c.get('tama_cd_rps', 60)}s | Chatter: {c.get('tama_chatter_cooldown', 30)}s | Medicate: {c.get('tama_cd_medicate', 60)}s | "
        f"Clean: {c.get('tama_cd_clean', 60)}s | Other: {c.get('tama_cd_other', 60)}s | "
        f"Lucky Gift: {c.get('tama_cd_lucky_gift', 600)}s\n\n"
        f"**Inventory Items:**\n"
        f"{inventory_lines}"
    )
    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="dev-set-stats", description="Directly set the current Tamagotchi stats for testing")
@app_commands.describe(
    hunger="Current hunger value",
    thirst="Current thirst value",
    happiness="Current happiness value",
    health="Current health value",
    energy="Current energy value",
    dirt="Current dirt value",
    sick="Whether the bot is currently sick",
)
@app_commands.default_permissions(administrator=True)
async def dev_set_stats(
    interaction: discord.Interaction,
    hunger: float | None = None,
    thirst: float | None = None,
    happiness: float | None = None,
    health: float | None = None,
    energy: float | None = None,
    dirt: int | None = None,
    sick: bool | None = None,
):
    if hunger is not None:
        bot_config["tama_hunger"] = max(0.0, min(float(bot_config.get("tama_hunger_max", 100)), round(hunger, 2)))
    if thirst is not None:
        bot_config["tama_thirst"] = max(0.0, min(float(bot_config.get("tama_thirst_max", 100)), round(thirst, 2)))
    if happiness is not None:
        bot_config["tama_happiness"] = max(0.0, min(float(bot_config.get("tama_happiness_max", 100)), round(happiness, 2)))
    if health is not None:
        bot_config["tama_health"] = max(0.0, min(float(bot_config.get("tama_health_max", 100)), round(health, 2)))
    if energy is not None:
        bot_config["tama_energy"] = max(0.0, min(float(bot_config.get("tama_energy_max", 100)), round(energy, 2)))
    if dirt is not None:
        bot_config["tama_dirt"] = max(0, min(int(bot_config.get("tama_dirt_max", 4)), dirt))
    if sick is not None:
        bot_config["tama_sick"] = sick
    save_config(bot_config)
    if tama_manager and (dirt is not None or sick is not None):
        tama_manager._sync_dirt_grace()
    await interaction.response.send_message(
        "✅ Current Tamagotchi stats updated for testing.", ephemeral=True
    )


@bot.tree.command(name="reset-tama-stats", description="Reset the Tamagotchi state or start a fresh egg")
@app_commands.default_permissions(administrator=True)
async def reset_tama_stats(interaction: discord.Interaction):
    if bot_config.get("tama_enabled", False):
        await interaction.response.defer(ephemeral=True)
        fresh_start = await _run_tama_fresh_start(
            fallback_channel_ids=[interaction.channel_id],
        )
        if not fresh_start.get("hatch_message_posted"):
            raise RuntimeError(
                "Fresh start did not post a hatch message. "
                f"Target channel: {fresh_start.get('hatch_channel_id') or '(missing)'}. "
                f"Reason: {fresh_start.get('hatch_failure_reason') or 'unknown'}"
            )
        await interaction.followup.send(
            "✅ Tamagotchi reset complete. Soul wiped, `[ce]` sent to the main chat and thoughts channels, and a new egg is hatching.",
            ephemeral=True,
        )
        return

    reset_tamagotchi_state(bot_config)
    save_config(bot_config)
    if tama_manager:
        tama_manager.clear_poop_timers()
    await interaction.response.send_message("✅ All Tamagotchi stats reset to max.", ephemeral=True)



