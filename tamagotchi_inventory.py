"""
tamagotchi_inventory.py - Inventory defaults and helpers for ChatBuddy's Tamagotchi.
"""

import re

import discord

DEFAULT_TAMA_INVENTORY_ITEMS = {
    "unlimited_hamburger": {
        "name": "Hamburger",
        "emoji": "🍔",
        "item_type": "food",
        "multiplier": 1.0,
        "energy_multiplier": 1.0,
        "happiness_delta": 0.0,
        "button_style": "success",
        "amount": -1,
        "lucky_gift_prize": False,
        "store_in_inventory": True,
    },
    "unlimited_water": {
        "name": "Cup of Water",
        "emoji": "🥤",
        "item_type": "drink",
        "multiplier": 1.0,
        "energy_multiplier": 1.0,
        "happiness_delta": 0.0,
        "button_style": "primary",
        "amount": -1,
        "lucky_gift_prize": False,
        "store_in_inventory": True,
    },
    "teddy_bear": {
        "name": "Teddy Bear",
        "emoji": "🧸",
        "item_type": "misc",
        "multiplier": 0.0,
        "energy_multiplier": 0.0,
        "happiness_delta": 10.0,
        "button_style": "success",
        "amount": 0,
        "lucky_gift_prize": True,
        "store_in_inventory": True,
    },
    "sushi": {
        "name": "Sushi",
        "emoji": "🍣",
        "item_type": "food",
        "multiplier": 2.0,
        "energy_multiplier": 2.0,
        "happiness_delta": 0.0,
        "button_style": "primary",
        "amount": 0,
        "lucky_gift_prize": True,
        "store_in_inventory": True,
    },
    "meat_on_bone": {
        "name": "Meat on Bone",
        "emoji": "🍖",
        "item_type": "food",
        "multiplier": 3.0,
        "energy_multiplier": 3.0,
        "happiness_delta": 0.0,
        "button_style": "danger",
        "amount": 0,
        "lucky_gift_prize": True,
        "store_in_inventory": True,
    },
    "lump_of_coal": {
        "name": "Lump of Coal",
        "emoji": "⚫",
        "item_type": "misc",
        "multiplier": 0.0,
        "energy_multiplier": 0.0,
        "happiness_delta": -10.0,
        "button_style": "secondary",
        "amount": 0,
        "lucky_gift_prize": True,
        "store_in_inventory": False,
    },
}
TAMA_INVENTORY_DEFAULTS_VERSION = 5

BUTTON_STYLE_BY_NAME = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}

BUTTON_STYLE_LABELS = {
    "primary": "blue",
    "secondary": "gray",
    "success": "green",
    "danger": "red",
}


def inventory_item_id_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug[:48] or "item"


def ensure_inventory_defaults(config: dict) -> bool:
    items = config.get("tama_inventory_items")
    if not isinstance(items, dict):
        items = {}
        config["tama_inventory_items"] = items

    initialized = bool(config.get("tama_inventory_initialized", False))
    defaults_version = int(config.get("tama_inventory_defaults_version", 0) or 0)

    changed = False
    if not initialized or defaults_version < TAMA_INVENTORY_DEFAULTS_VERSION:
        for item_id, defaults in DEFAULT_TAMA_INVENTORY_ITEMS.items():
            stored = items.get(item_id)
            if not isinstance(stored, dict):
                items[item_id] = dict(defaults)
                changed = True
                continue
            for key, value in defaults.items():
                if key not in stored:
                    stored[key] = value
                    changed = True
        config["tama_inventory_initialized"] = True
        config["tama_inventory_defaults_version"] = TAMA_INVENTORY_DEFAULTS_VERSION
        changed = True

    config["tama_inventory_items"] = items
    return changed


def _coerce_item_amount(value) -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return 0
    return amount if amount < 0 else max(0, amount)


def _normalize_inventory_item(item_id: str, raw_item: dict) -> dict:
    item_type = str(raw_item.get("item_type", "food")).strip().lower()
    if item_type not in {"food", "drink", "misc"}:
        item_type = "food"

    button_style = str(raw_item.get("button_style", "secondary")).strip().lower()
    if button_style not in BUTTON_STYLE_BY_NAME:
        button_style = "secondary"

    multiplier = max(0.0, float(raw_item.get("multiplier", 1.0) or 0.0))
    energy_multiplier = max(0.0, float(raw_item.get("energy_multiplier", 1.0) or 0.0))
    happiness_delta = round(float(raw_item.get("happiness_delta", 0.0) or 0.0), 2)
    amount = _coerce_item_amount(raw_item.get("amount", 0))
    default_emoji = "🍔" if item_type == "food" else ("🥤" if item_type == "drink" else "🎁")
    emoji = str(raw_item.get("emoji", default_emoji)).strip() or default_emoji

    return {
        "id": item_id,
        "name": str(raw_item.get("name", item_id)).strip() or item_id,
        "emoji": emoji,
        "item_type": item_type,
        "multiplier": multiplier,
        "energy_multiplier": energy_multiplier,
        "happiness_delta": happiness_delta,
        "button_style": button_style,
        "amount": amount,
        "is_unlimited": amount < 0,
        "stock_text": "∞" if amount < 0 else str(amount),
        "lucky_gift_prize": bool(raw_item.get("lucky_gift_prize", False)),
        "store_in_inventory": bool(raw_item.get("store_in_inventory", True)),
    }


def get_inventory_items(
    config: dict,
    *,
    visible_only: bool = False,
    item_type: str | None = None,
) -> list[dict]:
    ensure_inventory_defaults(config)
    items: list[dict] = []
    for item_id, raw_item in config.get("tama_inventory_items", {}).items():
        if not isinstance(raw_item, dict):
            continue
        item = _normalize_inventory_item(item_id, raw_item)
        if item_type and item["item_type"] != item_type:
            continue
        if visible_only and not (item["is_unlimited"] or item["amount"] > 0):
            continue
        items.append(item)
    items.sort(key=lambda item: (item["item_type"], item["name"].lower(), item["id"]))
    return items


def get_inventory_item(config: dict, item_id: str) -> dict | None:
    raw_item = config.get("tama_inventory_items", {}).get(item_id)
    if not isinstance(raw_item, dict):
        return None
    return _normalize_inventory_item(item_id, raw_item)


def inventory_button_style(item: dict) -> discord.ButtonStyle:
    return BUTTON_STYLE_BY_NAME.get(item.get("button_style", "secondary"), discord.ButtonStyle.secondary)


def inventory_message_text(config: dict) -> str:
    visible_items = get_inventory_items(config, visible_only=True)
    if not visible_items:
        return "Inventory: (empty)"
    details = [f"{item['emoji']} {item['name']} x{item['stock_text']}" for item in visible_items]
    return "Inventory: " + ", ".join(details)
