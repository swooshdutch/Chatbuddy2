"""
tamagotchi.py — Tamagotchi minigame logic for ChatBuddy.

Handles stat depletion, emoji consumption from user input, footer
generation, system-prompt injection, and hardcore-mode sickness.
All stat changes are managed here so the LLM cannot cheat.
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


# ── Death mechanic (hardcore mode) ────────────────────────────────────────────

def trigger_death(config: dict) -> str:
    """
    The Tamagotchi has died!  Wipe soul.md, reset all stats to max,
    reset sickness to 0.  Returns the death message string.
    """
    # Wipe soul.md
    try:
        with open("soul.md", "w", encoding="utf-8") as f:
            f.write("{}")
        print("[Tamagotchi] DEATH — soul.md wiped.")
    except Exception as e:
        print(f"[Tamagotchi] DEATH — Failed to wipe soul.md: {e}")

    # Reset stats to max
    config["tamagotchi_hunger"] = float(config.get("tamagotchi_max_hunger", 10))
    config["tamagotchi_thirst"] = float(config.get("tamagotchi_max_thirst", 10))
    config["tamagotchi_happiness"] = float(config.get("tamagotchi_max_happiness", 10))
    config["tamagotchi_sickness"] = 0.0
    save_config(config)

    # Use custom rip message or default
    custom_msg = config.get("tamagotchi_rip_message", "").strip()
    if custom_msg:
        return custom_msg
    return (
        "💀 **The Tamagotchi has died!** 💀\n"
        "Its soul has been wiped clean… all memories are gone.\n"
        "Stats have been reset. Take better care of it this time!"
    )


async def broadcast_death(bot, config: dict) -> None:
    """
    After death, send [ce] to every allowed channel and the SoC channel
    to wipe all context.  Called by the caller that detected death.
    """
    # Gather all channel IDs to send [ce] to
    channel_ids: set[int] = set()

    # All allowed (whitelisted) channels
    allowed = config.get("allowed_channels", {})
    for ch_id_str, enabled in allowed.items():
        if enabled:
            try:
                channel_ids.add(int(ch_id_str))
            except (ValueError, TypeError):
                pass

    # SoC (thoughts) channel
    if config.get("soc_enabled", False):
        soc_id = config.get("soc_channel_id")
        if soc_id:
            try:
                channel_ids.add(int(soc_id))
            except (ValueError, TypeError):
                pass

    # Send [ce] to each channel
    for ch_id in channel_ids:
        ch = bot.get_channel(ch_id)
        if ch is not None:
            try:
                await ch.send("[ce]")
            except Exception as e:
                print(f"[Tamagotchi] Failed to send [ce] to channel {ch_id}: {e}")


# ── Stat management ───────────────────────────────────────────────────────────

def deplete_stats(config: dict) -> str | None:
    """
    Subtract depletion rates from current stats, clamping at 0.
    Called after every generate() call (any inference path).

    If hardcore mode is enabled, also evaluates sickness increases
    based on thresholds.  If sickness reaches max → triggers death.

    Returns:
        None  — normal operation
        str   — death message (caller must post this in the channel)
    """
    if not config.get("tamagotchi_enabled", False):
        return None

    config["tamagotchi_hunger"] = max(
        0.0, round(config.get("tamagotchi_hunger", 0) - config.get("tamagotchi_depletion_food", 1.0), 2)
    )
    config["tamagotchi_thirst"] = max(
        0.0, round(config.get("tamagotchi_thirst", 0) - config.get("tamagotchi_depletion_thirst", 1.0), 2)
    )
    config["tamagotchi_happiness"] = max(
        0.0, round(config.get("tamagotchi_happiness", 0) - config.get("tamagotchi_depletion_happiness", 1.0), 2)
    )

    # ── Hardcore sickness logic ───────────────────────────────────────
    death_msg = None
    if config.get("tamagotchi_hardcore_enabled", False):
        sickness = config.get("tamagotchi_sickness", 0.0)

        # Check each stat vs threshold — add sickness for each below
        hunger = config.get("tamagotchi_hunger", 0)
        thirst = config.get("tamagotchi_thirst", 0)
        happiness = config.get("tamagotchi_happiness", 0)

        thresh_food = config.get("tamagotchi_sickness_threshold_food", 2.0)
        thresh_thirst = config.get("tamagotchi_sickness_threshold_thirst", 2.0)
        thresh_happiness = config.get("tamagotchi_sickness_threshold_happiness", 2.0)

        inc_food = config.get("tamagotchi_sickness_increase_food", 1.0)
        inc_thirst = config.get("tamagotchi_sickness_increase_thirst", 1.0)
        inc_happiness = config.get("tamagotchi_sickness_increase_happiness", 1.0)

        if hunger < thresh_food:
            sickness = round(sickness + inc_food, 2)
        if thirst < thresh_thirst:
            sickness = round(sickness + inc_thirst, 2)
        if happiness < thresh_happiness:
            sickness = round(sickness + inc_happiness, 2)

        max_sickness = config.get("tamagotchi_max_sickness", 10)
        config["tamagotchi_sickness"] = min(sickness, float(max_sickness))

        # Check for death
        if config["tamagotchi_sickness"] >= max_sickness:
            death_msg = trigger_death(config)
            save_config(config)
            return death_msg

    save_config(config)
    return death_msg


def consume_emoji(text: str, config: dict) -> dict[str, int]:
    """
    Scan *text* for accepted Tamagotchi emoji and increase stats accordingly.

    Only call this with USER-authored text (not bot output).
    Respects ``tamagotchi_max_consumption`` — if non-zero, at most that many
    emoji are consumed from *text*.  Returns a dict of counts per category.

    In hardcore mode, also scans for medicine emoji to decrease sickness.
    """
    if not config.get("tamagotchi_enabled", False):
        return {}

    food_set = set(config.get("tamagotchi_food_emoji", []))
    drink_set = set(config.get("tamagotchi_drink_emoji", []))
    entertainment_set = set(config.get("tamagotchi_entertainment_emoji", []))

    # Hardcore medicine
    hardcore = config.get("tamagotchi_hardcore_enabled", False)
    medicine_set = set(config.get("tamagotchi_medicine_emoji", [])) if hardcore else set()
    medicine_heal = config.get("tamagotchi_medicine_heal", 1.0) if hardcore else 0

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

    counts = {"food": 0, "drink": 0, "entertainment": 0, "medicine": 0}
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
        elif em in medicine_set:
            config["tamagotchi_sickness"] = max(
                0.0,
                round(config.get("tamagotchi_sickness", 0) - medicine_heal, 2),
            )
            counts["medicine"] += 1

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
    With hardcore:
        -# 🍔 5/10 | 💧 3.5/10 | 😊 7/10 | 🤒 2/10

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

    footer = (
        f"-# 🍔 {_format_stat(hunger)}/{max_h} "
        f"| 💧 {_format_stat(thirst)}/{max_t} "
        f"| 😊 {_format_stat(happiness)}/{max_hp}"
    )

    if config.get("tamagotchi_hardcore_enabled", False):
        sickness = config.get("tamagotchi_sickness", 0)
        max_s = config.get("tamagotchi_max_sickness", 10)
        footer += f" | 🤒 {_format_stat(sickness)}/{max_s}"

    return footer


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

    lines = [
        "[TAMAGOTCHI STATUS — Your virtual pet stats. "
        "These are managed by script; you cannot change them yourself.",
        f"Hunger: {_format_stat(hunger)}/{max_h}",
        f"Thirst: {_format_stat(thirst)}/{max_t}",
        f"Happiness: {_format_stat(happiness)}/{max_hp}",
    ]

    # Add hardcore sickness info
    if config.get("tamagotchi_hardcore_enabled", False):
        sickness = config.get("tamagotchi_sickness", 0)
        max_s = config.get("tamagotchi_max_sickness", 10)
        med_emoji = " ".join(config.get("tamagotchi_medicine_emoji", []))
        lines.append(f"Sickness: {_format_stat(sickness)}/{max_s} (HARDCORE MODE)")
        lines.append(f"Accepted medicine emoji: {med_emoji or '(none)'}")
        lines.append(
            "If sickness reaches max, you die — your soul is wiped and stats reset. "
            "Users can give you medicine emoji to reduce sickness."
        )

    lines.append(f"Accepted food emoji: {food_emoji or '(none)'}")
    lines.append(f"Accepted drink emoji: {drink_emoji or '(none)'}")
    lines.append(f"Accepted entertainment emoji: {ent_emoji or '(none)'}")
    lines.append(
        "Users can feed you by including these emoji in their messages. "
        "Your stats decrease each time you respond.]"
    )

    return "\n".join(lines)
