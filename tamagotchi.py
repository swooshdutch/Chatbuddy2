"""
tamagotchi.py — Tamagotchi minigame logic for ChatBuddy.

Handles stat depletion, emoji consumption from user input, footer
generation, and system-prompt injection.  All stat changes are managed
here so the LLM cannot cheat.
"""

import re
import emoji as emoji_lib  # python-emoji library for robust detection
from config import save_config


# ── Validation helpers ────────────────────────────────────────────────────────

def validate_rate(value: float) -> bool:
    """Return True if *value* has at most 2 decimal places and is <= 99."""
    if value < 0 or value > 99:
        return False
    # Check decimal places: multiply by 100, see if it's (close to) an integer
    scaled = round(value * 100, 6)
    return abs(scaled - round(scaled)) < 1e-6


def parse_emoji_list(text: str) -> list[str]:
    """
    Extract individual emoji from a user-provided string.

    Accepts comma-separated or space-separated input.  Uses the `emoji`
    library so both Unicode emoji (🍔) and shortcodes are handled.
    Discord custom emoji (<:name:id> / <a:name:id>) are also captured.
    """
    found: list[str] = []

    # 1) Capture Discord custom emoji  <:name:id> / <a:name:id>
    discord_pattern = re.compile(r"<a?:\w+:\d+>")
    for m in discord_pattern.finditer(text):
        found.append(m.group(0))
    # Remove them so they don't interfere with Unicode extraction
    text = discord_pattern.sub("", text)

    # 2) Extract Unicode emoji
    for ch in text:
        if emoji_lib.is_emoji(ch):
            found.append(ch)

    # Also handle multi-char emoji sequences (flags, skin tones, ZWJ sequences)
    for em_data in emoji_lib.emoji_list(text):
        em = em_data["emoji"]
        if em not in found:
            found.append(em)

    return found


# ── Stat management ───────────────────────────────────────────────────────────

def deplete_stats(config: dict) -> None:
    """
    Subtract depletion rates from current stats, clamping at 0.
    Called after every generate() call (any inference path).
    """
    if not config.get("tamagotchi_enabled", False):
        return

    config["tamagotchi_hunger"] = max(
        0.0, round(config.get("tamagotchi_hunger", 0) - config.get("tamagotchi_depletion_food", 1.0), 2)
    )
    config["tamagotchi_thirst"] = max(
        0.0, round(config.get("tamagotchi_thirst", 0) - config.get("tamagotchi_depletion_thirst", 1.0), 2)
    )
    config["tamagotchi_happiness"] = max(
        0.0, round(config.get("tamagotchi_happiness", 0) - config.get("tamagotchi_depletion_happiness", 1.0), 2)
    )
    save_config(config)


def consume_emoji(text: str, config: dict) -> dict[str, int]:
    """
    Scan *text* for accepted Tamagotchi emoji and increase stats accordingly.

    Only call this with USER-authored text (not bot output).
    Respects ``tamagotchi_max_consumption`` — if non-zero, at most that many
    emoji are consumed from *text*.  Returns a dict of counts per category.
    """
    if not config.get("tamagotchi_enabled", False):
        return {}

    food_set = set(config.get("tamagotchi_food_emoji", []))
    drink_set = set(config.get("tamagotchi_drink_emoji", []))
    entertainment_set = set(config.get("tamagotchi_entertainment_emoji", []))

    max_consumption = config.get("tamagotchi_max_consumption", 0)
    fill_food = config.get("tamagotchi_fill_food", 1.0)
    fill_thirst = config.get("tamagotchi_fill_thirst", 1.0)
    fill_happiness = config.get("tamagotchi_fill_happiness", 1.0)

    # Collect all emoji in order of appearance
    emoji_in_text: list[str] = []

    # Discord custom emoji
    discord_pattern = re.compile(r"<a?:\w+:\d+>")
    # Build a position-ordered list of (position, emoji_str)
    ordered: list[tuple[int, str]] = []
    for m in discord_pattern.finditer(text):
        ordered.append((m.start(), m.group(0)))

    # Remove discord emoji before scanning Unicode
    clean_text = discord_pattern.sub("", text)

    # Unicode emoji — use emoji_list for position-aware extraction
    for em_data in emoji_lib.emoji_list(clean_text):
        ordered.append((em_data["match_start"], em_data["emoji"]))

    # Sort by position so we process left-to-right
    ordered.sort(key=lambda x: x[0])
    emoji_in_text = [e for _, e in ordered]

    # Apply max_consumption limit
    if max_consumption > 0:
        emoji_in_text = emoji_in_text[:max_consumption]

    counts = {"food": 0, "drink": 0, "entertainment": 0}
    for em in emoji_in_text:
        if em in food_set:
            config["tamagotchi_hunger"] = min(
                config.get("tamagotchi_max_hunger", 10),
                round(config.get("tamagotchi_hunger", 0) + fill_food, 2),
            )
            counts["food"] += 1
        elif em in drink_set:
            config["tamagotchi_thirst"] = min(
                config.get("tamagotchi_max_thirst", 10),
                round(config.get("tamagotchi_thirst", 0) + fill_thirst, 2),
            )
            counts["drink"] += 1
        elif em in entertainment_set:
            config["tamagotchi_happiness"] = min(
                config.get("tamagotchi_max_happiness", 10),
                round(config.get("tamagotchi_happiness", 0) + fill_happiness, 2),
            )
            counts["entertainment"] += 1

    if any(counts.values()):
        save_config(config)

    return counts


# ── Footer / prompt helpers ───────────────────────────────────────────────────

def _format_stat(val: float) -> str:
    """Format a stat value: show integer if whole, otherwise up to 2 decimals."""
    if val == int(val):
        return str(int(val))
    return f"{val:.2f}".rstrip("0").rstrip(".")


def build_tamagotchi_footer(config: dict) -> str:
    """
    Return the small-text stats footer, e.g.
        -# 🍔 5/10 | 💧 3.5/10 | 😊 7/10

    Returns '' if tamagotchi mode is disabled.
    """
    if not config.get("tamagotchi_enabled", False):
        return ""

    hunger = config.get("tamagotchi_hunger", 0)
    thirst = config.get("tamagotchi_thirst", 0)
    happiness = config.get("tamagotchi_happiness", 0)
    max_h = config.get("tamagotchi_max_hunger", 10)
    max_t = config.get("tamagotchi_max_thirst", 10)
    max_hp = config.get("tamagotchi_max_happiness", 10)

    return (
        f"-# 🍔 {_format_stat(hunger)}/{max_h} "
        f"| 💧 {_format_stat(thirst)}/{max_t} "
        f"| 😊 {_format_stat(happiness)}/{max_hp}"
    )


def build_tamagotchi_system_prompt(config: dict) -> str:
    """
    Build the system-prompt injection describing current Tamagotchi state.
    Returns '' if tamagotchi mode is disabled.
    """
    if not config.get("tamagotchi_enabled", False):
        return ""

    hunger = config.get("tamagotchi_hunger", 0)
    thirst = config.get("tamagotchi_thirst", 0)
    happiness = config.get("tamagotchi_happiness", 0)
    max_h = config.get("tamagotchi_max_hunger", 10)
    max_t = config.get("tamagotchi_max_thirst", 10)
    max_hp = config.get("tamagotchi_max_happiness", 10)

    food_emoji = " ".join(config.get("tamagotchi_food_emoji", []))
    drink_emoji = " ".join(config.get("tamagotchi_drink_emoji", []))
    ent_emoji = " ".join(config.get("tamagotchi_entertainment_emoji", []))

    return (
        "[TAMAGOTCHI STATUS — Your virtual pet stats. "
        "These are managed by script; you cannot change them yourself.\n"
        f"Hunger: {_format_stat(hunger)}/{max_h}\n"
        f"Thirst: {_format_stat(thirst)}/{max_t}\n"
        f"Happiness: {_format_stat(happiness)}/{max_hp}\n"
        f"Accepted food emoji: {food_emoji or '(none)'}\n"
        f"Accepted drink emoji: {drink_emoji or '(none)'}\n"
        f"Accepted entertainment emoji: {ent_emoji or '(none)'}\n"
        "Users can feed you by including these emoji in their messages. "
        "Your stats decrease each time you respond.]"
    )
