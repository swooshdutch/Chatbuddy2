"""Shared runtime state for the ChatBuddy app."""

from collections import defaultdict
import os
import random
import secrets

import discord
from discord.ext import commands

from secret_store import load_environment


class Ref:
    """Tiny mutable reference wrapper for shared manager instances."""

    def __init__(self) -> None:
        self.value = None

    def set(self, value) -> None:
        self.value = value

    def clear(self) -> None:
        self.value = None

    def __bool__(self) -> bool:
        return self.value is not None

    def __getattr__(self, name: str):
        if self.value is None:
            raise AttributeError(name)
        return getattr(self.value, name)


load_environment()

TOKEN = os.getenv("DISCORD_TOKEN")
SETUP_API_KEY = os.getenv("API_KEY", "")
SETUP_GEMINI_ENDPOINT = os.getenv("GEMINI_ENDPOINT", "")
SETUP_GEMMA_ENDPOINT = os.getenv("GEMMA_ENDPOINT", "")
SETUP_AUDIO_ENDPOINT = os.getenv("AUDIO_ENDPOINT", "")
SETUP_MAIN_CHAT_CHANNEL = os.getenv("MAIN_CHAT_CHANNEL", "")
SETUP_THOUGHTS_CHANNEL = os.getenv("THOUGHTS_CHANNEL", "")
SETUP_SOUL_CHANNEL = os.getenv("SOUL_CHANNEL", "")
SETUP_SYS_INSTRUCT = os.getenv("SYS_INSTRUCT", "")
SETUP_BOT_OWNER_ID = os.getenv("BOT_OWNER_ID", "")

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is not set. "
        "Copy .env.template to .env and paste your bot token."
    )

if not hasattr(secrets, "randbits"):
    secrets.randbits = random.getrandbits

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

bot_config: dict = {}
revival_manager = Ref()
auto_chat_manager = Ref()
reminder_manager = Ref()
heartbeat_manager = Ref()
tama_manager = Ref()

bot.tama_manager = tama_manager
bot.auto_chat_manager = auto_chat_manager

_generating_channels: set[int] = set()
_pending_messages: dict[int, list] = defaultdict(list)
