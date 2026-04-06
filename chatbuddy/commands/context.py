"""Channel, context, and dynamic prompt commands."""

from ..common import *


# ---------------------------------------------------------------------------
# Slash commands - Channel / context settings
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-allowed-channel", description="Whitelist or blacklist a channel for the bot")
@app_commands.describe(
    channel="The channel to configure",
    enabled="True = bot responds in this channel, False = bot ignores this channel",
)
@app_commands.default_permissions(administrator=True)
async def set_allowed_channel(interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool):
    allowed = bot_config.get("allowed_channels", {})
    allowed[str(channel.id)] = enabled
    bot_config["allowed_channels"] = allowed
    save_config(bot_config)
    state = "whitelisted" if enabled else "blacklisted"
    await interaction.response.send_message(f"✅ {channel.mention} has been **{state}**.", ephemeral=True)


@bot.tree.command(name="set-ce", description="Enable/disable [ce] context cutoff for a channel")
@app_commands.describe(
    channel="The channel to configure",
    enabled="True = [ce] cuts off context (default), False = [ce] is ignored",
)
@app_commands.default_permissions(administrator=True)
async def set_ce(interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool):
    ce_channels = bot_config.get("ce_channels", {})
    ce_channels[str(channel.id)] = enabled
    bot_config["ce_channels"] = ce_channels
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ `[ce]` context cutoff **{state}** for {channel.mention}.", ephemeral=True
    )


# ---------------------------------------------------------------------------
# Slash commands - Stream of Consciousness (SoC)
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-soc", description="Configure the Stream of Consciousness thoughts channel")
@app_commands.describe(
    channel="The channel where the bot's thoughts will be posted",
    enabled="True = extract thoughts to channel, False = disabled",
)
@app_commands.default_permissions(administrator=True)
async def set_soc(interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool):
    bot_config["soc_channel_id"] = str(channel.id)
    if enabled:
        bot_config["soc_enabled"] = True
        save_config(bot_config)
        await interaction.response.send_message(
            f"✅ SoC thoughts channel set to {channel.mention} - **enabled**.\n"
            f"Text between `<my-thoughts>` and `</my-thoughts>` will be extracted and posted there.",
            ephemeral=True,
        )
    else:
        bot_config["soc_enabled"] = False
        save_config(bot_config)
        await interaction.response.send_message(
            f"✅ SoC thoughts channel set to {channel.mention} - **disabled**.",
            ephemeral=True,
        )


@bot.tree.command(name="set-soc-context", description="Enable cross-channel thought context from the SoC channel")
@app_commands.describe(
    enabled="True = read past thoughts as context, False = disabled",
    count="Number of recent thought messages to read (default: 10)",
)
@app_commands.default_permissions(administrator=True)
async def set_soc_context(interaction: discord.Interaction, enabled: bool, count: int = 10):
    if enabled and not bot_config.get("soc_channel_id"):
        await interaction.response.send_message(
            "⚠️ No SoC channel configured yet. Run `/set-soc` first to set a thoughts channel.",
            ephemeral=True,
        )
        return
    if count < 1:
        await interaction.response.send_message("⚠️ Count must be at least 1.", ephemeral=True)
        return
    bot_config["soc_context_enabled"] = enabled
    bot_config["soc_context_count"] = count
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ SoC context **{state}** - reading last **{count}** thought messages.",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Slash commands - Dynamic system prompt
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-dynamic-system-prompt", description="Set an extra dynamic system prompt (appended after main)")
@app_commands.describe(
    prompt="The dynamic prompt text",
    enabled="True = active, False = disabled",
)
@app_commands.default_permissions(administrator=True)
async def set_dynamic_system_prompt(interaction: discord.Interaction, prompt: str, enabled: bool):
    prompt = prompt.replace("\\n", "\n")
    bot_config["dynamic_prompt"] = prompt
    bot_config["dynamic_prompt_enabled"] = enabled
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Dynamic system prompt **{state}** and saved.", ephemeral=True
    )
