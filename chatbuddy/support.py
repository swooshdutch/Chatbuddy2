"""Runtime-aware helper wrappers shared across modules."""

import discord

from bot_helpers import (
    build_tama_view as _build_tama_view_impl,
    command_access_check,
    configured_owner_id as _configured_owner_id_impl,
    deny_command as _deny_command_impl,
    format_tama_item_summary as _format_tama_item_summary_impl,
    handle_soc_extraction as _handle_soc_extraction_impl,
    is_allowed_command_user as _is_allowed_command_user_impl,
    is_owner_user as _is_owner_user_impl,
    maybe_begin_auto_rest as _maybe_begin_auto_rest_impl,
    read_soc_context as _read_soc_context_impl,
    send_soul_logs as _send_soul_logs_impl,
    resolve_tama_item_id as _resolve_tama_item_id_impl,
    tama_hatching_active as _tama_hatching_active_impl,
)

from .runtime import SETUP_BOT_OWNER_ID, bot, bot_config, tama_manager
from .tamagotchi import TamagotchiView

_tama_view_registered = False


async def _read_soc_context(bot_ref, config: dict) -> str:
    return await _read_soc_context_impl(bot_ref, config)


async def _handle_soc_extraction(response_text: str, bot_ref, config: dict) -> str:
    return await _handle_soc_extraction_impl(response_text, bot_ref, config)


async def _send_soul_logs(bot_ref, config: dict, soul_logs: list[str]) -> None:
    await _send_soul_logs_impl(bot_ref, config, soul_logs)


def _build_tama_view():
    return _build_tama_view_impl(bot_config, tama_manager)


def _maybe_begin_auto_rest(channel_id: int | str | None) -> bool:
    return _maybe_begin_auto_rest_impl(bot_config, tama_manager, channel_id)


def _format_tama_item_summary(item: dict) -> str:
    return _format_tama_item_summary_impl(item)


def _resolve_tama_item_id(name_or_id: str) -> str | None:
    return _resolve_tama_item_id_impl(bot_config, name_or_id)


def _tama_hatching_active() -> bool:
    return _tama_hatching_active_impl(bot_config, tama_manager)


def _configured_owner_id() -> str:
    return _configured_owner_id_impl(bot_config, SETUP_BOT_OWNER_ID)


def _is_allowed_command_user(user_id: int | str) -> bool:
    return _is_allowed_command_user_impl(bot_config, SETUP_BOT_OWNER_ID, user_id)


def _is_owner_user(user_id: int | str) -> bool:
    return _is_owner_user_impl(bot_config, SETUP_BOT_OWNER_ID, user_id)


async def _deny_command(interaction: discord.Interaction) -> None:
    await _deny_command_impl(interaction)


async def _command_access_check(interaction: discord.Interaction) -> bool:
    return await command_access_check(interaction, bot_config, SETUP_BOT_OWNER_ID)


def _register_tama_view() -> None:
    global _tama_view_registered
    if (
        _tama_view_registered
        or not tama_manager
        or not bot_config.get("tama_enabled", False)
    ):
        return
    bot.add_view(TamagotchiView(bot_config, tama_manager))
    _tama_view_registered = True
