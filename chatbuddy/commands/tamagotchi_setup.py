"""Tamagotchi setup and access commands."""

from ..common import *
from ..events import _run_backend_setup, _run_tama_fresh_start
# ---------------------------------------------------------------------------
# Slash commands â€” Tamagotchi (unified gamified system)
# ---------------------------------------------------------------------------


@bot.tree.command(name="setup-bot", description="Populate the bot config from backend environment variables")
async def setup_bot(interaction: discord.Interaction):
    if not _is_owner_user(interaction.user.id):
        await _deny_command(interaction)
        return
    await _run_backend_setup(
        interaction,
        model_mode="gemini",
        endpoint_env_name="GEMINI_ENDPOINT",
        endpoint_value=SETUP_GEMINI_ENDPOINT,
    )


@bot.tree.command(name="setup-bot-gemma", description="Populate the bot config from backend environment variables in Gemma mode")
async def setup_bot_gemma(interaction: discord.Interaction):
    if not _is_owner_user(interaction.user.id):
        await _deny_command(interaction)
        return
    await _run_backend_setup(
        interaction,
        model_mode="gemma",
        endpoint_env_name="GEMMA_ENDPOINT",
        endpoint_value=SETUP_GEMMA_ENDPOINT,
    )


@bot.tree.command(name="set-command-user", description="Add or remove a user ID that can use bot commands")
@app_commands.describe(user_id="The Discord user ID to change access for", allowed="True to allow, False to remove")
async def set_command_user(interaction: discord.Interaction, user_id: str, allowed: bool):
    if not _is_owner_user(interaction.user.id):
        await _deny_command(interaction)
        return

    normalized = user_id.strip()
    if not normalized.isdigit():
        await interaction.response.send_message("User ID must be numeric.", ephemeral=True)
        return
    if normalized == _configured_owner_id():
        await interaction.response.send_message("The owner ID is always allowed and cannot be removed.", ephemeral=True)
        return

    allowed_ids = [str(x).strip() for x in bot_config.get("command_allowed_user_ids", []) if str(x).strip()]
    if allowed and normalized not in allowed_ids:
        allowed_ids.append(normalized)
    if not allowed:
        allowed_ids = [x for x in allowed_ids if x != normalized]

    bot_config["command_allowed_user_ids"] = allowed_ids
    save_config(bot_config)
    state = "allowed" if allowed else "removed"
    await interaction.response.send_message(f"Command access {state} for `{normalized}`.", ephemeral=True)


@bot.tree.command(name="set-tama-mode", description="Enable or disable Tamagotchi mode")
@app_commands.describe(enabled="True to enable, False to disable")
@app_commands.default_permissions(administrator=True)
async def set_tama_mode(interaction: discord.Interaction, enabled: bool):
    bot_config["tama_enabled"] = enabled
    save_config(bot_config)
    if tama_manager:
        if enabled:
            tama_manager.start()
        else:
            tama_manager.stop()
    state = "**enabled** 🐣" if enabled else "**disabled** 🚫"
    await interaction.response.send_message(f"✅ Tamagotchi mode {state}.", ephemeral=True)


@bot.tree.command(name="set-tamagotchi-mode", description="Enable or disable Tamagotchi mode")
@app_commands.describe(enabled="True to enable, False to disable")
@app_commands.default_permissions(administrator=True)
async def set_tamagotchi_mode(interaction: discord.Interaction, enabled: bool):
    bot_config["tama_enabled"] = enabled
    save_config(bot_config)
    if tama_manager:
        if enabled:
            tama_manager.start()
        else:
            tama_manager.stop()
    state = "**enabled** 🐣" if enabled else "**disabled** 🚫"
    await interaction.response.send_message(f"✅ Tamagotchi mode {state}.", ephemeral=True)

