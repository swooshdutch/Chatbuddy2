"""Soul management commands."""

from ..common import *
# ---------------------------------------------------------------------------
# Slash commands â€” Soul feature
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-soul", description="Enable or disable the dynamic soul prompt and set its limit")
@app_commands.describe(
    enabled="True = active, False = disabled",
    limit="Max physical character limit of the soul text (default 2000)",
)
@app_commands.default_permissions(administrator=True)
async def set_soul(interaction: discord.Interaction, enabled: bool, limit: int = 2000):
    if limit < 100:
        await interaction.response.send_message("⚠️ Limit must be at least 100.", ephemeral=True)
        return
    bot_config["soul_enabled"] = enabled
    bot_config["soul_limit"] = limit
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Soul feature **{state}** with a limit of **{limit}** characters.\n"
        f"Bot uses `<!soul-update: text>` and `<!soul-override: text>` to update it.",
        ephemeral=True,
    )


@bot.tree.command(name="show-soul", description="View the current contents of the soul")
async def show_soul(interaction: discord.Interaction):
    if not os.path.exists("soul.md"):
        await interaction.response.send_message("📝 Soul is currently **empty** (file does not exist).", ephemeral=True)
        return
    
    with open("soul.md", "r", encoding="utf-8") as f:
        soul_text = f.read().strip()
        
    if not soul_text or soul_text == "{}":
        await interaction.response.send_message("📝 Soul is currently **empty**.", ephemeral=True)
        return

    full_text = f"📝 **Current Soul:**\n```\n{soul_text}\n```"
    chunks = chunk_message(full_text)
    await interaction.response.send_message(chunks[0], ephemeral=True)
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)


async def _read_soul() -> dict:
    if not os.path.exists("soul.md"):
        return {}
    try:
        with open("soul.md", "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                return json.loads(content)
    except:
        pass
    return {}

async def _write_soul(interaction: discord.Interaction, soul_data: dict) -> bool:
    new_json = json.dumps(soul_data, indent=2, ensure_ascii=False)
    soul_limit = bot_config.get("soul_limit", 2000)
    if len(new_json) > soul_limit:
        await interaction.response.send_message(
            f"⚠️ Manual edit rejected: too large ({len(new_json)} > {soul_limit} limit).", 
            ephemeral=True
        )
        return False
    with open("soul.md", "w", encoding="utf-8") as f:
        f.write(new_json)
    return True

@bot.tree.command(name="wipe-soul", description="Wipe the entire soul file empty")
@app_commands.default_permissions(administrator=True)
async def wipe_soul(interaction: discord.Interaction):
    with open("soul.md", "w", encoding="utf-8") as f:
        f.write("{}")
    await interaction.response.send_message("✅ Soul successfully wiped.", ephemeral=True)

@bot.tree.command(name="edit-soul-delete-entry", description="Delete an entry from the soul")
@app_commands.describe(entry_name="The ID of the entry to delete")
@app_commands.default_permissions(administrator=True)
async def edit_soul_delete_entry(interaction: discord.Interaction, entry_name: str):
    soul_data = await _read_soul()
    if entry_name in soul_data:
        soul_data.pop(entry_name, None)
        if await _write_soul(interaction, soul_data):
            await interaction.response.send_message(f"✅ Deleted entry **{entry_name}**.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Entry **{entry_name}** not found.", ephemeral=True)

@bot.tree.command(name="edit-soul-add-entry", description="Add text to an entry (appends if exists)")
@app_commands.describe(
    entry_name="The ID of the entry",
    entry_text="Text to append or create"
)
@app_commands.default_permissions(administrator=True)
async def edit_soul_add_entry(interaction: discord.Interaction, entry_name: str, entry_text: str):
    soul_data = await _read_soul()
    entry_text = entry_text.replace("\\n", "\n")
    if entry_name in soul_data:
        soul_data[entry_name] += "\n" + entry_text
    else:
        soul_data[entry_name] = entry_text
    if await _write_soul(interaction, soul_data):
        await interaction.response.send_message(f"✅ Appended/added text to **{entry_name}**.", ephemeral=True)

@bot.tree.command(name="edit-soul-overwrite", description="Replace the text of an entry")
@app_commands.describe(
    entry_name="The ID of the entry",
    entry_text="Text to replace with"
)
@app_commands.default_permissions(administrator=True)
async def edit_soul_overwrite(interaction: discord.Interaction, entry_name: str, entry_text: str):
    soul_data = await _read_soul()
    entry_text = entry_text.replace("\\n", "\n")
    soul_data[entry_name] = entry_text
    if await _write_soul(interaction, soul_data):
        await interaction.response.send_message(f"✅ Overwrote entry **{entry_name}**.", ephemeral=True)


@bot.tree.command(name="set-soul-channel", description="Set the channel to log soul updates + enable/disable")
@app_commands.describe(
    channel="The channel to log updates to",
    enabled="True = active, False = disabled",
)
@app_commands.default_permissions(administrator=True)
async def set_soul_channel(interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool):
    bot_config["soul_channel_id"] = str(channel.id)
    bot_config["soul_channel_enabled"] = enabled
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"✅ Soul logging **{state}** in {channel.mention}.", ephemeral=True)



