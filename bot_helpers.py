"""
bot_helpers.py - Shared helpers extracted from bot.py.
"""

import discord

from tamagotchi import (
    BUTTON_STYLE_LABELS,
    TamagotchiView,
    get_inventory_items,
    inventory_item_id_from_name,
    is_hatching,
    should_auto_sleep,
)
from utils import chunk_message, extract_thoughts


async def resolve_channel(bot_ref, channel_id: int | str | None):
    """Return a cached channel if possible, otherwise fetch it from Discord."""
    if not channel_id:
        return None
    try:
        numeric_id = int(channel_id)
    except (TypeError, ValueError):
        return None

    channel = bot_ref.get_channel(numeric_id)
    if channel is not None:
        return channel

    try:
        return await bot_ref.fetch_channel(numeric_id)
    except Exception:
        return None


async def read_soc_context(bot_ref, config: dict) -> str:
    """Read SoC channel messages and return formatted context string (or '')."""
    soc_context_enabled = config.get("soc_context_enabled", False)
    soc_channel_id = config.get("soc_channel_id")
    if not soc_context_enabled or not soc_channel_id:
        return ""

    soc_count = config.get("soc_context_count", 10)
    soc_channel = await resolve_channel(bot_ref, soc_channel_id)
    if soc_channel is None:
        return ""

    soc_messages = []
    try:
        async for msg in soc_channel.history(limit=soc_count):
            soc_messages.append(msg)
    except Exception as e:
        print(f"[SoC] Failed to read context history: {e}")
        return ""
    soc_messages.reverse()

    ce_idx = None
    for i, message in enumerate(soc_messages):
        if message.content.strip().lower() == "[ce]":
            ce_idx = i
    if ce_idx is not None:
        soc_messages = soc_messages[ce_idx + 1:]

    if not soc_messages:
        return ""

    soc_lines = []
    for message in soc_messages:
        ts = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
        soc_lines.append(f"[{ts}] {message.content}")
    return (
        "\n[YOUR PREVIOUS THOUGHTS - internal notes from earlier turns. These are not new user messages and should not be counted as extra repeats of the same event. Use them only as background memory.]\n"
        + "\n".join(soc_lines)
        + "\n[END YOUR PREVIOUS THOUGHTS]\n"
    )


async def handle_soc_extraction(response_text: str, bot_ref, config: dict) -> str:
    """Extract thoughts, send them to the SoC channel, and return clean text."""
    soc_enabled = config.get("soc_enabled", False)
    soc_channel_id = config.get("soc_channel_id")
    clean_text, thoughts_text = extract_thoughts(response_text)
    if thoughts_text and soc_enabled and soc_channel_id:
        try:
            thought_channel = await resolve_channel(bot_ref, soc_channel_id)
            if thought_channel is not None:
                for chunk in chunk_message(thoughts_text):
                    await thought_channel.send(chunk)
        except Exception as e:
            print(f"[SoC] Failed to post extracted thoughts: {e}")
    return clean_text


async def send_soul_logs(bot_ref, config: dict, soul_logs: list[str]) -> None:
    """Send soul update logs to the configured soul channel when enabled."""
    if not soul_logs or not config.get("soul_channel_enabled"):
        return

    soul_channel_id = str(config.get("soul_channel_id", "") or "").strip()
    if not soul_channel_id:
        return

    soul_channel = await resolve_channel(bot_ref, soul_channel_id)
    if soul_channel is None:
        print(f"[Soul] Could not resolve configured soul channel {soul_channel_id}.")
        return

    joined_logs = "\n".join(log for log in soul_logs if log)
    prefix = "**Soul Updates:**\n"
    for log_chunk in chunk_message(joined_logs, limit=1900):
        try:
            await soul_channel.send(f"{prefix}{log_chunk}")
        except Exception as e:
            print(f"[Soul] Failed to send soul logs: {e}")
            return


def build_tama_view(bot_config: dict, tama_manager) -> TamagotchiView | None:
    if bot_config.get("tama_enabled", False) and tama_manager:
        return TamagotchiView(bot_config, tama_manager)
    return None


def maybe_begin_auto_rest(bot_config: dict, tama_manager, channel_id: int | str | None) -> bool:
    if not (bot_config.get("tama_enabled", False) and tama_manager):
        return False
    if not should_auto_sleep(bot_config):
        return False
    tama_manager.begin_rest(channel_id)
    return True


def format_tama_item_summary(item: dict) -> str:
    stock = "unlimited" if item.get("is_unlimited") else f"x{item.get('amount', 0)}"
    color_name = BUTTON_STYLE_LABELS.get(
        item.get("button_style", "secondary"),
        item.get("button_style", "secondary"),
    )
    parts = [
        f"{item.get('emoji', '')} **{item.get('name', item.get('id', 'item'))}** "
        f"(`{item.get('id', '')}`) - {item.get('item_type', 'food')}, "
        f"fill x{item.get('multiplier', 1.0)}, energy x{item.get('energy_multiplier', 1.0)}, "
        f"{stock}, {color_name} button"
    ]
    energy_delta = float(item.get("energy_delta", 0.0) or 0.0)
    if energy_delta:
        parts.append(f"energy {energy_delta:+g}")
    happiness_delta = float(item.get("happiness_delta", 0.0) or 0.0)
    if happiness_delta:
        parts.append(f"happiness {happiness_delta:+g}")
    if item.get("lucky_gift_prize"):
        parts.append("lucky-gift prize")
    if not item.get("store_in_inventory", True):
        parts.append("instant-effect reward")
    return ", ".join(parts)


def resolve_tama_item_id(bot_config: dict, name_or_id: str) -> str | None:
    needle = inventory_item_id_from_name(name_or_id)
    for item in get_inventory_items(bot_config, visible_only=False):
        if item["id"] == needle or item["name"].strip().lower() == name_or_id.strip().lower():
            return item["id"]
    return None


def tama_hatching_active(bot_config: dict, tama_manager) -> bool:
    return bool(bot_config.get("tama_enabled", False)) and (
        (tama_manager.hatching if tama_manager else False) or is_hatching(bot_config)
    )


def configured_owner_id(bot_config: dict, setup_bot_owner_id: str) -> str:
    return str(bot_config.get("bot_owner_id") or setup_bot_owner_id or "").strip()


def allowed_command_ids(bot_config: dict, setup_bot_owner_id: str) -> set[str]:
    ids = {
        str(value).strip()
        for value in bot_config.get("command_allowed_user_ids", [])
        if str(value).strip()
    }
    owner_id = configured_owner_id(bot_config, setup_bot_owner_id)
    if owner_id:
        ids.add(owner_id)
    return ids


def is_allowed_command_user(bot_config: dict, setup_bot_owner_id: str, user_id: int | str) -> bool:
    return str(user_id) in allowed_command_ids(bot_config, setup_bot_owner_id)


def is_owner_user(bot_config: dict, setup_bot_owner_id: str, user_id: int | str) -> bool:
    owner_id = configured_owner_id(bot_config, setup_bot_owner_id)
    return bool(owner_id) and str(user_id) == owner_id


async def deny_command(interaction: discord.Interaction) -> None:
    message = "You are not allowed to use bot setup commands."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def command_access_check(interaction: discord.Interaction, bot_config: dict, setup_bot_owner_id: str) -> bool:
    command_name = getattr(getattr(interaction, "command", None), "name", None)
    if not command_name and isinstance(getattr(interaction, "data", None), dict):
        command_name = interaction.data.get("name")
    if command_name == "help":
        return True
    if is_allowed_command_user(bot_config, setup_bot_owner_id, interaction.user.id):
        return True
    await deny_command(interaction)
    return False
