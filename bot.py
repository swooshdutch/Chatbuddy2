"""
bot.py — Main entry point for ChatBuddy, a Discord bot powered by Gemini.
"""

import os
import io
import re
import json
import asyncio
import threading
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from config import load_config, save_config
from gemini_api import generate, build_system_prompt
from utils import strip_mention, chunk_message, format_context, resolve_custom_emoji, extract_thoughts, extract_soul_updates
from revival import RevivalManager
from auto_chat import AutoChatManager
from reminders import ReminderManager
from heartbeat import HeartbeatManager
from tamagotchi import consume_emoji, deplete_stats, build_tamagotchi_footer, validate_rate, parse_emoji_list, broadcast_death

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is not set. "
        "Copy .env.template to .env and paste your bot token."
    )

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Runtime config (loaded from disk on startup)
bot_config: dict = {}

# Managers (initialised in on_ready)
revival_manager: RevivalManager | None = None
auto_chat_manager: AutoChatManager | None = None
reminder_manager: ReminderManager | None = None
heartbeat_manager: HeartbeatManager | None = None

# Message batching: tracks which channels are mid-generation and queues
# incoming mentions/replies so they can be processed as a single batch.
_generating_channels: set[int] = set()          # channel IDs currently generating
_pending_messages: dict[int, list] = defaultdict(list)  # channel_id -> [Message, ...]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _read_soc_context(bot_ref, config: dict) -> str:
    """Read SoC channel messages and return formatted context string (or '')."""
    soc_context_enabled = config.get("soc_context_enabled", False)
    soc_channel_id = config.get("soc_channel_id")
    if not soc_context_enabled or not soc_channel_id:
        return ""

    soc_count = config.get("soc_context_count", 10)
    soc_channel = bot_ref.get_channel(int(soc_channel_id))
    if soc_channel is None:
        return ""

    soc_messages = []
    async for msg in soc_channel.history(limit=soc_count):
        soc_messages.append(msg)
    soc_messages.reverse()

    # Apply [ce] cutoff to SoC context
    ce_idx = None
    for i, m in enumerate(soc_messages):
        if m.content.strip().lower() == "[ce]":
            ce_idx = i
    if ce_idx is not None:
        soc_messages = soc_messages[ce_idx + 1:]

    if not soc_messages:
        return ""

    soc_lines = []
    for msg in soc_messages:
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        soc_lines.append(f"[{ts}] {msg.content}")
    return (
        "\n[YOUR PREVIOUS THOUGHTS]\n"
        + "\n".join(soc_lines)
        + "\n[END YOUR PREVIOUS THOUGHTS]\n"
    )


async def _handle_soc_extraction(response_text: str, bot_ref, config: dict) -> str:
    """Extract thoughts, send to SoC channel, return clean text."""
    soc_enabled = config.get("soc_enabled", False)
    soc_channel_id = config.get("soc_channel_id")
    clean_text, thoughts_text = extract_thoughts(response_text)
    if thoughts_text and soc_enabled and soc_channel_id:
        thought_channel = bot_ref.get_channel(int(soc_channel_id))
        if thought_channel is not None:
            for chunk in chunk_message(thoughts_text):
                await thought_channel.send(chunk)
    return clean_text

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    global bot_config, revival_manager, auto_chat_manager, reminder_manager, heartbeat_manager
    bot_config = load_config()

    revival_manager = RevivalManager(bot, bot_config)
    revival_manager.start()

    auto_chat_manager = AutoChatManager(bot, bot_config)
    auto_chat_manager.start()

    reminder_manager = ReminderManager(bot, bot_config)
    reminder_manager.start()

    heartbeat_manager = HeartbeatManager(bot, bot_config)
    heartbeat_manager.start()

    try:
        synced = await bot.tree.sync()
        print(f"[ChatBuddy] Online as {bot.user} — synced {len(synced)} command(s)")
    except Exception as e:
        print(f"[ChatBuddy] Failed to sync commands: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def purgecommands(ctx):
    """Nuke all guild-specific slash commands and resync global ones to clear 'ghosts'."""
    bot.tree.clear_commands(guild=ctx.guild)
    await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"✅ Wiped old guild slash commands and refreshed the tree for {ctx.guild.name}.")



@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    # Channel whitelist gate
    channel_key = str(message.channel.id)
    allowed = bot_config.get("allowed_channels", {})
    if not allowed.get(channel_key, False):
        return

    is_mentioned = bot.user in message.mentions
    is_reply_to_bot = (
        message.reference is not None
        and message.reference.resolved is not None
        and isinstance(message.reference.resolved, discord.Message)
        and message.reference.resolved.author == bot.user
    )

    # Auto-chat reactivation: if mentioned/replied in the auto-chat channel
    # while idle, wake it up and respond normally
    auto_chat_channel = bot_config.get("auto_chat_channel_id")
    if auto_chat_channel and channel_key == str(auto_chat_channel):
        if auto_chat_manager and auto_chat_manager.is_idle:
            if is_mentioned or is_reply_to_bot:
                auto_chat_manager.reactivate()
                # Fall through to normal response below

    if not is_mentioned and not is_reply_to_bot:
        await bot.process_commands(message)
        return

    # ── Bot-to-bot response gate (only for mention/reply) ──────────
    if message.author.bot:
        if not bot_config.get("respond_to_bot", False):
            return  # responding to bots is disabled
        # Check consecutive bot message limit
        limit = bot_config.get("respond_bot_limit", 3)
        limit = max(1, min(9, limit))
        recent_msgs: list[discord.Message] = []
        async for msg in message.channel.history(limit=limit):
            recent_msgs.append(msg)
        # If ALL of the last N messages are from bots/apps, stop
        if recent_msgs and all(m.author.bot for m in recent_msgs):
            return

    # If it is mentioned, also make sure we process commands in case it's a command too
    await bot.process_commands(message)

    # ── Message batching: queue if already generating ──────────────
    ch_id = message.channel.id
    if ch_id in _generating_channels:
        # Another generation is in progress — queue this message
        _pending_messages[ch_id].append(message)
        return

    # Mark this channel as generating
    _generating_channels.add(ch_id)
    try:
        await _generate_and_respond(message)

        # Process any messages that queued up during generation
        while _pending_messages[ch_id]:
            batch = _pending_messages[ch_id].copy()
            _pending_messages[ch_id].clear()
            await _generate_batched_response(message.channel, batch)
    finally:
        _generating_channels.discard(ch_id)
        _pending_messages.pop(ch_id, None)


# ---------------------------------------------------------------------------
# Core response helpers (extracted from on_message)
# ---------------------------------------------------------------------------

async def _generate_and_respond(message: discord.Message):
    """Handle a single mention/reply — the normal response flow."""
    async with message.channel.typing():
        user_text = strip_mention(message.content, bot.user.id)
        if not user_text:
            user_text = "(empty message)"

        # Tamagotchi: consume emoji from user input BEFORE generate
        consume_emoji(message.content, bot_config)

        import re
        if bot_config.get("duck_search_enabled", False):
            if "!search" in user_text.lower():
                parts = re.split(r"!search", user_text, flags=re.IGNORECASE, maxsplit=1)
                query = parts[1].strip() if len(parts) > 1 else ""
                if not query:
                    query = user_text.strip()
                from duck_search import get_duckduckgo_context
                import asyncio
                search_ctx = await asyncio.to_thread(get_duckduckgo_context, query)
                user_text = f"{search_ctx}\n\nUser Question/Message: {user_text}"

        history_limit = bot_config.get("chat_history_limit", 30)
        history_messages = []
        async for msg in message.channel.history(limit=history_limit, before=message):
            history_messages.append(msg)
        history_messages.reverse()

        ce_channels = bot_config.get("ce_channels", {})
        channel_key = str(message.channel.id)
        ce_enabled = ce_channels.get(channel_key, True)
        context = format_context(history_messages, ce_enabled=ce_enabled)

        # SoC context injection (after chat history)
        context += await _read_soc_context(bot, bot_config)

        attachments_data = []
        if bot_config.get("multimodal_enabled", False):
            for a in message.attachments:
                if a.content_type and (a.content_type.startswith("image/") or a.content_type.startswith("audio/")):
                    file_bytes = await a.read()
                    attachments_data.append({"mime_type": a.content_type, "data": file_bytes})

        response_text, audio_bytes, soul_logs, reminder_cmds = await generate(
            user_text, context, bot_config,
            speaker_name=message.author.display_name,
            speaker_id=str(message.author.id),
            attachments=attachments_data,
        )

        # Tamagotchi: deplete stats after generate
        death_msg = deplete_stats(bot_config)
        if death_msg:
            response_text = (response_text + "\n\n" + death_msg) if response_text else death_msg
            await broadcast_death(bot, bot_config)

        # AI-triggered 2-stage turn for Web Search
        import re
        if bot_config.get("duck_search_enabled", False):
            search_match = re.search(r"<!search:\s*(.+?)>", response_text)
            if search_match:
                query = search_match.group(1).strip()
                from duck_search import get_duckduckgo_context
                import asyncio
                search_ctx = await asyncio.to_thread(get_duckduckgo_context, query)
                
                second_input = (
                    f"{response_text}\n\n"
                    f"[Search Results for '{query}']:\n{search_ctx}\n\n"
                    f"Please review the search results above and generate your final user-facing answer. Dodge all <!search:> tags now."
                )
                
                response_text, audio_bytes, soul_logs2, reminder_cmds2 = await generate(
                    second_input, context, bot_config,
                    speaker_name=message.author.display_name,
                    speaker_id=str(message.author.id),
                    attachments=None,  # Do not resend attachments on the invisible turn
                )
                # Tamagotchi: deplete stats for the second inference too
                death_msg2 = deplete_stats(bot_config)
                if death_msg2:
                    response_text = (response_text + "\n\n" + death_msg2) if response_text else death_msg2
                    await broadcast_death(bot, bot_config)
                if soul_logs2: soul_logs.extend(soul_logs2)
                if reminder_cmds2: reminder_cmds.extend(reminder_cmds2)

        # Apply any reminder/wake-time commands the bot emitted
        if reminder_cmds and reminder_manager:
            await reminder_manager._apply_commands(reminder_cmds, source_channel_id=str(message.channel.id))

        # SoC thought extraction
        response_text = await _handle_soc_extraction(response_text, bot, bot_config)

        # Resolve custom emoji shortcodes before sending
        response_text = resolve_custom_emoji(response_text, message.guild)

        # Tamagotchi: append stats footer only if there is visible text to send
        tama_footer = build_tamagotchi_footer(bot_config)
        if tama_footer and response_text.strip():
            response_text = response_text.rstrip() + "\n" + tama_footer

        if audio_bytes:
            audio_file = discord.File(fp=io.BytesIO(audio_bytes), filename="chatbuddy_voice.wav")
            await message.reply(file=audio_file, mention_author=False)
            chunks = chunk_message(response_text)
            for chunk in chunks:
                await message.channel.send(chunk)
        else:
            chunks = chunk_message(response_text)
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await message.reply(chunk, mention_author=False)
                else:
                    await message.channel.send(chunk)

        # Send soul logs to configured channel if present
        if soul_logs and bot_config.get("soul_channel_enabled"):
            ch_id = bot_config.get("soul_channel_id")
            if ch_id:
                soul_ch = bot.get_channel(int(ch_id))
                if soul_ch:
                    joined_logs = "\n".join(soul_logs)
                    for log_chunk in chunk_message(joined_logs, limit=1900):
                        await soul_ch.send(f"**🧠 Soul Updates:**\n{log_chunk}")


async def _generate_batched_response(channel: discord.TextChannel, batch: list[discord.Message]):
    """
    Process a batch of messages that arrived during generation.
    Formats them as a single chatlog input and generates one response.
    """
    async with channel.typing():
        # Build the batched input showing who said what
        batch_lines = []
        for msg in batch:
            user_text = strip_mention(msg.content, bot.user.id)
            if not user_text:
                user_text = "(empty message)"
            batch_lines.append(f"[{msg.author.display_name}]: {user_text}")
        batched_input = (
            "[MULTIPLE MESSAGES RECEIVED — respond to all of them naturally]\n"
            + "\n".join(batch_lines)
        )

        # Tamagotchi: consume emoji from all user messages in the batch
        for msg in batch:
            consume_emoji(msg.content, bot_config)

        import re
        if bot_config.get("duck_search_enabled", False):
            if "!search" in batched_input.lower():
                parts = re.split(r"!search", batched_input, flags=re.IGNORECASE, maxsplit=1)
                query = parts[1].strip() if len(parts) > 1 else ""
                if not query:
                    query = batched_input.strip()
                from duck_search import get_duckduckgo_context
                import asyncio
                search_ctx = await asyncio.to_thread(get_duckduckgo_context, query)
                batched_input = f"{search_ctx}\n\nUser Question/Message: {batched_input}"

        history_limit = bot_config.get("chat_history_limit", 30)
        history_messages = []
        async for msg in channel.history(limit=history_limit):
            history_messages.append(msg)
        history_messages.reverse()

        ce_channels = bot_config.get("ce_channels", {})
        channel_key = str(channel.id)
        ce_enabled = ce_channels.get(channel_key, True)
        context = format_context(history_messages, ce_enabled=ce_enabled)

        context += await _read_soc_context(bot, bot_config)

        attachments_data = []
        if bot_config.get("multimodal_enabled", False):
            for m in batch:
                for a in m.attachments:
                    if a.content_type and (a.content_type.startswith("image/") or a.content_type.startswith("audio/")):
                        file_bytes = await a.read()
                        attachments_data.append({"mime_type": a.content_type, "data": file_bytes})

        # Use the last message's author info for speaker metadata
        last_msg = batch[-1]
        response_text, audio_bytes, soul_logs, reminder_cmds = await generate(
            batched_input, context, bot_config,
            speaker_name=last_msg.author.display_name,
            speaker_id=str(last_msg.author.id),
            attachments=attachments_data,
        )

        # Tamagotchi: deplete stats after generate
        death_msg = deplete_stats(bot_config)
        if death_msg:
            response_text = (response_text + "\n\n" + death_msg) if response_text else death_msg
            await broadcast_death(bot, bot_config)

        # AI-triggered 2-stage turn for Web Search
        import re
        if bot_config.get("duck_search_enabled", False):
            search_match = re.search(r"<!search:\s*(.+?)>", response_text)
            if search_match:
                query = search_match.group(1).strip()
                from duck_search import get_duckduckgo_context
                import asyncio
                search_ctx = await asyncio.to_thread(get_duckduckgo_context, query)
                
                second_input = (
                    f"{response_text}\n\n"
                    f"[Search Results for '{query}']:\n{search_ctx}\n\n"
                    f"Please review the search results above and generate your final user-facing answer. Dodge all <!search:> tags now."
                )
                
                response_text, audio_bytes, soul_logs2, reminder_cmds2 = await generate(
                    second_input, context, bot_config,
                    speaker_name=last_msg.author.display_name,
                    speaker_id=str(last_msg.author.id),
                    attachments=None,  # Do not resend attachments on the invisible turn
                )
                # Tamagotchi: deplete stats for the second inference too
                death_msg2 = deplete_stats(bot_config)
                if death_msg2:
                    response_text = (response_text + "\n\n" + death_msg2) if response_text else death_msg2
                    await broadcast_death(bot, bot_config)
                if soul_logs2: soul_logs.extend(soul_logs2)
                if reminder_cmds2: reminder_cmds.extend(reminder_cmds2)

        if reminder_cmds and reminder_manager:
            await reminder_manager._apply_commands(reminder_cmds, source_channel_id=str(channel.id))

        response_text = await _handle_soc_extraction(response_text, bot, bot_config)
        response_text = resolve_custom_emoji(response_text, channel.guild)

        # Tamagotchi: append stats footer only if there is visible text to send
        tama_footer = build_tamagotchi_footer(bot_config)
        if tama_footer and response_text.strip():
            response_text = response_text.rstrip() + "\n" + tama_footer

        if audio_bytes:
            audio_file = discord.File(fp=io.BytesIO(audio_bytes), filename="chatbuddy_voice.wav")
            await channel.send(file=audio_file)
            chunks = chunk_message(response_text)
            for chunk in chunks:
                await channel.send(chunk)
        else:
            chunks = chunk_message(response_text)
            for chunk in chunks:
                await channel.send(chunk)

        if soul_logs and bot_config.get("soul_channel_enabled"):
            ch_id = bot_config.get("soul_channel_id")
            if ch_id:
                soul_ch = bot.get_channel(int(ch_id))
                if soul_ch:
                    joined_logs = "\n".join(soul_logs)
                    for log_chunk in chunk_message(joined_logs, limit=1900):
                        await soul_ch.send(f"**🧠 Soul Updates:**\n{log_chunk}")


# ---------------------------------------------------------------------------
# Slash commands — Core settings
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
    bot_config["api_key"] = key
    save_config(bot_config)
    await interaction.response.send_message("✅ API key has been set and saved.", ephemeral=True)


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
@app_commands.describe(limit="Number of previous messages (default: 30)")
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
    prompt = prompt.replace("\\n", "\n")
    bot_config["system_prompt"] = prompt
    save_config(bot_config)
    await interaction.response.send_message("✅ System prompt updated and saved.", ephemeral=True)


@bot.tree.command(name="show-sys-instruct", description="Display the full effective system prompt")
@app_commands.default_permissions(administrator=True)
async def show_sys_instruct(interaction: discord.Interaction):
    prompt = build_system_prompt(bot_config, include_word_game=True)
    if not prompt:
        prompt = "(not set)"

    full_text = f"📝 **Current effective system prompt:**\n```\n{prompt}\n```"
    chunks = chunk_message(full_text)
    await interaction.response.send_message(chunks[0], ephemeral=True)
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)


# ---------------------------------------------------------------------------
# Slash commands — Text model mode
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
        key_status = "set" if bot_config.get("api_key_custom", "").strip() else "not set"
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
# Slash commands — Audio clip mode
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


# ---------------------------------------------------------------------------
# Slash commands — Channel / context settings
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
# Slash commands — Stream of Consciousness (SoC)
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
            f"✅ SoC thoughts channel set to {channel.mention} — **enabled**.\n"
            f"Text between `<my-thoughts>` and `</my-thoughts>` will be extracted and posted there.",
            ephemeral=True,
        )
    else:
        bot_config["soc_enabled"] = False
        save_config(bot_config)
        await interaction.response.send_message(
            f"✅ SoC thoughts channel set to {channel.mention} — **disabled**.",
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
        f"✅ SoC context **{state}** — reading last **{count}** thought messages.",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Slash commands — Dynamic system prompt
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


# ---------------------------------------------------------------------------
# Slash commands — Word game
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-word-game", description="Set the word game rules prompt + enable/disable")
@app_commands.describe(
    prompt="Game rules prompt (use {secret-word} as placeholder)",
    enabled="True = word game active, False = disabled",
)
@app_commands.default_permissions(administrator=True)
async def set_word_game(interaction: discord.Interaction, prompt: str, enabled: bool):
    prompt = prompt.replace("\\n", "\n")
    bot_config["word_game_prompt"] = prompt
    bot_config["word_game_enabled"] = enabled
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Word game **{state}**.\n"
        f"Prompt contains `{{secret-word}}`: **{'yes' if '{secret-word}' in prompt else 'no'}**",
        ephemeral=True,
    )


@bot.tree.command(name="set-word-game-selector-prompt", description="Set the hidden-turn prompt for selecting a secret word")
@app_commands.describe(prompt="Instruction appended to main prompt for the hidden word-selection turn")
@app_commands.default_permissions(administrator=True)
async def set_word_game_selector_prompt(interaction: discord.Interaction, prompt: str):
    prompt = prompt.replace("\\n", "\n")
    bot_config["word_game_selector_prompt"] = prompt
    save_config(bot_config)
    await interaction.response.send_message(
        "✅ Word game selector prompt saved.", ephemeral=True
    )


@bot.tree.command(name="set-secret-word", description="Trigger a hidden turn to pick a new secret word")
@app_commands.describe(prompt="Theme or constraint for the secret word (e.g. 'animals', 'foods')")
async def set_secret_word(interaction: discord.Interaction, prompt: str):
    # --- Role-based permission check ---
    allowed_roles = [str(r) for r in bot_config.get("secret_word_allowed_roles", [])]
    is_admin = False
    has_role = False
    
    if getattr(interaction, "guild", None) and isinstance(interaction.user, discord.Member):
        is_admin = interaction.user.guild_permissions.administrator
        has_role = any(str(role.id) in allowed_roles for role in interaction.user.roles)
        
    if not is_admin and not has_role:
        await interaction.response.send_message(
            "⚠️ You don't have permission to use this command. "
            "Ask an admin to grant your role access via `/set-secret-word-permission`.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    # Build hidden-turn system prompt: main + selector only
    main_prompt = bot_config.get("system_prompt", "")
    selector = bot_config.get("word_game_selector_prompt", "")
    hidden_sys = (main_prompt + "\n\n" + selector).strip() if selector else main_prompt

    hidden_response, _, _, _ = await generate(
        prompt=prompt,
        context="",
        config=bot_config,
        system_prompt_override=hidden_sys,
    )

    # Parse {secret-word:WORD} from the response
    word_match = re.search(r"\{secret-word:(.+?)\}", hidden_response)
    if word_match:
        secret = word_match.group(1).strip()
        bot_config["secret_word"] = secret
        save_config(bot_config)
        await interaction.followup.send("✅ A new secret word has been set!", ephemeral=True)
    else:
        await interaction.followup.send(
            "⚠️ Could not parse a secret word from the hidden turn. "
            "Make sure the selector prompt instructs the model to output `{secret-word:WORD}`.",
            ephemeral=True,
        )


@bot.tree.command(name="set-secret-word-permission", description="Grant or revoke a role's access to /set-secret-word")
@app_commands.describe(
    role="The role to configure",
    allowed="True = grant access, False = revoke access",
)
@app_commands.default_permissions(administrator=True)
async def set_secret_word_permission(interaction: discord.Interaction, role: discord.Role, allowed: bool):
    roles_list: list = bot_config.get("secret_word_allowed_roles", [])
    role_id = str(role.id)
    if allowed:
        if role_id not in roles_list:
            roles_list.append(role_id)
        action = "granted"
    else:
        if role_id in roles_list:
            roles_list.remove(role_id)
        action = "revoked"
    bot_config["secret_word_allowed_roles"] = roles_list
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ `/set-secret-word` access **{action}** for role **{role.name}**.",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Slash commands — Auto-chat mode
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


@bot.tree.command(name="set-auto-idle-message", description="Set the message posted when auto-chat enters idle mode")
@app_commands.describe(message="The idle message (default: 'Going afk, ping me if you need me')")
@app_commands.default_permissions(administrator=True)
async def set_auto_idle_message(interaction: discord.Interaction, message: str):
    message = message.replace("\\n", "\n")
    bot_config["auto_chat_idle_message"] = message
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Auto-chat idle message set to:\n```{message}```", ephemeral=True
    )


# ---------------------------------------------------------------------------
# Slash commands — Soul feature
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


# ---------------------------------------------------------------------------
# Slash commands — Reminders & auto-wake
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


# ---------------------------------------------------------------------------
# Slash commands — Bot-to-bot response control
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-respond-to-bot", description="Enable or disable responding to other bots")
@app_commands.describe(enabled="True to respond to bots, False to ignore them")
@app_commands.default_permissions(administrator=True)
async def set_respond_to_bot(interaction: discord.Interaction, enabled: bool):
    bot_config["respond_to_bot"] = enabled
    save_config(bot_config)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Responding to other bots is now **{state}**.",
        ephemeral=True,
    )


@bot.tree.command(name="set-respond-bot-limit", description="Set how many consecutive bot messages before stopping replies (1-9)")
@app_commands.describe(limit="Threshold: stop if the last N messages are all from bots/apps (1-9)")
@app_commands.default_permissions(administrator=True)
async def set_respond_bot_limit(interaction: discord.Interaction, limit: int):
    if limit < 1 or limit > 9:
        await interaction.response.send_message(
            "❌ Limit must be between 1 and 9.", ephemeral=True
        )
        return
    bot_config["respond_bot_limit"] = limit
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Bot-to-bot reply limit set to **{limit}** consecutive bot messages.",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Slash commands — Heartbeat
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-heartbeat", description="Configure periodic heartbeat messages")
@app_commands.describe(
    enabled="True to enable, False to disable",
    interval="Interval in minutes between heartbeats",
    channel="Channel to post heartbeat messages in",
    prompt="The input prompt the bot receives each heartbeat",
)
@app_commands.default_permissions(administrator=True)
async def set_heartbeat_cmd(
    interaction: discord.Interaction,
    enabled: bool,
    interval: int,
    channel: discord.TextChannel,
    prompt: str,
):
    bot_config["heartbeat_enabled"] = enabled
    bot_config["heartbeat_interval_minutes"] = max(1, interval)
    bot_config["heartbeat_channel_id"] = str(channel.id)
    bot_config["heartbeat_prompt"] = prompt
    save_config(bot_config)

    # Restart the heartbeat manager with new settings
    global heartbeat_manager
    if heartbeat_manager:
        heartbeat_manager.stop()
    heartbeat_manager = HeartbeatManager(bot, bot_config)
    heartbeat_manager.start()

    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(
        f"✅ Heartbeat **{state}** — every **{max(1, interval)}min** in {channel.mention}.",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Slash commands — Tamagotchi minigame
# ---------------------------------------------------------------------------

from tamagotchi import validate_rate, parse_emoji_list


@bot.tree.command(name="set-tamagochi-mode", description="Enable or disable Tamagotchi mode")
@app_commands.describe(enabled="True to enable, False to disable")
@app_commands.default_permissions(administrator=True)
async def set_tamagochi_mode(interaction: discord.Interaction, enabled: bool):
    if enabled and not bot_config.get("tamagotchi_rules_set", False):
        await interaction.response.send_message(
            "⚠️ Cannot enable Tamagotchi mode — rules have not been set yet.\n"
            "Run `/set-tamagochi-rules` first to configure accepted emoji and stat limits.",
            ephemeral=True,
        )
        return
    bot_config["tamagotchi_enabled"] = enabled
    save_config(bot_config)
    state = "**enabled** 🐣" if enabled else "**disabled** 🚫"
    await interaction.response.send_message(
        f"✅ Tamagotchi mode {state}.", ephemeral=True
    )


@bot.tree.command(name="set-tamagochi-rules", description="Set the Tamagotchi accepted emoji and stat limits")
@app_commands.describe(
    food_emoji="Accepted food emoji (e.g. 🍔🍕🍩)",
    drink_emoji="Accepted drink emoji (e.g. 💧🥤☕)",
    entertainment_emoji="Accepted entertainment emoji (e.g. 🎮🎲🎵)",
    hunger="Maximum hunger stat value",
    thirst="Maximum thirst stat value",
    happiness="Maximum happiness stat value",
)
@app_commands.default_permissions(administrator=True)
async def set_tamagochi_rules(
    interaction: discord.Interaction,
    food_emoji: str,
    drink_emoji: str,
    entertainment_emoji: str,
    hunger: int,
    thirst: int,
    happiness: int,
):
    if hunger < 1 or thirst < 1 or happiness < 1:
        await interaction.response.send_message(
            "⚠️ All stat maximums must be at least 1.", ephemeral=True
        )
        return

    food_list = parse_emoji_list(food_emoji)
    drink_list = parse_emoji_list(drink_emoji)
    ent_list = parse_emoji_list(entertainment_emoji)

    if not food_list and not drink_list and not ent_list:
        await interaction.response.send_message(
            "⚠️ No valid emoji detected. Please include at least one emoji in your input.",
            ephemeral=True,
        )
        return

    bot_config["tamagotchi_food_emoji"] = food_list
    bot_config["tamagotchi_drink_emoji"] = drink_list
    bot_config["tamagotchi_entertainment_emoji"] = ent_list
    bot_config["tamagotchi_max_hunger"] = hunger
    bot_config["tamagotchi_max_thirst"] = thirst
    bot_config["tamagotchi_max_happiness"] = happiness
    # Reset current stats to max on rule setup
    bot_config["tamagotchi_hunger"] = float(hunger)
    bot_config["tamagotchi_thirst"] = float(thirst)
    bot_config["tamagotchi_happiness"] = float(happiness)
    bot_config["tamagotchi_rules_set"] = True
    save_config(bot_config)

    await interaction.response.send_message(
        f"✅ Tamagotchi rules configured!\n"
        f"• Food emoji: {' '.join(food_list) or '(none)'}\n"
        f"• Drink emoji: {' '.join(drink_list) or '(none)'}\n"
        f"• Entertainment emoji: {' '.join(ent_list) or '(none)'}\n"
        f"• Hunger max: **{hunger}** | Thirst max: **{thirst}** | Happiness max: **{happiness}**\n"
        f"• Current stats reset to max values.",
        ephemeral=True,
    )


@bot.tree.command(name="set-tamagochi-depletion-rate", description="Set how much each stat decreases per inference")
@app_commands.describe(
    food="Hunger depletion per inference (max 2 decimals, max 99)",
    thirst="Thirst depletion per inference (max 2 decimals, max 99)",
    happiness="Happiness depletion per inference (max 2 decimals, max 99)",
)
@app_commands.default_permissions(administrator=True)
async def set_tamagochi_depletion_rate(
    interaction: discord.Interaction,
    food: float,
    thirst: float,
    happiness: float,
):
    for name, val in [("food", food), ("thirst", thirst), ("happiness", happiness)]:
        if not validate_rate(val):
            await interaction.response.send_message(
                f"⚠️ Invalid **{name}** rate: `{val}`. Must have at most 2 decimal places and be ≤ 99.",
                ephemeral=True,
            )
            return
    bot_config["tamagotchi_depletion_food"] = food
    bot_config["tamagotchi_depletion_thirst"] = thirst
    bot_config["tamagotchi_depletion_happiness"] = happiness
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Tamagotchi depletion rates set:\n"
        f"• Hunger: **{food}**/turn | Thirst: **{thirst}**/turn | Happiness: **{happiness}**/turn",
        ephemeral=True,
    )


@bot.tree.command(name="set-tamagochi-fill-rate", description="Set how much each stat increases per emoji consumed")
@app_commands.describe(
    food="Hunger gained per food emoji (max 2 decimals, max 99, default 1)",
    thirst="Thirst gained per drink emoji (max 2 decimals, max 99, default 1)",
    happiness="Happiness gained per entertainment emoji (max 2 decimals, max 99, default 1)",
)
@app_commands.default_permissions(administrator=True)
async def set_tamagochi_fill_rate(
    interaction: discord.Interaction,
    food: float,
    thirst: float,
    happiness: float,
):
    for name, val in [("food", food), ("thirst", thirst), ("happiness", happiness)]:
        if not validate_rate(val):
            await interaction.response.send_message(
                f"⚠️ Invalid **{name}** rate: `{val}`. Must have at most 2 decimal places and be ≤ 99.",
                ephemeral=True,
            )
            return
    bot_config["tamagotchi_fill_food"] = food
    bot_config["tamagotchi_fill_thirst"] = thirst
    bot_config["tamagotchi_fill_happiness"] = happiness
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Tamagotchi fill rates set:\n"
        f"• Hunger: **{food}**/emoji | Thirst: **{thirst}**/emoji | Happiness: **{happiness}**/emoji",
        ephemeral=True,
    )


@bot.tree.command(name="set-tamagochi-max-consumption", description="Limit how many emoji the bot can consume per input")
@app_commands.describe(limit="Max emoji consumed per input (0 = unlimited, default 0)")
@app_commands.default_permissions(administrator=True)
async def set_tamagochi_max_consumption(interaction: discord.Interaction, limit: int):
    if limit < 0:
        await interaction.response.send_message(
            "⚠️ Limit must be 0 (unlimited) or a positive number.", ephemeral=True
        )
        return
    bot_config["tamagotchi_max_consumption"] = limit
    save_config(bot_config)
    desc = "**unlimited** (no cap)" if limit == 0 else f"**{limit}** emoji per input"
    await interaction.response.send_message(
        f"✅ Tamagotchi max consumption set to {desc}.", ephemeral=True
    )


@bot.tree.command(name="show-tamagochi-stats", description="Show current Tamagotchi stats and configuration")
@app_commands.default_permissions(administrator=True)
async def show_tamagochi_stats(interaction: discord.Interaction):
    from tamagotchi import _format_stat
    enabled = bot_config.get("tamagotchi_enabled", False)
    rules_set = bot_config.get("tamagotchi_rules_set", False)

    if not rules_set:
        await interaction.response.send_message(
            "⚠️ Tamagotchi rules have not been configured yet. Run `/set-tamagochi-rules` first.",
            ephemeral=True,
        )
        return

    hunger = bot_config.get("tamagotchi_hunger", 0)
    thirst = bot_config.get("tamagotchi_thirst", 0)
    happiness = bot_config.get("tamagotchi_happiness", 0)
    max_h = bot_config.get("tamagotchi_max_hunger", 10)
    max_t = bot_config.get("tamagotchi_max_thirst", 10)
    max_hp = bot_config.get("tamagotchi_max_happiness", 10)

    food_emoji = " ".join(bot_config.get("tamagotchi_food_emoji", []))
    drink_emoji = " ".join(bot_config.get("tamagotchi_drink_emoji", []))
    ent_emoji = " ".join(bot_config.get("tamagotchi_entertainment_emoji", []))

    dep_f = bot_config.get("tamagotchi_depletion_food", 1.0)
    dep_t = bot_config.get("tamagotchi_depletion_thirst", 1.0)
    dep_h = bot_config.get("tamagotchi_depletion_happiness", 1.0)
    fill_f = bot_config.get("tamagotchi_fill_food", 1.0)
    fill_t = bot_config.get("tamagotchi_fill_thirst", 1.0)
    fill_h = bot_config.get("tamagotchi_fill_happiness", 1.0)
    max_cons = bot_config.get("tamagotchi_max_consumption", 0)

    state = "✅ Enabled" if enabled else "❌ Disabled"
    cons_desc = "Unlimited" if max_cons == 0 else str(max_cons)

    msg = (
        f"🐣 **Tamagotchi Status** — {state}\n\n"
        f"**Current Stats:**\n"
        f"• 🍔 Hunger: {_format_stat(hunger)}/{max_h}\n"
        f"• 💧 Thirst: {_format_stat(thirst)}/{max_t}\n"
        f"• 😊 Happiness: {_format_stat(happiness)}/{max_hp}\n"
    )

    # Hardcore sickness section
    if bot_config.get("tamagotchi_hardcore_enabled", False):
        sickness = bot_config.get("tamagotchi_sickness", 0)
        max_s = bot_config.get("tamagotchi_max_sickness", 10)
        med_emoji = " ".join(bot_config.get("tamagotchi_medicine_emoji", []))
        med_heal = bot_config.get("tamagotchi_medicine_heal", 1.0)
        thresh_f = bot_config.get("tamagotchi_sickness_threshold_food", 2.0)
        thresh_t = bot_config.get("tamagotchi_sickness_threshold_thirst", 2.0)
        thresh_hp = bot_config.get("tamagotchi_sickness_threshold_happiness", 2.0)
        inc_f = bot_config.get("tamagotchi_sickness_increase_food", 1.0)
        inc_t = bot_config.get("tamagotchi_sickness_increase_thirst", 1.0)
        inc_hp = bot_config.get("tamagotchi_sickness_increase_happiness", 1.0)
        msg += (
            f"• 🤒 Sickness: {_format_stat(sickness)}/{max_s} **(HARDCORE)**\n\n"
            f"**Hardcore Settings:**\n"
            f"• Medicine emoji: {med_emoji or '(none)'} — heals **{med_heal}**/emoji\n"
            f"• Sickness thresholds: 🍔 <{thresh_f} | 💧 <{thresh_t} | 😊 <{thresh_hp}\n"
            f"• Sickness increase: 🍔 +{inc_f} | 💧 +{inc_t} | 😊 +{inc_hp}\n"
        )
        rip_msg = bot_config.get("tamagotchi_rip_message", "").strip()
        msg += f"• Death message: {rip_msg or '(default)'}\n"
    else:
        msg += "\n"

    msg += (
        f"**Accepted Emoji:**\n"
        f"• Food: {food_emoji or '(none)'}\n"
        f"• Drink: {drink_emoji or '(none)'}\n"
        f"• Entertainment: {ent_emoji or '(none)'}\n\n"
        f"**Rates:**\n"
        f"• Depletion: 🍔 {dep_f}/turn | 💧 {dep_t}/turn | 😊 {dep_h}/turn\n"
        f"• Fill: 🍔 {fill_f}/emoji | 💧 {fill_t}/emoji | 😊 {fill_h}/emoji\n"
        f"• Max consumption: {cons_desc}"
    )

    await interaction.response.send_message(msg, ephemeral=True)


# ---------------------------------------------------------------------------
# Slash commands — Tamagotchi hardcore mode
# ---------------------------------------------------------------------------


@bot.tree.command(name="set-hardcore-tamagochi-mode", description="Enable or disable hardcore Tamagotchi mode (sickness + death)")
@app_commands.describe(enabled="True to enable, False to disable")
@app_commands.default_permissions(administrator=True)
async def set_hardcore_tamagochi_mode(interaction: discord.Interaction, enabled: bool):
    if enabled:
        # Check that core tamagotchi mode is enabled
        if not bot_config.get("tamagotchi_enabled", False):
            await interaction.response.send_message(
                "⚠️ Cannot enable hardcore mode — base Tamagotchi mode is not enabled.\n"
                "Run `/set-tamagochi-mode true` first.",
                ephemeral=True,
            )
            return

        # Check all hardcore settings are configured
        missing = []
        if bot_config.get("tamagotchi_max_sickness", 10) == 10 and not bot_config.get("_hc_sickness_set", False):
            missing.append("`/set-hardcore-sickness-stat` — max sickness value")
        if not bot_config.get("tamagotchi_medicine_emoji", []):
            missing.append("`/set-hardcore-tamagochi-medicine` — medicine emoji + heal amount")
        if not bot_config.get("_hc_threshold_set", False):
            missing.append("`/set-hc-sick-threshold` — sickness thresholds")
        if not bot_config.get("_hc_increase_set", False):
            missing.append("`/set-hc-sick-increase` — sickness increase rates")

        if missing:
            missing_text = "\n".join(f"• {m}" for m in missing)
            await interaction.response.send_message(
                f"⚠️ Cannot enable hardcore mode — the following settings are missing:\n{missing_text}",
                ephemeral=True,
            )
            return

        bot_config["tamagotchi_hardcore_enabled"] = True
        bot_config["tamagotchi_hardcore_rules_set"] = True
        save_config(bot_config)
        await interaction.response.send_message(
            "✅ Hardcore Tamagotchi mode **enabled** 💀. Sickness is now active!",
            ephemeral=True,
        )
    else:
        # Disabling resets sickness to 0
        bot_config["tamagotchi_hardcore_enabled"] = False
        bot_config["tamagotchi_sickness"] = 0.0
        save_config(bot_config)
        await interaction.response.send_message(
            "✅ Hardcore Tamagotchi mode **disabled**. Sickness has been reset to 0.",
            ephemeral=True,
        )


@bot.tree.command(name="set-hardcore-sickness-stat", description="Set the max sickness value (death threshold)")
@app_commands.describe(max_sickness="Maximum sickness before death (max 2 decimals, max 99)")
@app_commands.default_permissions(administrator=True)
async def set_hardcore_sickness_stat(interaction: discord.Interaction, max_sickness: float):
    if not validate_rate(max_sickness) or max_sickness <= 0:
        await interaction.response.send_message(
            f"⚠️ Invalid value: `{max_sickness}`. Must be > 0, at most 2 decimal places, and ≤ 99.",
            ephemeral=True,
        )
        return
    bot_config["tamagotchi_max_sickness"] = max_sickness
    bot_config["_hc_sickness_set"] = True
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Max sickness set to **{max_sickness}**. The Tamagotchi dies when sickness reaches this.",
        ephemeral=True,
    )


@bot.tree.command(name="set-hardcore-tamagochi-medicine", description="Set medicine emoji and heal amount")
@app_commands.describe(
    emoji="Emoji that count as medicine (e.g. 💊🩹)",
    heal_amount="How much sickness decreases per medicine emoji (max 2 decimals, max 99)",
)
@app_commands.default_permissions(administrator=True)
async def set_hardcore_tamagochi_medicine(
    interaction: discord.Interaction, emoji: str, heal_amount: float
):
    if not validate_rate(heal_amount) or heal_amount <= 0:
        await interaction.response.send_message(
            f"⚠️ Invalid heal amount: `{heal_amount}`. Must be > 0, at most 2 decimal places, and ≤ 99.",
            ephemeral=True,
        )
        return
    med_list = parse_emoji_list(emoji)
    if not med_list:
        await interaction.response.send_message(
            "⚠️ No valid emoji detected. Please include at least one emoji.",
            ephemeral=True,
        )
        return
    bot_config["tamagotchi_medicine_emoji"] = med_list
    bot_config["tamagotchi_medicine_heal"] = heal_amount
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Medicine configured:\n"
        f"• Emoji: {' '.join(med_list)}\n"
        f"• Heal amount: **{heal_amount}** per emoji",
        ephemeral=True,
    )


@bot.tree.command(name="set-hc-sick-threshold", description="Set stat thresholds below which sickness increases")
@app_commands.describe(
    food="Sickness increases when hunger drops below this value",
    thirst="Sickness increases when thirst drops below this value",
    happiness="Sickness increases when happiness drops below this value",
)
@app_commands.default_permissions(administrator=True)
async def set_hardcore_tamagochi_sickness_threshold(
    interaction: discord.Interaction, food: float, thirst: float, happiness: float
):
    for name, val in [("food", food), ("thirst", thirst), ("happiness", happiness)]:
        if val < 0:
            await interaction.response.send_message(
                f"⚠️ Invalid **{name}** threshold: `{val}`. Must be ≥ 0.",
                ephemeral=True,
            )
            return
    bot_config["tamagotchi_sickness_threshold_food"] = food
    bot_config["tamagotchi_sickness_threshold_thirst"] = thirst
    bot_config["tamagotchi_sickness_threshold_happiness"] = happiness
    bot_config["_hc_threshold_set"] = True
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Sickness thresholds set:\n"
        f"• Sickness increases when: 🍔 Hunger < **{food}** | 💧 Thirst < **{thirst}** | 😊 Happiness < **{happiness}**",
        ephemeral=True,
    )


@bot.tree.command(name="set-hc-sick-increase", description="Set how much sickness increases per turn when below threshold")
@app_commands.describe(
    food="Sickness added per turn when hunger is below threshold (max 2 decimals, max 99)",
    thirst="Sickness added per turn when thirst is below threshold (max 2 decimals, max 99)",
    happiness="Sickness added per turn when happiness is below threshold (max 2 decimals, max 99)",
)
@app_commands.default_permissions(administrator=True)
async def set_hardcore_tamagochi_sickness_increase(
    interaction: discord.Interaction, food: float, thirst: float, happiness: float
):
    for name, val in [("food", food), ("thirst", thirst), ("happiness", happiness)]:
        if not validate_rate(val):
            await interaction.response.send_message(
                f"⚠️ Invalid **{name}** rate: `{val}`. Must have at most 2 decimal places and be ≤ 99.",
                ephemeral=True,
            )
            return
    bot_config["tamagotchi_sickness_increase_food"] = food
    bot_config["tamagotchi_sickness_increase_thirst"] = thirst
    bot_config["tamagotchi_sickness_increase_happiness"] = happiness
    bot_config["_hc_increase_set"] = True
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Sickness increase rates set:\n"
        f"• 🍔 +**{food}**/turn | 💧 +**{thirst}**/turn | 😊 +**{happiness}**/turn",
        ephemeral=True,
    )


@bot.tree.command(name="set-tamagochi-rip-message", description="Set the custom death message shown when the Tamagotchi dies")
@app_commands.describe(message="The message to display when the Tamagotchi dies (leave empty to use default)")
@app_commands.default_permissions(administrator=True)
async def set_tamagochi_rip_message(interaction: discord.Interaction, message: str):
    bot_config["tamagotchi_rip_message"] = message.strip()
    save_config(bot_config)
    if message.strip():
        await interaction.response.send_message(
            f"✅ Custom death message set:\n{message.strip()}",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "✅ Death message reset to default.",
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Slash commands — Custom model settings
# ---------------------------------------------------------------------------

@bot.tree.command(name="set-api-key-custom", description="Set the API key for the custom (non-Google) model")
@app_commands.describe(key="Your custom model API key")
@app_commands.default_permissions(administrator=True)
async def set_api_key_custom(interaction: discord.Interaction, key: str):
    bot_config["api_key_custom"] = key
    save_config(bot_config)
    await interaction.response.send_message("✅ Custom API key has been set and saved.", ephemeral=True)


@bot.tree.command(name="set-api-endpoint-custom", description="Set the endpoint for the custom (non-Google) model")
@app_commands.describe(endpoint="Full URL or model name for your custom model")
@app_commands.default_permissions(administrator=True)
async def set_api_endpoint_custom(interaction: discord.Interaction, endpoint: str):
    bot_config["model_endpoint_custom"] = endpoint
    save_config(bot_config)
    await interaction.response.send_message(
        f"✅ Custom model endpoint set to **{endpoint}**.", ephemeral=True
    )


# ---------------------------------------------------------------------------
# Slash commands — Chat revival
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


# ---------------------------------------------------------------------------
# Slash commands — Help
# ---------------------------------------------------------------------------

@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 ChatBuddy — Command Reference",
        description="All commands except `/help` and `/set-secret-word` require **Administrator** permissions.",
        color=discord.Color.blurple(),
    )

    embed.add_field(
        name="⚙️ Core Settings",
        value=(
            "`/set-api-key` — Set the Gemini API key\n"
            "`/set-api-context` — Track daily API quota in system prompt\n"
            "`/check-api-quota` — Check the current tracked daily quota\n"
            "`/set-chat-history [limit]` : Set the maximum messages to remember (default 30)\n"
            "`/set-temp` — Set model temperature (0.0 – 2.0)\n"
            "`/set-api-endpoint-gemini` — Set the Gemini model endpoint\n"
            "`/set-api-endpoint-gemma` — Set the Gemma model endpoint\n"
            "`/set-api-key-custom` — Set the API key for a custom (non-Google) model\n"
            "`/set-api-endpoint-custom` — Set the endpoint for a custom model\n"
            "`/set-sys-instruct` — Set the main system prompt\n"
            "`/show-sys-instruct` — Display the full effective system prompt\n"
            "`/set-model-mode` — Switch between `gemini`, `gemma`, and `custom`"
        ),
        inline=False,
    )

    embed.add_field(
        name="🌐 Multimodal & Search",
        value=(
            "`/set-multimodal [true/false]` : Enable Image and Audio analysis\n"
            "`/set-gemini-web-search [true/false]` : Enable internal Gemini Search\n"
            "`/set-duck-search [true/false]` : Enable free Python DuckDuckGo Search"
        ),
        inline=False,
    )

    embed.add_field(
        name="🧠 Soul Memory",
        value=(
            "`/set-soul` — Enable/disable the self-updating soul memory\n"
            "`/show-soul` — View current soul memory\n"
            "`/edit-soul-add-entry` — Add/append a new memory entry manually\n"
            "`/edit-soul-overwrite` — Overwrite an existing memory entry manually\n"
            "`/edit-soul-delete-entry` — Delete a given memory entry manually\n"
            "`/wipe-soul` — Wipe all memory entries immediately\n"
            "`/set-soul-channel` — Set the channel to log soul updates\n"
            "*Note: The bot uses `<!soul-add-new[id]: text>`, `<!soul-update[id]: text>`, `<!soul-override[id]: text>`, or `<!soul-delete[id]>`.*"
        ),
        inline=False,
    )

    embed.add_field(
        name="📝 Dynamic & Game Prompts",
        value=(
            "`/set-dynamic-system-prompt` — Set an extra prompt (appended after main) + enable/disable\n"
            "`/set-word-game` — Set word game rules (`{secret-word}` placeholder) + enable/disable\n"
            "`/set-word-game-selector-prompt` — Set the hidden-turn prompt for word selection\n"
            "`/set-secret-word` — Trigger a hidden turn to pick a new secret word (role-gated)\n"
            "`/set-secret-word-permission` — Grant/revoke a role's access to `/set-secret-word`"
        ),
        inline=False,
    )

    embed.add_field(
        name="🔊 Audio Clip Mode",
        value=(
            "`/set-audio-endpoint` — Set the TTS model\n"
            "`/set-audio-settings` — Choose the voice\n"
            "`/set-audio-mode` — Enable/disable audio clips globally"
        ),
        inline=False,
    )

    embed.add_field(
        name="📺 Channel Settings",
        value=(
            "`/set-allowed-channel` — Whitelist/blacklist a channel\n"
            "`/set-ce` — Enable/disable `[ce]` context cutoff per channel"
        ),
        inline=False,
    )

    embed.add_field(
        name="🧠 Stream of Consciousness (SoC)",
        value=(
            "`/set-soc` — Set thoughts output channel + enable/disable\n"
            "`/set-soc-context` — Enable cross-channel thought context + message count\n\n"
            "Extracts `<my-thoughts>` blocks to a dedicated channel. "
            "`[ce]` works in the SoC channel too."
        ),
        inline=False,
    )

    embed.add_field(
        name="💬 Auto-Chat Mode",
        value=(
            "`/set-auto-chat-mode` — Auto-reply in a channel without needing mentions\n"
            "`/set-auto-idle-message` — Set the message posted when entering idle\n\n"
            "Checks every N seconds. Goes idle if the bot's own message is the latest "
            "for the configured timeout. A mention/reply reactivates it."
        ),
        inline=False,
    )

    embed.add_field(
        name="🔁 Chat Revival",
        value=(
            "`/set-chat-revival` — Configure periodic chat revival + enable/disable\n"
            "`/set-cr-params` — Set active window duration & check interval\n"
            "`/set-cr-leave-msg` — Set the goodbye message after revival expires"
        ),
        inline=False,
    )

    embed.add_field(
        name="⏰ Reminders & Auto-Wake",
        value=(
            "`/setup-reminders` — Enable/disable reminders\n"
            "`/set-reminder-channel` — Set the channel where reminders fire\n"
            "`/set-reminder-log-channel` — Set a log channel for transparency\n"
            "`/add-reminder` — Add a named reminder (dd-mm-yy HH:MM)\n"
            "`/delete-reminder` — Delete a reminder by name\n"
            "`/show-reminders` — Show all scheduled reminders & wake-times\n\n"
            "The bot can also self-manage via hidden tags:\n"
            "`<!add-reminder>`, `<!delete-reminder>`\n"
            "`<!add-auto-wake-time>`, `<!delete-auto-wake-time>`"
        ),
        inline=False,
    )

    embed.add_field(
        name="🤖 Bot-to-Bot Response",
        value=(
            "`/set-respond-to-bot` — Enable/disable replying to other bots\n"
            "`/set-respond-bot-limit` — Stop after N consecutive bot messages (1-9)\n\n"
            "Only affects direct mention/reply. Reminders, auto-chat, revival, "
            "and heartbeat are **not** affected."
        ),
        inline=False,
    )

    embed.add_field(
        name="💓 Heartbeat",
        value=(
            "`/set-heartbeat` — Configure periodic heartbeat (interval, channel, prompt)\n\n"
            "Fires on schedule regardless of activity. Separate from auto-chat "
            "(no idle timer)."
        ),
        inline=False,
    )

    embed.add_field(
        name="🐣 Tamagotchi Minigame",
        value=(
            "`/set-tamagochi-rules` — Set accepted food/drink/entertainment emoji + stat limits\n"
            "`/set-tamagochi-mode` — Enable/disable Tamagotchi mode (rules must be set first)\n"
            "`/set-tamagochi-depletion-rate` — Set how much stats decrease per inference\n"
            "`/set-tamagochi-fill-rate` — Set how much stats increase per emoji consumed\n"
            "`/set-tamagochi-max-consumption` — Limit emoji consumed per input (0 = unlimited)\n"
            "`/show-tamagochi-stats` — View current stats, emoji, and rates\n\n"
            "Stats deplete on every bot inference. Users feed the bot by including "
            "accepted emoji in their messages. A stats footer is appended to every "
            "visible response."
        ),
        inline=False,
    )

    embed.add_field(
        name="💀 Tamagotchi Hardcore Mode",
        value=(
            "`/set-hardcore-sickness-stat` — Set max sickness (death threshold)\n"
            "`/set-hardcore-tamagochi-medicine` — Set medicine emoji + heal amount\n"
            "`/set-hc-sick-threshold` — Set thresholds below which sickness increases\n"
            "`/set-hc-sick-increase` — Set sickness increase per turn per stat\n"
            "`/set-tamagochi-rip-message` — Set custom death message (empty = default)\n"
            "`/set-hardcore-tamagochi-mode` — Enable/disable hardcore (all settings must be configured)\n\n"
            "When stats drop below their thresholds, sickness increases each turn. "
            "Medicine emoji reduce sickness. If sickness reaches max → the Tamagotchi "
            "dies, wiping soul memory, resetting stats, sending `[ce]` to all channels "
            "(including SoC) to wipe context, and posting the death message. "
            "Disabling resets sickness to 0."
        ),
        inline=False,
    )

    embed.add_field(
        name="📊 API Quota Edit",
        value=(
            "`/set-edit-api-current-quota` — Manually correct the current API usage counter\n"
            "Cannot exceed the max quota limit. Requires API context tracking to be enabled."
        ),
        inline=False,
    )

    embed.set_footer(text="Mention me or reply to my messages to chat!")
    await interaction.response.send_message(embed=embed)


# ---------------------------------------------------------------------------
# Dummy HTTP server for Back4app health checks
# ---------------------------------------------------------------------------

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is online")

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
bot.run(TOKEN)
