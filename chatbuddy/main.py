"""Package entrypoint for ChatBuddy."""

from .runtime import TOKEN, bot
from .support import _command_access_check

# Import side-effect modules so events and slash commands register themselves.
from . import events, healthcheck, response_flow  # noqa: F401
from .commands import (  # noqa: F401
    auto_chat,
    bot_controls,
    context,
    core,
    custom_model,
    help,
    reminders,
    revival,
    soul,
    tamagotchi_items,
    tamagotchi_messages,
    tamagotchi_setup,
    tamagotchi_stats,
)


bot.tree.interaction_check = _command_access_check


def main() -> None:
    bot.run(TOKEN)

