"""Reminder commands."""

from ..common import *
# ---------------------------------------------------------------------------
# Slash commands â€” Reminders & auto-wake
# ---------------------------------------------------------------------------

@bot.tree.command(name="setup-reminders", description="Enable/disable reminders and set the output channel")
@app_commands.describe(
    enabled="True = reminders active, False = disabled",
    channel="The channel where fired reminders are posted",
)
@app_commands.default_permissions(administrator=True)
async def setup_reminders(interaction: discord.Interaction, enabled: bool, channel: discord.TextChannel):
    bot_config["reminders_enabled"] = enabled
    bot_config["reminders_channel_id"] = str(channel.id)
    save_config(bot_config)

    if reminder_manager:
        if enabled:
            reminder_manager.start()
        else:
            reminder_manager.stop()

    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Reminders **{state}** — output channel: {channel.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="add-reminder", description="Add a named reminder")
@app_commands.describe(
    name="Unique name for this reminder (used to delete it later)",
    datetime="Date and time in dd-mm-yy HH:MM format (24-hour clock)",
    prompt="The reminder text / prompt that will be sent to the bot when it fires",
)
@app_commands.default_permissions(administrator=True)
async def add_reminder_cmd(interaction: discord.Interaction, name: str, datetime: str, prompt: str):
    if not reminder_manager:
        await interaction.response.send_message("⚠️ Reminder system not initialised.", ephemeral=True)
        return
    err = reminder_manager.add_reminder(name, datetime, prompt)
    if err:
        await interaction.response.send_message(f"⚠️ {err}", ephemeral=True)
    else:
        await interaction.response.send_message(
            f"✅ Reminder **{name}** set for `{datetime}`.\n📝 Prompt: {prompt}",
            ephemeral=True,
        )


@bot.tree.command(name="delete-reminder", description="Delete a reminder by name")
@app_commands.describe(name="The name of the reminder to delete")
@app_commands.default_permissions(administrator=True)
async def delete_reminder_cmd(interaction: discord.Interaction, name: str):
    if not reminder_manager:
        await interaction.response.send_message("⚠️ Reminder system not initialised.", ephemeral=True)
        return
    err = reminder_manager.delete_reminder(name)
    if err:
        await interaction.response.send_message(f"⚠️ {err}", ephemeral=True)
    else:
        await interaction.response.send_message(f"✅ Reminder **{name}** deleted.", ephemeral=True)


@bot.tree.command(name="show-reminders", description="Show all currently scheduled reminders and wake-times")
@app_commands.default_permissions(administrator=True)
async def show_reminders_cmd(interaction: discord.Interaction):
    from reminders import get_all_reminders_text
    text = get_all_reminders_text()
    full = f"📋 **Scheduled Entries:**\n```\n{text}\n```"
    chunks = chunk_message(full)
    await interaction.response.send_message(chunks[0], ephemeral=True)
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)


@bot.tree.command(name="set-reminder-channel", description="Set the channel where fired reminders are posted")
@app_commands.describe(channel="The channel for reminder output")
@app_commands.default_permissions(administrator=True)
async def set_reminder_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    bot_config["reminders_channel_id"] = str(channel.id)
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Reminders will now fire in {channel.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="set-reminder-log-channel", description="Set the channel where reminder registrations are logged")
@app_commands.describe(channel="The log channel for transparency")
@app_commands.default_permissions(administrator=True)
async def set_reminder_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    bot_config["reminder_log_channel_id"] = str(channel.id)
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Reminder log channel set to {channel.mention}.",
        ephemeral=True,
    )



