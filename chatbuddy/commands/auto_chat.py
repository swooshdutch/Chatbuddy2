"""Auto-chat commands."""

from ..common import *
# ---------------------------------------------------------------------------
# Slash commands â€” Auto-chat mode
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-auto-chat-mode", description="Configure auto-chat mode for a channel")
@app_commands.describe(
    channel="The channel for auto-chat (one at a time)",
    enabled="True = auto-chat active, False = disabled",
    interval="Seconds between checks (default: 30)",
    idle_minutes="Minutes of inactivity before idle mode (default: 10)",
)
@app_commands.default_permissions(administrator=True)
async def set_auto_chat_mode(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    enabled: bool,
    interval: int = 30,
    idle_minutes: int = 10,
):
    if interval < 5:
        await interaction.response.send_message("⚠️ Interval must be at least 5 seconds.", ephemeral=True)
        return
    if idle_minutes < 1:
        await interaction.response.send_message("⚠️ Idle timeout must be at least 1 minute.", ephemeral=True)
        return

    bot_config["auto_chat_channel_id"] = str(channel.id)
    bot_config["auto_chat_enabled"] = enabled
    bot_config["auto_chat_interval"] = interval
    bot_config["auto_chat_idle_minutes"] = idle_minutes
    save_config(bot_config)

    if auto_chat_manager:
        auto_chat_manager.start()

    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Auto-chat **{state}** for {channel.mention}.\n"
        f"• Check interval: **{interval}s**\n"
        f"• Idle timeout: **{idle_minutes}m**",
        ephemeral=True,
    )


@bot.tree.command(name="set-auto-idle-message", description="Enable/disable and optionally set the auto-chat idle message")
@app_commands.describe(
    enabled="True = post the idle message, False = disable it",
    message="Optional idle message text",
)
@app_commands.default_permissions(administrator=True)
async def set_auto_idle_message(
    interaction: discord.Interaction,
    enabled: bool,
    message: str | None = None,
):
    if message is not None:
        message = message.replace("\\n", "\n")
        bot_config["auto_chat_idle_message"] = message

    bot_config["auto_chat_idle_message_enabled"] = enabled
    save_config(bot_config)

    current_message = bot_config.get(
        "auto_chat_idle_message",
        "Going afk, ping me if you need me",
    )
    state = "enabled" if enabled else "disabled"
    reply = f"✅ Auto-chat idle message {state}."
    if enabled:
        reply += f"\nCurrent message:\n```{current_message}```"

    await interaction.response.send_message(reply, ephemeral=True)



