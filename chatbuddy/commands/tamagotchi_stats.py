"""Tamagotchi stat configuration commands."""

from ..common import *


@bot.tree.command(name="set-tama-hunger", description="Configure the hunger stat")
@app_commands.describe(max="Maximum hunger value", depletion="Hunger lost per configured energy step")
@app_commands.default_permissions(administrator=True)
async def set_tama_hunger(interaction: discord.Interaction, max: int, depletion: float):
    if max < 1:
        await interaction.response.send_message("⚠️ Max must be at least 1.", ephemeral=True)
        return
    bot_config["tama_hunger_max"] = max
    bot_config["tama_hunger_depletion"] = depletion
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Hunger: max **{max}**, depletion **{depletion}** per configured energy step.", ephemeral=True
    )


@bot.tree.command(name="set-tama-thirst", description="Configure the thirst stat")
@app_commands.describe(max="Maximum thirst value", depletion="Thirst lost per configured energy step")
@app_commands.default_permissions(administrator=True)
async def set_tama_thirst(interaction: discord.Interaction, max: int, depletion: float):
    if max < 1:
        await interaction.response.send_message("⚠️ Max must be at least 1.", ephemeral=True)
        return
    bot_config["tama_thirst_max"] = max
    bot_config["tama_thirst_depletion"] = depletion
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Thirst: max **{max}**, depletion **{depletion}** per configured energy step.", ephemeral=True
    )


@bot.tree.command(name="set-tama-happiness", description="Configure the happiness stat")
@app_commands.describe(
    max="Maximum happiness value",
    depletion="Happiness lost each loneliness interval",
    interval_minutes="Minutes without interaction before the loneliness loss applies",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_happiness(
    interaction: discord.Interaction,
    max: int,
    depletion: float,
    interval_minutes: float,
):
    if max < 1:
        await interaction.response.send_message("⚠️ Max must be at least 1.", ephemeral=True)
        return
    if depletion < 0 or interval_minutes <= 0:
        await interaction.response.send_message("⚠️ Depletion must be ≥ 0 and interval must be greater than 0.", ephemeral=True)
        return
    bot_config["tama_happiness_max"] = max
    bot_config["tama_happiness_depletion"] = depletion
    bot_config["tama_happiness_depletion_interval"] = int(round(interval_minutes * 60))
    save_config(bot_config)
    if tama_manager:
        tama_manager.record_interaction(save=False)
    await interaction.response.send_message(
        f"✅ Happiness: max **{max}**, loneliness loss **{depletion}** every **{interval_minutes:g}** minute(s) without interaction.",
        ephemeral=True
    )


@bot.tree.command(name="set-tama-health", description="Configure the health stat")
@app_commands.describe(
    max="Maximum health value",
    damage_per_stat="HP lost per stat below threshold each turn",
    threshold="Stats below this value trigger HP damage",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_health(interaction: discord.Interaction, max: int, damage_per_stat: float, threshold: float):
    if max < 1:
        await interaction.response.send_message("⚠️ Max must be at least 1.", ephemeral=True)
        return
    bot_config["tama_health_max"] = max
    bot_config["tama_health_damage_per_stat"] = damage_per_stat
    bot_config["tama_health_threshold"] = threshold
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Health: max **{max}**, **{damage_per_stat}** HP/stat below **{threshold}**.", ephemeral=True
    )


@bot.tree.command(name="set-tama-energy", description="Configure the energy stat")
@app_commands.describe(
    max="Maximum energy value",
    api_depletion="Energy lost per LLM API call",
    game_depletion="Energy lost per game played",
    needs_every="For every this much energy spent, hunger/thirst lose their configured amounts",
    recharge_minutes="Minutes of no interaction before energy recharge ticks",
    recharge_amount="Energy restored each recharge tick",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_energy(
    interaction: discord.Interaction,
    max: int,
    api_depletion: float,
    game_depletion: float,
    needs_every: float,
    recharge_minutes: float,
    recharge_amount: float,
):
    if max < 1:
        await interaction.response.send_message("⚠️ Max must be at least 1.", ephemeral=True)
        return
    if recharge_minutes <= 0:
        await interaction.response.send_message("⚠️ Recharge minutes must be greater than 0.", ephemeral=True)
        return
    if recharge_amount < 0:
        await interaction.response.send_message("⚠️ Recharge amount must be ≥ 0.", ephemeral=True)
        return
    if needs_every <= 0:
        await interaction.response.send_message("⚠️ Needs trigger must be greater than 0.", ephemeral=True)
        return
    recharge_interval_seconds = int(round(recharge_minutes * 60))
    if recharge_interval_seconds < 1:
        recharge_interval_seconds = 1
    bot_config["tama_energy_max"] = max
    bot_config["tama_energy_depletion_api"] = api_depletion
    bot_config["tama_energy_depletion_game"] = game_depletion
    bot_config["tama_needs_depletion_per_energy"] = needs_every
    bot_config["tama_energy_recharge_interval"] = recharge_interval_seconds
    bot_config["tama_energy_recharge_amount"] = recharge_amount
    save_config(bot_config)
    if tama_manager:
        tama_manager.record_interaction(save=False)
    await interaction.response.send_message(
        f"✅ Energy: max **{max}**, API **-{api_depletion}**, game **-{game_depletion}**, needs trigger **{needs_every:g}** energy, "
        f"recharge **+{recharge_amount}** every **{recharge_minutes:g}m** of inactivity.",
        ephemeral=True,
    )


@bot.tree.command(name="set-tama-low-energy-mood", description="Configure happiness loss when energy gets critically low")
@app_commands.describe(
    threshold_percent="Below this energy percent, LLM turns reduce happiness",
    happiness_loss="Happiness lost per LLM turn while below the threshold",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_low_energy_mood(
    interaction: discord.Interaction,
    threshold_percent: float,
    happiness_loss: float,
):
    if threshold_percent < 0 or threshold_percent > 100:
        await interaction.response.send_message("⚠️ Threshold percent must be between 0 and 100.", ephemeral=True)
        return
    if happiness_loss < 0:
        await interaction.response.send_message("⚠️ Happiness loss must be ≥ 0.", ephemeral=True)
        return
    bot_config["tama_low_energy_happiness_threshold_pct"] = round(threshold_percent, 2)
    bot_config["tama_low_energy_happiness_loss"] = round(happiness_loss, 2)
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Low-energy mood: lose **{happiness_loss:g}** happiness per LLM turn below **{threshold_percent:g}%** energy.",
        ephemeral=True,
    )


@bot.tree.command(name="set-tama-rest", description="Configure automatic sleep duration")
@app_commands.describe(
    duration="How long the bot sleeps in seconds",
    cooldown="Legacy rest cooldown value kept for compatibility",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_rest(interaction: discord.Interaction, duration: int, cooldown: int):
    if duration < 1:
        await interaction.response.send_message("⚠️ Duration must be at least 1 second.", ephemeral=True)
        return
    if cooldown < 0:
        await interaction.response.send_message("⚠️ Cooldown must be ≥ 0.", ephemeral=True)
        return
    bot_config["tama_rest_duration"] = duration
    bot_config["tama_cd_rest"] = cooldown
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Rest: sleep **{duration}s**, cooldown **{cooldown}s**.", ephemeral=True
    )


@bot.tree.command(name="set-tama-hatch-time", description="Configure how long the egg takes to hatch")
@app_commands.describe(seconds="Egg hatch countdown in seconds")
@app_commands.default_permissions(administrator=True)
async def set_tama_hatch_time(interaction: discord.Interaction, seconds: int):
    if seconds < 1:
        await interaction.response.send_message("⚠️ Hatch time must be at least 1 second.", ephemeral=True)
        return
    bot_config["tama_egg_hatch_time"] = seconds
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Egg hatch time set to **{seconds}s**.", ephemeral=True
    )


@bot.tree.command(name="set-tama-hatch-prompt", description="Configure the hidden prompt used when the egg hatches")
@app_commands.describe(prompt="The automated input the bot receives when it hatches")
@app_commands.default_permissions(administrator=True)
async def set_tama_hatch_prompt(interaction: discord.Interaction, prompt: str):
    bot_config["tama_hatch_prompt"] = prompt.strip()
    save_config(bot_config)
    await interaction.response.send_message("✅ Egg hatch prompt updated.", ephemeral=True)


@bot.tree.command(name="set-tama-wake-prompt", description="Configure the hidden prompt used when the bot wakes from sleep")
@app_commands.describe(prompt="The automated input the bot receives when it wakes up")
@app_commands.default_permissions(administrator=True)
async def set_tama_wake_prompt(interaction: discord.Interaction, prompt: str):
    bot_config["tama_wake_prompt"] = prompt.strip()
    save_config(bot_config)
    await interaction.response.send_message("✅ Wake prompt updated.", ephemeral=True)


@bot.tree.command(name="set-tama-chatter", description="Configure the chatter button")
@app_commands.describe(
    enabled="Whether the chatter button is visible and usable",
    cooldown="Cooldown in seconds between chatter button uses",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_chatter(interaction: discord.Interaction, enabled: bool, cooldown: int = 30):
    if cooldown < 0:
        await interaction.response.send_message("⚠️ Cooldown must be ≥ 0.", ephemeral=True)
        return
    bot_config["tama_chatter_enabled"] = enabled
    bot_config["tama_chatter_cooldown"] = cooldown
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Chatter button {state} with **{cooldown}s** cooldown.",
        ephemeral=True,
    )


@bot.tree.command(name="set-tama-chatter-prompt", description="Configure the hidden prompt used by the chatter button")
@app_commands.describe(prompt="The automated input the bot receives when the chatter button is used")
@app_commands.default_permissions(administrator=True)
async def set_tama_chatter_prompt(interaction: discord.Interaction, prompt: str):
    bot_config["tama_chatter_prompt"] = prompt.strip()
    save_config(bot_config)
    await interaction.response.send_message("✅ Chatter prompt updated.", ephemeral=True)


@bot.tree.command(name="set-tama-dirt", description="Configure the dirtiness/poop system")
@app_commands.describe(
    max="Max poop count before cap",
    food_threshold="Food consumed before a poop timer is queued",
    poop_timer_max_minutes="Max random poop timer length in minutes",
    health_damage="Extra sickness damage per poop on each turn",
    interval="Seconds before uncleared poop makes the bot sick",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_dirt(
    interaction: discord.Interaction,
    max: int, food_threshold: int, poop_timer_max_minutes: int, health_damage: float, interval: int,
):
    if max < 1:
        await interaction.response.send_message("⚠️ Max must be at least 1.", ephemeral=True)
        return
    if food_threshold < 1:
        await interaction.response.send_message("⚠️ Food threshold must be at least 1.", ephemeral=True)
        return
    if poop_timer_max_minutes < 1:
        await interaction.response.send_message("⚠️ Poop timer max must be at least 1 minute.", ephemeral=True)
        return
    if interval < 10:
        await interaction.response.send_message("⚠️ Interval must be at least 10 seconds.", ephemeral=True)
        return
    bot_config["tama_dirt_max"] = max
    bot_config["tama_dirt_food_threshold"] = food_threshold
    bot_config["tama_dirt_poop_timer_max_minutes"] = poop_timer_max_minutes
    bot_config["tama_dirt_health_damage"] = health_damage
    bot_config["tama_dirt_damage_interval"] = interval
    bot_config["tama_dirt_grace_until"] = 0.0
    save_config(bot_config)
    # Re-sync the dirt grace timer with the new settings.
    if tama_manager:
        tama_manager._sync_dirt_grace()
    await interaction.response.send_message(
        f"✅ Dirtiness: max **{max}** 💩, queue a poop timer every **{food_threshold}** food, "
        f"random timer **1-{poop_timer_max_minutes} min**, sickness after **{interval}s** dirty, "
        f"and **{health_damage}** extra sickness damage per poop.",
        ephemeral=True,
    )


@bot.tree.command(name="set-tama-sickness", description="Configure sickness damage")
@app_commands.describe(
    health_damage="HP lost per LLM turn while sick",
)
@app_commands.default_permissions(administrator=True)
async def set_tama_sickness(interaction: discord.Interaction, health_damage: float):
    bot_config["tama_sick_health_damage"] = health_damage
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Sickness: **{health_damage}** HP/turn while sick.",
        ephemeral=True
    )

