"""Chat revival commands."""

from ..common import *
# ---------------------------------------------------------------------------
# Slash commands â€” Chat revival
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-chat-revival", description="Configure periodic chat revival in a channel")
@app_commands.describe(
    channel="The channel for chat revival",
    minutes="Minutes between revival messages",
    system_instruct="Special system instruction for revival messages",
    enabled="True = revival is active, False = revival does nothing",
)
@app_commands.default_permissions(administrator=True)
async def set_chat_revival(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    minutes: int,
    system_instruct: str,
    enabled: bool,
):
    if minutes < 1:
        await interaction.response.send_message("⚠️ Interval must be at least 1 minute.", ephemeral=True)
        return

    system_instruct = system_instruct.replace("\\n", "\n")

    bot_config["chat_revival"] = {
        "channel_id": str(channel.id),
        "interval_minutes": minutes,
        "system_instruct": system_instruct,
        "enabled": enabled,
    }
    save_config(bot_config)

    if revival_manager:
        revival_manager.start()

    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Chat revival set for {channel.mention} every **{minutes}** minute(s) — **{state}**.\n"
        f"📝 Revival instruction: ```{system_instruct}```",
        ephemeral=True,
    )


@bot.tree.command(name="set-cr-leave-msg", description="Set the message the bot sends when chat revival time expires")
@app_commands.describe(message="The goodbye message to send after the revival window")
@app_commands.default_permissions(administrator=True)
async def set_cr_leave_msg(interaction: discord.Interaction, message: str):
    message = message.replace("\\n", "\n")
    bot_config["cr_leave_message"] = message
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Chat revival leave message updated to:\n```{message}```", ephemeral=True
    )


@bot.tree.command(name="set-cr-params", description="Set chat revival active duration and check interval")
@app_commands.describe(
    minutes="How many minutes the bot can freely talk during revival",
    seconds="How often (in seconds) it checks for new messages during revival",
)
@app_commands.default_permissions(administrator=True)
async def set_cr_params(interaction: discord.Interaction, minutes: int, seconds: int):
    if minutes < 1:
        await interaction.response.send_message("⚠️ Active duration must be at least 1 minute.", ephemeral=True)
        return
    if seconds < 5:
        await interaction.response.send_message("⚠️ Check interval must be at least 5 seconds.", ephemeral=True)
        return

    bot_config["cr_active_minutes"] = minutes
    bot_config["cr_check_seconds"] = seconds
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Chat revival params updated:\n"
        f"• Active duration: **{minutes}** minute(s)\n"
        f"• Check interval: **{seconds}** second(s)",
        ephemeral=True,
    )



