"""Common imports used by the refactored bot modules."""

import asyncio
import io
import json
import os
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

from auto_chat import AutoChatManager
from config import load_config, save_config
from gemini_api import build_system_prompt, generate
from heartbeat import HeartbeatManager
from reminders import ReminderManager
from revival import RevivalManager
from secret_store import has_secret, set_secret
from system_prompt_store import (
    DEFAULT_BOT_NAME,
    DEFAULT_BOT_PERSONALITY,
    SYSTEM_PROMPT_TEMPLATE_FILE,
    ensure_system_prompt_template_file,
    get_bot_name,
    get_bot_personality,
    read_system_prompt_template,
    write_system_prompt_template,
)
from utils import (
    chunk_message,
    collect_context_entries,
    format_context,
    resolve_custom_emoji,
    strip_mention,
)

from .runtime import (
    SETUP_API_KEY,
    SETUP_AUDIO_ENDPOINT,
    SETUP_BOT_OWNER_ID,
    SETUP_GEMINI_ENDPOINT,
    SETUP_GEMMA_ENDPOINT,
    SETUP_MAIN_CHAT_CHANNEL,
    SETUP_SOUL_CHANNEL,
    SETUP_SYS_INSTRUCT,
    SETUP_THOUGHTS_CHANNEL,
    TOKEN,
    _generating_channels,
    _pending_messages,
    auto_chat_manager,
    bot,
    bot_config,
    heartbeat_manager,
    reminder_manager,
    revival_manager,
    tama_manager,
)
from .support import (
    _build_tama_view,
    _command_access_check,
    _configured_owner_id,
    _deny_command,
    _format_tama_item_summary,
    _handle_soc_extraction,
    _is_allowed_command_user,
    _is_owner_user,
    _maybe_begin_auto_rest,
    _read_soc_context,
    _register_tama_view,
    _resolve_tama_item_id,
    _send_soul_logs,
    _tama_hatching_active,
)
from .tamagotchi import *  # noqa: F401,F403

__all__ = [name for name in globals() if not name.startswith("__")]
