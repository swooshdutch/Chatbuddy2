"""Custom model commands."""

from ..common import *
# ---------------------------------------------------------------------------
# Slash commands â€” Custom model settings
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-api-key-custom", description="Set the API key for the custom (non-Google) model")
@app_commands.describe(key="Your custom model API key")
@app_commands.default_permissions(administrator=True)
async def set_api_key_custom(interaction: discord.Interaction, key: str):
    set_secret("api_key_custom", key)
    await interaction.response.send_message("✅ Custom API key has been stored in `.env`.", ephemeral=True)


@bot.tree.command(name="set-api-endpoint-custom", description="Set the endpoint for the custom (non-Google) model")
@app_commands.describe(endpoint="Full URL or model name for your custom model")
@app_commands.default_permissions(administrator=True)
async def set_api_endpoint_custom(interaction: discord.Interaction, endpoint: str):
    bot_config["model_endpoint_custom"] = endpoint
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Custom model endpoint set to **{endpoint}**.", ephemeral=True
    )



