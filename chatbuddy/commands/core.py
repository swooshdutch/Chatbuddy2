"""Core setup, model, and audio commands."""

from ..common import *
# ---------------------------------------------------------------------------
# Slash commands â€” Core settings
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-api-context", description="Configure daily API usage context tracking")
@app_commands.describe(
    enabled="True = track requests and inject usage to AI, False = disabled",
    limit="Max amount of requests per day (e.g. 500)",
    reset_time="Reset time in 24h format (e.g. 00:00)",
)
@app_commands.default_permissions(administrator=True)
async def set_api_context(interaction: discord.Interaction, enabled: bool, limit: int, reset_time: str):
    import re
    if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", reset_time):
        await interaction.response.send_message("⚠️ Reset time must be in 24h HH:MM format (e.g. 00:00).", ephemeral=True)
        return
        
    bot_config["api_context_enabled"] = enabled
    bot_config["api_context_limit"] = limit
    bot_config["api_context_reset_time"] = reset_time
    save_config(bot_config)
    
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ API context tracking **{state}**.\n"
        f"• Daily limit: **{limit}**\n"
        f"• Reset time: **{reset_time}**",
        ephemeral=True,
    )


@bot.tree.command(name="check-api-quota", description="Check the current daily API usage (if tracking is enabled)")
async def check_api_quota(interaction: discord.Interaction):
    if not bot_config.get("api_context_enabled", False):
        await interaction.response.send_message(
            "⚠️ API Context tracking is currently **disabled**. An administrator must enable it via `/set-api-context`.", 
            ephemeral=True
        )
        return
        
    limit = bot_config.get("api_context_limit", 500)
    usage = bot_config.get("api_context_current_usage", 0)
    reset_time = bot_config.get("api_context_reset_time", "00:00")
    last_reset = bot_config.get("api_context_last_reset_date", "Never")
    
    await interaction.response.send_message(
        f"📊 **Daily API Quota Status**\n"
        f"• Current Usage: **{usage} / {limit}** requests\n"
        f"• Reset Time: **{reset_time}** (system time)\n"
        f"• Last Reset Date: **{last_reset}**",
        ephemeral=True
    )


@bot.tree.command(name="set-edit-api-current-quota", description="Manually edit the current API quota usage")
@app_commands.describe(amount="New current usage value")
@app_commands.default_permissions(administrator=True)
async def set_edit_api_current_quota(interaction: discord.Interaction, amount: int):
    if not bot_config.get("api_context_enabled", False):
        await interaction.response.send_message(
            "⚠️ API Context tracking is currently **disabled**. Enable it via `/set-api-context` first.",
            ephemeral=True,
        )
        return
    if amount < 0:
        await interaction.response.send_message(
            "⚠️ Amount cannot be negative.", ephemeral=True
        )
        return
    limit = bot_config.get("api_context_limit", 500)
    if amount > limit:
        await interaction.response.send_message(
            f"⚠️ Amount **{amount}** exceeds the max quota limit of **{limit}**.",
            ephemeral=True,
        )
        return
    bot_config["api_context_current_usage"] = amount
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ API current quota manually set to **{amount} / {limit}**.",
        ephemeral=True,
    )


@bot.tree.command(name="set-api-key", description="Set the Gemini API key")
@app_commands.describe(key="Your Gemini API key")
@app_commands.default_permissions(administrator=True)
async def set_api_key(interaction: discord.Interaction, key: str):
    set_secret("api_key", key)
    await interaction.response.send_message("✅ API key has been stored in `.env`.", ephemeral=True)


@bot.tree.command(name="set-multimodal", description="Enable or disable multimodal support (images and audio)")
@app_commands.describe(enabled="True = bot can view images and hear audio. False = disabled (default)")
@app_commands.default_permissions(administrator=True)
async def set_multimodal(interaction: discord.Interaction, enabled: bool):
    bot_config["multimodal_enabled"] = enabled
    save_config(bot_config)
    state = "**enabled** 🖼️/🎤" if enabled else "**disabled** 🚫"
    await interaction.response.send_message(f"✅ Multimodal capabilities {state}.", ephemeral=True)


@bot.tree.command(name="set-gemini-web-search", description="Enable or disable Gemini Google Search Grounding")
@app_commands.describe(enabled="True = bot can search the web (requires API quota). False = disabled (default)")
@app_commands.default_permissions(administrator=True)
async def set_gemini_web_search(interaction: discord.Interaction, enabled: bool):
    bot_config["web_search_enabled"] = enabled
    save_config(bot_config)
    state = "**enabled** 🌍" if enabled else "**disabled** 🚫"
    await interaction.response.send_message(f"✅ Web search capabilities {state}.", ephemeral=True)


@bot.tree.command(name="set-duck-search", description="Enable or disable DuckDuckGo Web Search")
@app_commands.describe(enabled="True = bot can search the web for free. False = disabled (default)")
@app_commands.default_permissions(administrator=True)
async def set_duck_search(interaction: discord.Interaction, enabled: bool):
    bot_config["duck_search_enabled"] = enabled
    save_config(bot_config)
    state = "**enabled** 🦆" if enabled else "**disabled** 🚫"
    await interaction.response.send_message(f"✅ DuckDuckGo Web Search {state}.", ephemeral=True)


@bot.tree.command(name="set-chat-history", description="Set how many messages of context the bot receives")
@app_commands.describe(limit="Number of previous messages (default: 40)")
@app_commands.default_permissions(administrator=True)
async def set_chat_history(interaction: discord.Interaction, limit: int):
    if limit < 1:
        await interaction.response.send_message("⚠️ Limit must be at least 1.", ephemeral=True)
        return
    bot_config["chat_history_limit"] = limit
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Chat history limit set to **{limit}** messages.", ephemeral=True
    )


@bot.tree.command(name="set-temp", description="Set the model temperature")
@app_commands.describe(temperature="Temperature value (e.g. 0.7)")
@app_commands.default_permissions(administrator=True)
async def set_temp(interaction: discord.Interaction, temperature: float):
    if temperature < 0.0 or temperature > 2.0:
        await interaction.response.send_message(
            "⚠️ Temperature must be between 0.0 and 2.0.", ephemeral=True
        )
        return
    bot_config["temperature"] = temperature
    save_config(bot_config)
    await interaction.response.send_message(f"✅ Temperature set to **{temperature}**.", ephemeral=True)


@bot.tree.command(name="set-api-endpoint-gemini", description="Set the Gemini text model endpoint")
@app_commands.describe(endpoint="Model name (e.g. gemini-2.0-flash)")
@app_commands.default_permissions(administrator=True)
async def set_api_endpoint_gemini(interaction: discord.Interaction, endpoint: str):
    bot_config["model_endpoint_gemini"] = endpoint
    save_config(bot_config)
    await interaction.response.send_message(f"✅ Gemini endpoint set to **{endpoint}**.", ephemeral=True)


@bot.tree.command(name="set-api-endpoint-gemma", description="Set the Gemma text model endpoint")
@app_commands.describe(endpoint="Model name (e.g. gemma-3-27b-it)")
@app_commands.default_permissions(administrator=True)
async def set_api_endpoint_gemma(interaction: discord.Interaction, endpoint: str):
    bot_config["model_endpoint_gemma"] = endpoint
    save_config(bot_config)
    await interaction.response.send_message(f"✅ Gemma endpoint set to **{endpoint}**.", ephemeral=True)


@bot.tree.command(name="set-sys-instruct", description="Set the system instruction / prompt")
@app_commands.describe(prompt="The system prompt text")
@app_commands.default_permissions(administrator=True)
async def set_sys_instruct(interaction: discord.Interaction, prompt: str):
    write_system_prompt_template(prompt)
    await interaction.response.send_message(
        f"✅ System prompt template updated in `{SYSTEM_PROMPT_TEMPLATE_FILE}`.",
        ephemeral=True,
    )


@bot.tree.command(name="set-botname", description="Set the bot name used by <!BOTNAME!> prompt variables")
@app_commands.describe(name="Name to inject wherever <!BOTNAME!> appears")
@app_commands.default_permissions(administrator=True)
async def set_botname(interaction: discord.Interaction, name: str):
    cleaned = name.strip()
    if not cleaned:
        await interaction.response.send_message(
            "⚠️ Bot name cannot be empty.",
            ephemeral=True,
        )
        return
    bot_config["bot_name"] = cleaned
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Bot name set to **{cleaned}**.",
        ephemeral=True,
    )


@bot.tree.command(
    name="set-bot-personality",
    description="Set the personality text used by <!BOTPERSONALITY!> prompt variables",
)
@app_commands.describe(personality="Personality text to inject wherever <!BOTPERSONALITY!> appears")
@app_commands.default_permissions(administrator=True)
async def set_bot_personality(interaction: discord.Interaction, personality: str):
    cleaned = personality.strip()
    if not cleaned:
        await interaction.response.send_message(
            "⚠️ Bot personality cannot be empty.",
            ephemeral=True,
        )
        return
    bot_config["bot_personality"] = cleaned
    save_config(bot_config)
    await interaction.response.send_message(
        "✅ Bot personality updated.",
        ephemeral=True,
    )


@bot.tree.command(name="show-sys-instruct", description="Display the full effective system prompt")
@app_commands.default_permissions(administrator=True)
async def show_sys_instruct(interaction: discord.Interaction):
    prompt = build_system_prompt(bot_config)
    if not prompt:
        prompt = "(not set)"

    full_text = (
        "📝 **Current effective system prompt (rendered from the template file):**\n"
        f"```\n{prompt}\n```"
    )
    chunks = chunk_message(full_text)
    await interaction.response.send_message(chunks[0], ephemeral=True)
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)


# ---------------------------------------------------------------------------
# Slash commands â€” Text model mode
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-model-mode", description="Switch between Gemini, Gemma, and Custom text model modes")
@app_commands.describe(mode="gemini = standard Gemini, gemma = Gemma-compatible injection, custom = external API")
@app_commands.choices(mode=[
    app_commands.Choice(name="gemini",  value="gemini"),
    app_commands.Choice(name="gemma",   value="gemma"),
    app_commands.Choice(name="custom",  value="custom"),
])
@app_commands.default_permissions(administrator=True)
async def set_model_mode(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    bot_config["model_mode"] = mode.value
    save_config(bot_config)
    if mode.value == "gemma":
        ep = bot_config.get("model_endpoint_gemma", "(not set)")
        info = (
            f"\n⚠️ Gemma mode: system prompt injected into user content.\n"
            f"• Endpoint: `{ep}`"
        )
    elif mode.value == "custom":
        ep = bot_config.get("model_endpoint_custom", "(not set)")
        key_status = "set" if has_secret("api_key_custom") else "not set"
        info = (
            f"\n⚠️ Custom mode: system prompt injected into user content.\n"
            f"• Endpoint: `{ep}`\n"
            f"• Custom API key: **{key_status}**"
        )
    else:
        ep = bot_config.get("model_endpoint_gemini", "gemini-2.0-flash")
        info = f"\n• Endpoint: `{ep}`"
    await interaction.response.send_message(
        f"✅ Text model mode set to **{mode.value}**.{info}", ephemeral=True
    )


# ---------------------------------------------------------------------------
# Slash commands â€” Audio clip mode
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-audio-mode", description="Enable or disable audio clip mode server-wide")
@app_commands.describe(enabled="True = bot sends .wav voice clips with every response, False = text only")
@app_commands.default_permissions(administrator=True)
async def set_audio_mode(interaction: discord.Interaction, enabled: bool):
    if enabled and not bot_config.get("audio_endpoint", "").strip():
        await interaction.response.send_message(
            "⚠️ No audio endpoint configured yet. "
            "Run `/set-audio-endpoint` first, then enable audio mode.",
            ephemeral=True,
        )
        return

    bot_config["audio_enabled"] = enabled
    save_config(bot_config)
    state = "**enabled** 🔊" if enabled else "**disabled** 🔇"
    voice = bot_config.get("audio_settings", {}).get("voice", "Aoede")
    endpoint = bot_config.get("audio_endpoint", "(not set)")
    await interaction.response.send_message(
        f"✅ Audio clip mode {state}.\n"
        f"• TTS model: `{endpoint}`\n"
        f"• Voice: **{voice}**",
        ephemeral=True,
    )


@bot.tree.command(name="set-audio-endpoint", description="Set the Gemini TTS model endpoint")
@app_commands.describe(endpoint="TTS model name (e.g. gemini-2.5-flash-preview-tts)")
@app_commands.default_permissions(administrator=True)
async def set_audio_endpoint(interaction: discord.Interaction, endpoint: str):
    bot_config["audio_endpoint"] = endpoint
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Audio (TTS) endpoint set to **{endpoint}**.", ephemeral=True
    )


@bot.tree.command(name="set-audio-settings", description="Set the voice used for audio clip mode")
@app_commands.describe(voice="Voice name (e.g. Aoede, Puck, Charon, Kore, Fenrir, Leda, Orus, Zephyr)")
@app_commands.default_permissions(administrator=True)
async def set_audio_settings(interaction: discord.Interaction, voice: str):
    audio_settings = bot_config.get("audio_settings", {})
    audio_settings["voice"] = voice
    bot_config["audio_settings"] = audio_settings
    save_config(bot_config)
    await interaction.response.send_message(f"✅ Audio voice set to **{voice}**.", ephemeral=True)



