"""Discord events and lifecycle helpers."""

from .common import *
from .response_flow import (
    _generate_and_respond,
    _generate_batched_response,
    _is_inline_duck_search_message,
)
# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    bot_config.clear()
    bot_config.update(load_config())
    if ensure_inventory_defaults(bot_config):
        save_config(bot_config)
    if not bot_config.get("bot_owner_id") and SETUP_BOT_OWNER_ID:
        bot_config["bot_owner_id"] = SETUP_BOT_OWNER_ID
        save_config(bot_config)

    revival_manager.set(RevivalManager(bot, bot_config))
    revival_manager.start()

    auto_chat_manager.set(AutoChatManager(bot, bot_config))
    auto_chat_manager.start()

    reminder_manager.set(ReminderManager(bot, bot_config))
    reminder_manager.start()

    heartbeat_manager.set(HeartbeatManager(bot, bot_config))
    heartbeat_manager.start()

    tama_manager.set(TamagotchiManager(bot, bot_config))
    tama_manager.start()
    bot.tama_manager = tama_manager
    _register_tama_view()

    try:
        synced = await bot.tree.sync()
        print(f"[ChatBuddy] Online as {bot.user} — synced {len(synced)} command(s)")
    except Exception as e:
        print(f"[ChatBuddy] Failed to sync commands: {e}")


def _restart_background_managers():
    if revival_manager:
        revival_manager.start()
    if auto_chat_manager:
        auto_chat_manager.start()
    if reminder_manager:
        reminder_manager.start()
    if heartbeat_manager:
        heartbeat_manager.start()
    if tama_manager:
        tama_manager.start()


def _ensure_tama_manager() -> TamagotchiManager:
    if not tama_manager:
        tama_manager.set(TamagotchiManager(bot, bot_config))
        bot.tama_manager = tama_manager
        _register_tama_view()
    tama_manager.start()
    return tama_manager.value


async def _run_tama_fresh_start(
    channel_id: int | str | None = None,
    *,
    fallback_channel_ids: list[int | str] | tuple[int | str, ...] | None = None,
) -> dict:
    manager = _ensure_tama_manager()
    return await manager.start_egg_cycle(
        channel_id=channel_id,
        wipe_soul=True,
        reset_stats=True,
        send_ce=True,
        fallback_channel_ids=fallback_channel_ids,
    )


async def _run_backend_setup(
    interaction: discord.Interaction,
    *,
    model_mode: str,
    endpoint_env_name: str,
    endpoint_value: str,
) -> None:
    missing = []
    if not SETUP_API_KEY:
        missing.append("API_KEY")
    if not endpoint_value:
        missing.append(endpoint_env_name)
    if not SETUP_MAIN_CHAT_CHANNEL:
        missing.append("MAIN_CHAT_CHANNEL")
    if not _configured_owner_id():
        missing.append("BOT_OWNER_ID")

    if missing:
        await interaction.response.send_message(
            f"Missing setup env vars: {', '.join(missing)}",
            ephemeral=True,
        )
        return

    try:
        await interaction.response.defer(ephemeral=True)
    except discord.NotFound:
        print("[ChatBuddy] setup interaction expired before it could be deferred.")
        return
    try:
        allowed_channels = dict(bot_config.get("allowed_channels", {}))
        allowed_channels[str(SETUP_MAIN_CHAT_CHANNEL)] = True
        ce_channels = dict(bot_config.get("ce_channels", {}))
        ce_channels[str(SETUP_MAIN_CHAT_CHANNEL)] = True

        set_secret("api_key", SETUP_API_KEY)
        bot_config["model_mode"] = model_mode
        bot_config["model_endpoint"] = endpoint_value
        if model_mode == "gemma":
            bot_config["model_endpoint_gemma"] = endpoint_value
        else:
            bot_config["model_endpoint_gemini"] = endpoint_value
        bot_config["audio_endpoint"] = SETUP_AUDIO_ENDPOINT
        bot_config["audio_enabled"] = bool(SETUP_AUDIO_ENDPOINT)
        bot_config["multimodal_enabled"] = True
        bot_config["duck_search_enabled"] = True
        if SETUP_SYS_INSTRUCT:
            write_system_prompt_template(SETUP_SYS_INSTRUCT)
        else:
            ensure_system_prompt_template_file()
        bot_config["allowed_channels"] = allowed_channels
        bot_config["ce_channels"] = ce_channels
        bot_config["soc_channel_id"] = str(SETUP_THOUGHTS_CHANNEL) if SETUP_THOUGHTS_CHANNEL else None
        bot_config["soc_enabled"] = bool(SETUP_THOUGHTS_CHANNEL)
        bot_config["soc_context_enabled"] = bool(SETUP_THOUGHTS_CHANNEL)
        bot_config["soul_channel_id"] = str(SETUP_SOUL_CHANNEL) if SETUP_SOUL_CHANNEL else ""
        bot_config["soul_channel_enabled"] = bool(SETUP_SOUL_CHANNEL)
        bot_config["soul_enabled"] = True
        bot_config["soul_limit"] = 10000
        bot_config["tama_enabled"] = True
        bot_config["heartbeat_enabled"] = False
        bot_config["auto_chat_enabled"] = False
        bot_config["bot_owner_id"] = _configured_owner_id()
        bot_config["reminders_enabled"] = True
        bot_config["reminders_channel_id"] = str(SETUP_MAIN_CHAT_CHANNEL)
        bot_config["main_chat_channel_id"] = str(SETUP_MAIN_CHAT_CHANNEL)

        save_config(bot_config)
        _restart_background_managers()
        fresh_start = await _run_tama_fresh_start(
            channel_id=SETUP_MAIN_CHAT_CHANNEL,
            fallback_channel_ids=[interaction.channel_id],
        )
        if not fresh_start.get("hatch_message_posted"):
            raise RuntimeError(
                "Fresh start did not post a hatch message. "
                f"Target channel: {fresh_start.get('hatch_channel_id') or '(missing)'}. "
                f"Reason: {fresh_start.get('hatch_failure_reason') or 'unknown'}"
            )

        hatch_channel_id = str(fresh_start.get("hatch_channel_id") or "").strip()
        used_fallback_channel = bool(interaction.channel_id) and hatch_channel_id == str(interaction.channel_id)
        mode_label = "Gemma" if model_mode == "gemma" else "Gemini"
        await interaction.followup.send(
            f"Setup complete. Backend settings were applied in **{mode_label}** mode, the soul was wiped, `[ce]` was sent, "
            + (
                "and a new egg is now hatching in this channel because the configured main channel could not be used."
                if used_fallback_channel and hatch_channel_id != str(SETUP_MAIN_CHAT_CHANNEL)
                else "and a new egg is now hatching."
            ),
            ephemeral=True,
        )
    except Exception as e:
        print(f"[ChatBuddy] /setup-bot failed: {e}")
        await interaction.followup.send(
            f"Setup failed: `{type(e).__name__}: {e}`",
            ephemeral=True,
        )

@bot.command()
@commands.has_permissions(administrator=True)
async def purgecommands(ctx):
    """Nuke all guild-specific slash commands and resync global ones to clear 'ghosts'."""
    if not _is_allowed_command_user(ctx.author.id):
        await ctx.send("You are not allowed to use bot setup commands.")
        return
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

    if auto_chat_manager and auto_chat_manager.handles_channel(message.channel.id):
        if (is_mentioned or is_reply_to_bot) and not message.author.bot:
            auto_chat_manager.note_activity("mention/reply")
        await bot.process_commands(message)
        return

    if not is_mentioned and not is_reply_to_bot:
        await bot.process_commands(message)
        return

    # â”€â”€ Bot-to-bot response gate (only for mention/reply) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # Let inline Duck search stay in the normal chat flow instead of the legacy prefix-command parser.
    if not _is_inline_duck_search_message(message):
        await bot.process_commands(message)

    # â”€â”€ Message batching: queue if already generating â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ch_id = message.channel.id
    if ch_id in _generating_channels:
        # Another generation is in progress â€” queue this message
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


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error





