"""Shared stat and state helpers for the Tamagotchi feature."""

from datetime import datetime, timedelta, timezone

from .common import *


def _fs(val: float) -> str:
    """Format a stat value: integer if whole, else up to 2 decimals."""
    if val == int(val):
        return str(int(val))
    return f"{val:.2f}".rstrip("0").rstrip(".")


def _fmt_countdown(seconds: float) -> str:
    """Return a human-readable countdown string like '4m 32s'."""
    s = max(0, int(seconds))
    if s >= 60:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s}s"


def _discord_relative_time(seconds: float) -> str:
    target = int(time.time() + max(0.0, seconds))
    return f"<t:{target}:R>"


def _discord_relative_epoch(epoch: float) -> str:
    return f"<t:{max(0, int(epoch))}:R>"


def _actor_display_name(user) -> str:
    display_name = str(getattr(user, "display_name", "") or getattr(user, "name", "")).strip()
    if display_name:
        return display_name
    user_id = getattr(user, "id", "")
    return f"User {user_id}" if user_id else "Someone"


def _bot_display_name(interaction: discord.Interaction) -> str:
    guild_me = getattr(interaction.guild, "me", None)
    if guild_me is not None:
        display_name = getattr(guild_me, "display_name", "") or getattr(guild_me, "name", "")
        if display_name:
            return display_name

    client_user = getattr(interaction.client, "user", None)
    if client_user is not None:
        display_name = getattr(client_user, "display_name", "") or getattr(client_user, "name", "")
        if display_name:
            return display_name

    return "Botty"


def _log_tamagotchi_action(
    config: dict,
    interaction: discord.Interaction,
    action: str,
    message_id: int,
    *,
    item_id: str = "",
    item_name: str = "",
    item_emoji: str = "",
) -> None:
    action_log = list(config.get("tama_action_log", []))
    action_log.append(
        {
            "action": action,
            "channel_id": str(interaction.channel_id or ""),
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.display_name,
            "message_id": str(message_id),
            "timestamp": time.time(),
            "item_id": item_id,
            "item_name": item_name,
            "item_emoji": item_emoji,
        }
    )
    config["tama_action_log"] = action_log[-200:]
    save_config(config)


def _item_action_name(item: dict) -> str:
    if item.get("item_type") == "food":
        return "feed"
    if item.get("item_type") == "drink":
        return "drink"
    if item.get("item_type") == "misc":
        return "other"
    return ""


def _item_default_icon(action: str) -> str:
    return "🍔" if action == "feed" else "🥤"


def _apply_item_emoji_to_response(message: str, item: dict) -> str:
    action = _item_action_name(item)
    chosen_emoji = item.get("emoji", "").strip() or _item_default_icon(action)
    default_icon = _item_default_icon(action)
    if "{item}" in message:
        return message.replace("{item}", chosen_emoji)
    if default_icon in message:
        return message.replace(default_icon, chosen_emoji)
    if chosen_emoji in message:
        return message
    return f"{chosen_emoji} {message}".strip()


def render_tamagotchi_action_message(
    message: str,
    *,
    actor_name: str,
    action_summary: str,
    bot_name: str = "",
    item_name: str = "",
    item_emoji: str = "",
) -> str:
    """Inject actor-aware context into public Tamagotchi action messages."""
    rendered = (
        (message or "").strip()
        .replace("{user}", actor_name)
        .replace("{user_name}", actor_name)
        .replace("{actor}", actor_name)
        .replace("{bot}", bot_name)
        .replace("{item_name}", item_name)
        .replace("{item_emoji}", item_emoji)
    ).strip()
    if actor_name and actor_name not in rendered:
        prefix = f"**{actor_name}** {action_summary}."
        return f"{prefix}\n{rendered}".strip() if rendered else prefix
    return rendered


def is_sleeping(config: dict) -> bool:
    """Return True while the rest timer is active."""
    sleep_until = float(config.get("tama_sleep_until", 0.0) or 0.0)
    if sleep_until <= time.time():
        if config.get("tama_sleeping", False) or sleep_until:
            config["tama_sleeping"] = False
            config["tama_sleep_until"] = 0.0
            save_config(config)
        return False
    return True


def sleeping_remaining(config: dict) -> float:
    return max(0.0, float(config.get("tama_sleep_until", 0.0) or 0.0) - time.time())


def build_sleeping_message(config: dict) -> str:
    template = config.get("tama_resp_sleeping", "I am sleeping come back in {time}")
    return template.replace("{time}", _discord_relative_time(sleeping_remaining(config)))


def build_awake_message(config: dict) -> str:
    return "✨ I'm awake again!"


def get_birth_datetime(config: dict) -> datetime | None:
    birth_at = float(config.get("tama_birth_at", 0.0) or 0.0)
    if birth_at <= 0.0:
        return None
    return datetime.fromtimestamp(birth_at, tz=timezone.utc).astimezone()


def is_hatching(config: dict) -> bool:
    hatch_until = float(config.get("tama_hatch_until", 0.0) or 0.0)
    return bool(config.get("tama_hatching", False)) and hatch_until > time.time()


def hatching_remaining(config: dict) -> float:
    return max(0.0, float(config.get("tama_hatch_until", 0.0) or 0.0) - time.time())


def build_hatching_message(config: dict) -> str:
    remaining = max(1, int(hatching_remaining(config) + 0.999))
    return f"🥚 I'm about to hatch... life begins in **{remaining}s**. Please wait for me to hatch first."


def can_use_energy(config: dict) -> bool:
    return float(config.get("tama_energy", 0.0) or 0.0) > 0.0


def energy_ratio(config: dict) -> float:
    maximum = float(config.get("tama_energy_max", 100) or 0.0)
    if maximum <= 0.0:
        return 0.0
    current = float(config.get("tama_energy", 0.0) or 0.0)
    return max(0.0, min(1.0, current / maximum))


def apply_direct_energy_delta(config: dict, delta: float) -> float:
    current = float(config.get("tama_energy", 0.0) or 0.0)
    maximum = float(config.get("tama_energy_max", 100.0) or 100.0)
    new_value = min(maximum, max(0.0, round(current + float(delta or 0.0), 2)))
    applied = round(new_value - current, 2)
    if applied:
        config["tama_energy"] = new_value
    return applied


def apply_direct_happiness_delta(config: dict, delta: float) -> float:
    current = float(config.get("tama_happiness", 0.0) or 0.0)
    maximum = float(config.get("tama_happiness_max", 100.0) or 100.0)
    new_value = min(maximum, max(0.0, round(current + float(delta or 0.0), 2)))
    applied = round(new_value - current, 2)
    if applied:
        config["tama_happiness"] = new_value
    return applied


RPS_REWARD_KEYS = {
    "user_win": "tama_rps_reward_user_win",
    "draw": "tama_rps_reward_draw",
    "bot_win": "tama_rps_reward_bot_win",
}


def resolve_rps_outcome(user_choice: str, bot_choice: str) -> str:
    if user_choice == bot_choice:
        return "draw"
    if (
        (user_choice == "rock" and bot_choice == "scissors")
        or (user_choice == "paper" and bot_choice == "rock")
        or (user_choice == "scissors" and bot_choice == "paper")
    ):
        return "user_win"
    return "bot_win"


def apply_rps_happiness_reward(config: dict, outcome: str) -> float:
    reward_key = RPS_REWARD_KEYS.get(outcome)
    if not reward_key:
        return 0.0
    return apply_direct_happiness_delta(config, float(config.get(reward_key, 0.0) or 0.0))


def _heartbeat_rest_schedule(config: dict) -> tuple[int, int, int] | None:
    try:
        from heartbeat import normalize_heartbeat_rest_time
    except Exception:
        return None

    if not config.get("heartbeat_rest_enabled", True):
        return None

    duration_minutes = int(config.get("heartbeat_rest_duration_minutes", 480) or 0)
    if duration_minutes <= 0:
        return None

    normalized = normalize_heartbeat_rest_time(config.get("heartbeat_rest_start_time", "00:00"))
    if normalized is None:
        return None

    hour, minute = map(int, normalized.split(":"))
    return hour, minute, duration_minutes


def _heartbeat_rest_next_transition(
    config: dict,
    timestamp: float,
) -> tuple[float, bool]:
    schedule = _heartbeat_rest_schedule(config)
    if schedule is None:
        return float("inf"), False

    hour, minute, duration_minutes = schedule
    if duration_minutes >= 24 * 60:
        return float("inf"), True

    current_local = datetime.fromtimestamp(timestamp).astimezone()
    window = timedelta(minutes=duration_minutes)
    today_start = current_local.replace(hour=hour, minute=minute, second=0, microsecond=0)

    active_windows = [
        (today_start - timedelta(days=1), today_start - timedelta(days=1) + window),
        (today_start, today_start + window),
        (today_start + timedelta(days=1), today_start + timedelta(days=1) + window),
    ]
    for start, end in active_windows:
        if start <= current_local < end:
            return end.timestamp(), True

    next_start = min(start for start, _ in active_windows if start > current_local)
    return next_start.timestamp(), False


def _active_seconds_since(config: dict, start_ts: float, end_ts: float) -> float:
    if end_ts <= start_ts:
        return 0.0

    schedule = _heartbeat_rest_schedule(config)
    if schedule is None:
        return max(0.0, end_ts - start_ts)

    _, _, duration_minutes = schedule
    if duration_minutes >= 24 * 60:
        return 0.0

    active_seconds = 0.0
    cursor = float(start_ts)
    target = float(end_ts)
    while cursor < target:
        transition_ts, in_rest = _heartbeat_rest_next_transition(config, cursor)
        if in_rest:
            if transition_ts == float("inf"):
                break
            cursor = min(target, transition_ts)
            continue

        segment_end = min(target, transition_ts)
        active_seconds += max(0.0, segment_end - cursor)
        cursor = segment_end

    return active_seconds


def _advance_by_active_seconds(config: dict, start_ts: float, active_seconds: float) -> float:
    if active_seconds <= 0.0:
        return float(start_ts)

    schedule = _heartbeat_rest_schedule(config)
    if schedule is None:
        return float(start_ts) + float(active_seconds)

    _, _, duration_minutes = schedule
    if duration_minutes >= 24 * 60:
        return float("inf")

    remaining = float(active_seconds)
    cursor = float(start_ts)
    while remaining > 0.0:
        transition_ts, in_rest = _heartbeat_rest_next_transition(config, cursor)
        if in_rest:
            if transition_ts == float("inf"):
                return float("inf")
            cursor = transition_ts
            continue

        available = transition_ts - cursor
        if transition_ts == float("inf") or remaining <= available:
            return cursor + remaining

        remaining -= available
        cursor = transition_ts

    return cursor


def loneliness_next_due_at(config: dict) -> float:
    interval = max(1.0, float(config.get("tama_happiness_depletion_interval", 600) or 600))
    base = max(
        float(config.get("tama_last_interaction_at", 0.0) or 0.0),
        float(config.get("tama_lonely_last_update_at", 0.0) or 0.0),
    )
    if base <= 0.0:
        return time.time() + interval
    return _advance_by_active_seconds(config, base, interval)


def should_auto_sleep(config: dict) -> bool:
    return (
        config.get("tama_enabled", False)
        and not is_sleeping(config)
        and float(config.get("tama_energy", 0.0) or 0.0) <= 0.0
    )


def apply_low_energy_happiness_penalty(config: dict) -> float:
    threshold_pct = max(0.0, min(100.0, float(config.get("tama_low_energy_happiness_threshold_pct", 10.0) or 0.0)))
    happiness_loss = max(0.0, float(config.get("tama_low_energy_happiness_loss", 1.0) or 0.0))
    if threshold_pct <= 0.0 or happiness_loss <= 0.0:
        return 0.0
    if energy_ratio(config) * 100.0 >= threshold_pct:
        return 0.0

    current_happiness = float(config.get("tama_happiness", 0.0) or 0.0)
    new_happiness = max(0.0, round(current_happiness - happiness_loss, 2))
    actual_loss = round(current_happiness - new_happiness, 2)
    if actual_loss > 0.0:
        config["tama_happiness"] = new_happiness
    return actual_loss


def _stat_ratio(current: float, maximum: float) -> float:
    if maximum <= 0:
        return 0.0
    return max(0.0, min(1.0, float(current) / float(maximum)))


def happiness_emoji(config: dict) -> str:
    percent = _stat_ratio(
        float(config.get("tama_happiness", 0)),
        float(config.get("tama_happiness_max", 100)),
    ) * 100
    if percent >= 80:
        return "😁"
    if percent >= 60:
        return "😀"
    if percent >= 40:
        return "🙂"
    if percent >= 20:
        return "😕"
    return "😠"


def should_show_medicate(config: dict) -> bool:
    current_health = float(config.get("tama_health", 0.0) or 0.0)
    max_health = float(config.get("tama_health_max", 100.0) or 100.0)
    return bool(config.get("tama_sick", False)) or current_health < max_health


def wipe_soul_file() -> None:
    try:
        with open("soul.md", "w", encoding="utf-8") as f:
            f.write("{}")
        print("[Tamagotchi] soul.md wiped.")
    except Exception as e:
        print(f"[Tamagotchi] Failed to wipe soul.md: {e}")


def reset_tamagotchi_state(config: dict) -> None:
    now = time.time()
    config["tama_hunger"] = round(float(config.get("tama_hunger_max", 100)) * 0.5, 2)
    config["tama_thirst"] = round(float(config.get("tama_thirst_max", 100)) * 0.5, 2)
    config["tama_happiness"] = round(float(config.get("tama_happiness_max", 100)) * 0.5, 2)
    config["tama_health"] = float(config.get("tama_health_max", 100))
    config["tama_energy"] = float(config.get("tama_energy_max", 100))
    config["tama_dirt"] = 0
    config["tama_dirt_food_counter"] = 0
    config["tama_dirt_grace_until"] = 0.0
    config["tama_feed_energy_counter"] = 0
    config["tama_drink_energy_counter"] = 0
    config["tama_sick"] = False
    config["tama_sleeping"] = False
    config["tama_sleep_until"] = 0.0
    config["tama_birth_at"] = 0.0
    config["tama_last_interaction_at"] = now
    config["tama_lonely_last_update_at"] = now


def apply_loneliness(config: dict, *, now: float | None = None, save: bool = False) -> float:
    if not config.get("tama_enabled", False):
        return 0.0

    now = time.time() if now is None else now
    interval = max(1.0, float(config.get("tama_happiness_depletion_interval", 600) or 600))
    amount = max(0.0, float(config.get("tama_happiness_depletion", 1.0) or 0.0))
    last_interaction = float(config.get("tama_last_interaction_at", 0.0) or 0.0)
    last_update = float(config.get("tama_lonely_last_update_at", 0.0) or 0.0)
    base = max(last_interaction, last_update)

    if base <= 0.0:
        config["tama_last_interaction_at"] = now
        config["tama_lonely_last_update_at"] = now
        if save:
            save_config(config)
        return 0.0

    active_elapsed = _active_seconds_since(config, base, now)
    steps = int(max(0.0, active_elapsed) // interval)
    if steps <= 0 or amount <= 0.0:
        return 0.0

    loss = round(steps * amount, 2)
    config["tama_happiness"] = max(
        0.0,
        round(float(config.get("tama_happiness", 0.0) or 0.0) - loss, 2),
    )
    config["tama_lonely_last_update_at"] = _advance_by_active_seconds(config, base, steps * interval)
    if save:
        save_config(config)
    return loss


def apply_need_depletion_from_energy(config: dict, energy_loss: float) -> None:
    if not config.get("tama_enabled", False):
        return

    energy_loss = max(0.0, float(energy_loss or 0.0))
    if energy_loss <= 0.0:
        return

    per_energy = max(0.01, float(config.get("tama_needs_depletion_per_energy", 1.0) or 1.0))
    hunger_loss = (energy_loss / per_energy) * max(0.0, float(config.get("tama_hunger_depletion", 1.0) or 0.0))
    thirst_loss = (energy_loss / per_energy) * max(0.0, float(config.get("tama_thirst_depletion", 1.0) or 0.0))

    config["tama_hunger"] = max(
        0.0,
        round(float(config.get("tama_hunger", 0.0) or 0.0) - hunger_loss, 2),
    )
    config["tama_thirst"] = max(
        0.0,
        round(float(config.get("tama_thirst", 0.0) or 0.0) - thirst_loss, 2),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
