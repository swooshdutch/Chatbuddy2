"""
gemini_api.py — Async Gemini API client for ChatBuddy.

Text model modes (model_mode):
  gemini   — Standard Gemini inference with systemInstruction support.
  gemma    — Gemma-compatible: system prompt injected into user content.
  custom   — External / non-Google API with separate key and endpoint.

Audio clip mode (audio_enabled = True/False — fully independent of model_mode):
  When enabled, every text response is also converted to speech via the
  Gemini Live API WebSocket (tts.py).
"""

import os
import aiohttp
from datetime import datetime
import datetime as dt_module
from urllib.parse import urlparse

from config import save_config
from secret_store import get_secret
from utils import handle_soul_updates, extract_thoughts, extract_reminder_commands
from tts import generate_tts

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# ── friendly error messages ────────────────────────────────────────────────────
MSG_NO_KEY = (
    "⚠️ No API key has been configured yet. "
    "An administrator needs to run `/set-api-key` before I can respond."
)
MSG_RATE_LIMIT    = "I'm sorry, I'm out of API juice right now — please try again in a moment."
MSG_SAFETY_BLOCK  = (
    "⚠️ My response was blocked by the safety filter. "
    "Try rephrasing your message."
)
MSG_GENERIC_ERROR = "⚠️ Something went wrong while generating a response. Please try again later."


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_current_time_context() -> str:
    """Return a compact local-time header for the top of the system prompt."""
    now = datetime.now().astimezone()
    tz_name = now.tzname() or "local"
    utc_offset = now.strftime("%z")
    if utc_offset:
        utc_offset = f"UTC{utc_offset[:3]}:{utc_offset[3:]}"
    else:
        utc_offset = "UTC unknown"

    return (
        "[CURRENT TIME CONTEXT]\n"
        f"Local datetime: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Weekday: {now.strftime('%A')}\n"
        f"Timezone: {tz_name} ({utc_offset})\n"
        "Use this as the current reference point when interpreting relative time in chat history "
        "and user messages (for example: today, yesterday, tomorrow, later, earlier, in 2 hours)."
    )


def _prepend_time_context(system_prompt: str) -> str:
    """Ensure the prompt always starts with an explicit current-time anchor."""
    time_context = _build_current_time_context()
    return f"{time_context}\n\n{system_prompt}".strip() if system_prompt else time_context


def build_system_prompt(config: dict, *, include_word_game: bool = True) -> str:
    """
    Assemble the full system prompt from config.

    Hierarchy:
        Main system prompt
        + Dynamic prompt (if enabled)
        + Word game prompt with {secret-word} replaced (if enabled AND include_word_game)
    """
    parts = [config.get("system_prompt", "")]

    if config.get("dynamic_prompt_enabled") and config.get("dynamic_prompt", ""):
        parts.append(config["dynamic_prompt"])

    if include_word_game and config.get("word_game_enabled") and config.get("word_game_prompt", ""):
        secret = config.get("secret_word", "")
        game_prompt = config["word_game_prompt"].replace("{secret-word}", secret)
        parts.append(game_prompt)

    # Inject Soul from soul.md
    if config.get("soul_enabled", False):
        soul_text = ""
        if os.path.exists("soul.md"):
            try:
                with open("soul.md", "r", encoding="utf-8") as f:
                    soul_text = f.read().strip()
            except Exception:
                pass
        
        soul_instructions = (
            "[SOUL — This is your mutable memory system.\n"
            "To add a completely new memory entry, output: <!soul-add-new[id]: text>\n"
            "To append to an existing entry ID, output: <!soul-update[id]: text>\n"
            "To completely overwrite an entry ID, output: <!soul-override[id]: text>\n"
            "To delete an entry ID, output: <!soul-delete[id]>]"
        )
        if soul_text:
            parts.append(f"{soul_instructions}\n\nCURRENT SOUL CONTENT:\n{soul_text}")
        else:
            parts.append(f"{soul_instructions}\n\nCURRENT SOUL CONTENT:\n(empty)")

    # Inject 1-turn soul error if it exists
    soul_error = config.get("soul_error_turn", "")
    if soul_error:
        parts.append(f"[SYSTEM NOTICE FOR THIS TURN ONLY]\n{soul_error}")
        config["soul_error_turn"] = ""
        save_config(config)

    # Inject reminders & auto-wake-times
    if config.get("reminders_enabled", False):
        from reminders import get_all_reminders_text  # lazy to avoid circular import
        reminder_instructions = (
            "[REMINDERS & AUTO-WAKE — Your scheduled event system.\n"
            "IMPORTANT: Use EXACTLY this date format: dd-mm-yy HH:MM (24-hour clock).\n"
            "Example: 20-03-26 22:30 means 20th March 2026 at 22:30.\n\n"
            "To schedule a new reminder, output: <!add-reminder : [dd-mm-yy HH:MM] [prompt]>\n"
            "To cancel an existing reminder, output: <!delete-reminder : [dd-mm-yy HH:MM] [prompt]>\n"
            "To schedule a self-wake, output: <!add-auto-wake-time : [dd-mm-yy HH:MM] [self-prompt]>\n"
            "To cancel a self-wake, output: <!delete-auto-wake-time : [dd-mm-yy HH:MM] [self-prompt]>\n"
            "These tags are automatically hidden from users and logged for transparency.\n"
            "When a reminder fires, its prompt is sent to you as input.]"
        )
        all_reminders = get_all_reminders_text()
        parts.append(f"{reminder_instructions}\n\nCURRENT SCHEDULED ENTRIES:\n{all_reminders}")

    # Inject API Context Usage
    if config.get("api_context_enabled", False):
        limit = config.get("api_context_limit", 500)
        usage = config.get("api_context_current_usage", 0)
        reset_time = config.get("api_context_reset_time", "00:00")
        api_text = (
            f"# your daily api limit (when this number hits {limit}/{limit} you are no longer able to output until after {reset_time}), "
            f"you are currently at {usage}/{limit}."
        )
        parts.append(api_text)

    # Inject Tamagotchi status
    if config.get("tama_enabled", False):
        from tamagotchi import build_tamagotchi_system_prompt
        tama_prompt = build_tamagotchi_system_prompt(config)
        if tama_prompt:
            parts.append(tama_prompt)

    return "\n\n".join(p for p in parts if p)


def _build_user_text(
    prompt: str,
    context: str,
    system_prompt: str,
    gemma_mode: bool,
    speaker_name: str = "",
    speaker_id: str = "",
) -> str:
    """Assemble the full user-content string sent to the text model."""
    parts = []
    if gemma_mode and system_prompt:
        parts.append(
            "[BEHAVIORAL INSTRUCTIONS — follow these at all times]\n"
            f"{system_prompt}\n"
            "[END BEHAVIORAL INSTRUCTIONS]\n"
        )
    if context:
        parts.append(f"[CHAT CONTEXT]\n{context}\n[END CHAT CONTEXT]\n")
    if speaker_name:
        parts.append(f"[CURRENT SPEAKER]\n{speaker_name} (ID:{speaker_id})")
    parts.append(f"[USER MESSAGE]\n{prompt}")
    return "\n".join(parts)


def _extract_text(data: dict) -> str | None:
    """Pull the first text part out of a generateContent response."""
    candidates = data.get("candidates", [])
    if not candidates:
        return None
    candidate = candidates[0]
    if candidate.get("finishReason") == "SAFETY":
        return None
    for part in candidate.get("content", {}).get("parts", []):
        if "text" in part:
            return part["text"]
    return None


def _requires_search(prompt: str) -> bool:
    """Heuristic to decide if we should attach the web search tool, saving quota."""
    if not prompt:
        return False
    p = prompt.lower()
    triggers = [
        "search", "google", "look up", "lookup", "find out", "browse",
        "latest", "news", "current", "today", "weather",
        "who won", "price of", "how much is", "what time is"
    ]
    for t in triggers:
        if t in p:
            return True
    return False


def _is_google_api_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host.endswith("generativelanguage.googleapis.com")


# ── main entry point ──────────────────────────────────────────────────────────

async def generate(
    prompt: str,
    context: str,
    config: dict,
    revival_system_instruct: str = "",
    speaker_name: str = "",
    speaker_id: str = "",
    system_prompt_override: str | None = None,
    attachments: list[dict] | None = None,
) -> tuple[str, bytes | None, list[str], list[tuple[str, str, str]]]:
    """
    Call the Gemini API and return (text_reply, wav_bytes_or_None, soul_logs, reminder_cmds).

    system_prompt_override: if provided, used instead of the auto-assembled
    system prompt.  Used by the word-game hidden turn.
    """
    api_key = get_secret("api_key")
    if not api_key:
        return MSG_NO_KEY, None, [], []

    # ── API Context Tracker Increment ──
    if config.get("api_context_enabled", False):
        try:
            now = datetime.now()
            reset_time_str = config.get("api_context_reset_time", "00:00")
            parts_rt = reset_time_str.split(":")
            reset_hour = int(parts_rt[0]) if len(parts_rt) > 0 else 0
            reset_minute = int(parts_rt[1]) if len(parts_rt) > 1 else 0
            
            reset_threshold = now.replace(hour=reset_hour, minute=reset_minute, second=0, microsecond=0)
            
            if now >= reset_threshold:
                effective_date = now.strftime("%Y-%m-%d")
            else:
                effective_date = (now - dt_module.timedelta(days=1)).strftime("%Y-%m-%d")
                
            last_reset = config.get("api_context_last_reset_date", "")
            if last_reset != effective_date:
                config["api_context_current_usage"] = 0
                config["api_context_last_reset_date"] = effective_date
                
            config["api_context_current_usage"] = config.get("api_context_current_usage", 0) + 1
            save_config(config)
        except Exception as e:
            print(f"[ChatBuddy] API Context tracker error: {e}")

    model_mode    = config.get("model_mode", "gemini")
    # Treat legacy "default" the same as "gemini"
    if model_mode == "default":
        model_mode = "gemini"
    gemma_mode    = model_mode == "gemma"
    custom_mode   = model_mode == "custom"
    audio_enabled = config.get("audio_enabled", False)

    # Pick API key — custom mode can override
    if custom_mode:
        effective_api_key = get_secret("api_key_custom") or api_key
    else:
        effective_api_key = api_key

    # Pick endpoint based on mode
    if custom_mode:
        text_endpoint = config.get("model_endpoint_custom", "")
        if not text_endpoint:
            return "⚠️ No custom model endpoint configured. Run `/set-api-endpoint-custom` first.", None, [], []
    elif gemma_mode:
        text_endpoint = config.get("model_endpoint_gemma", "")
        if not text_endpoint:
            text_endpoint = config.get("model_endpoint", "gemini-2.0-flash")
    else:
        text_endpoint = config.get("model_endpoint_gemini", "gemini-2.0-flash")
        if not text_endpoint:
            text_endpoint = config.get("model_endpoint", "gemini-2.0-flash")

    temperature = config.get("temperature", 0.7)

    # Build effective system prompt
    if system_prompt_override is not None:
        system_prompt = system_prompt_override
    else:
        # Normal assembly: include_word_game=True unless revival
        include_game = not bool(revival_system_instruct)
        system_prompt = build_system_prompt(config, include_word_game=include_game)

    if revival_system_instruct:
        system_prompt = (system_prompt + "\n\n" + revival_system_instruct).strip()

    system_prompt = _prepend_time_context(system_prompt)

    # ── Step 1: text inference via REST generateContent ────────────────────
    # Custom mode with Gemma-style injection when using non-Google APIs
    inject_prompt = gemma_mode or custom_mode
    user_text = _build_user_text(prompt, context, system_prompt, inject_prompt, speaker_name, speaker_id)

    parts = []
    if attachments:
        import base64
        for att in attachments:
            b64_data = base64.b64encode(att["data"]).decode("utf-8")
            parts.append({
                "inlineData": {
                    "mimeType": att["mime_type"],
                    "data": b64_data
                }
            })
    parts.append({"text": user_text})

    text_body: dict = {
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
        "generationConfig": {
            "temperature": temperature,
        },
    }

    if config.get("web_search_enabled", False) and _requires_search(prompt):
        text_body["tools"] = [{"googleSearch": {}}]

    # Only standard Gemini mode uses the top-level systemInstruction field
    if not inject_prompt and system_prompt:
        text_body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    # Build the request URL — custom endpoints may be full URLs
    if custom_mode and text_endpoint.startswith("http"):
        # Full external URL — append key as query param
        text_url = text_endpoint
        headers: dict[str, str] = {}
        if _is_google_api_url(text_endpoint):
            headers["x-goog-api-key"] = effective_api_key
        else:
            sep = "&" if "?" in text_endpoint else "?"
            text_url = f"{text_endpoint}{sep}key={effective_api_key}"
    else:
        headers = {"x-goog-api-key": effective_api_key}
        text_url = f"{API_BASE}/{text_endpoint}:generateContent"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(text_url, json=text_body, headers=headers or None) as resp:
                status = resp.status
                data   = await resp.json()

        if status == 429:
            print(f"[ChatBuddy] Text API error 429 (Rate Limit): {data}")
            err_msg = str(data.get("error", {}).get("message", "Rate Limit / Quota Exceeded"))
            return f"⚠️ **Google API Error (429 Rate Limit)**:\n{err_msg}\n*(If you requested a search, your free tier quota likely does not support Search Grounding on this model!)*", None, [], []

        if status != 200:
            err = str(data)
            if "SAFETY" in err.upper() or "blocked" in err.lower():
                return MSG_SAFETY_BLOCK, None, [], []
            print(f"[ChatBuddy] Text API error {status}: {data}")
            err_msg = str(data.get("error", {}).get("message", err))
            return f"⚠️ **Google API Error ({status})**:\n{err_msg}", None, [], []

        if data.get("promptFeedback", {}).get("blockReason"):
            return MSG_SAFETY_BLOCK, None, [], []

        text_reply = _extract_text(data)
        if text_reply is None:
            return MSG_SAFETY_BLOCK, None, [], []

        # Process soul immediately before TTS or returning
        text_reply, soul_logs = handle_soul_updates(text_reply, config)

        # Extract reminder / wake-time commands from the response
        text_reply, reminder_cmds = extract_reminder_commands(text_reply)

    except aiohttp.ClientError as e:
        print(f"[ChatBuddy] HTTP error during text inference: {e}")
        return MSG_GENERIC_ERROR, None, [], []
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ChatBuddy] Unexpected error during text inference: {e}")
        return MSG_GENERIC_ERROR, None, [], []

    # ── Step 2: TTS via WebSocket Live API (only when audio is enabled) ────
    if not audio_enabled:
        return text_reply, None, soul_logs, reminder_cmds

    tts_endpoint = config.get("audio_endpoint", "").strip()
    if not tts_endpoint:
        print("[ChatBuddy] audio_enabled=True but audio_endpoint is empty — skipping TTS.")
        return text_reply, None, soul_logs, reminder_cmds

    voice = config.get("audio_settings", {}).get("voice", "Aoede")

    # Ensure thoughts are stripped from audio generation
    tts_text, _ = extract_thoughts(text_reply)
    if not tts_text.strip():
        # If the response was ONLY thoughts, no need to synthesize empty audio
        return text_reply, None, soul_logs, reminder_cmds

    import re
    if re.search(r"<!search:\s*(.+?)>", text_reply):
        # Dodge audio endpoint for intermediate search turn
        return text_reply, None, soul_logs, reminder_cmds

    wav_bytes = await generate_tts(api_key, tts_endpoint, voice, tts_text)

    if wav_bytes is None:
        return text_reply, None, soul_logs, reminder_cmds

    return text_reply, wav_bytes, soul_logs, reminder_cmds
