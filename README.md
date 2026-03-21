# ChatBuddy v3.1

ChatBuddy is a Discord chatbot powered by Google Gemini (and optionally Gemma or custom external models) that participates in server conversations through mentions, auto-chat mode, and scheduled chat revival — with support for audio responses, a word guessing game, stream-of-consciousness thought extraction, and fully configurable behaviour via slash commands.

---

## Quick Start

### 1. Prerequisites

- **Python 3.10+**
- A **Discord Bot Token** (from the [Discord Developer Portal](https://discord.com/developers/applications))
- A **Google Gemini API key** (from [Google AI Studio](https://aistudio.google.com/app/apikey))

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Copy or create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token_here
```

### 4. Run the Bot

```bash
python bot.py
```

The bot will come online and sync its slash commands with Discord automatically.

---

## Setup Walkthrough

Once the bot is online in your server, use these slash commands to configure it (all require **Administrator** permissions unless noted):

### Step 1 — Set Your API Key

```
/set-api-key key:<your Gemini API key>
```

### Step 2 — Whitelist a Channel

The bot only responds in whitelisted channels:

```
/set-allowed-channel channel:#general enabled:True
```

### Step 3 — Set a System Prompt

Give the bot its personality:

```
/set-sys-instruct prompt:You are a friendly and witty chatbot named ChatBuddy.
```

### Step 4 — Start Chatting

Mention the bot (`@ChatBuddy`) or reply to one of its messages. That's it!

---

## Command Reference

### ⚙️ Core Settings

| Command | Description |
|---|---|
| `/set-api-key` | Set the Gemini API key |
| `/set-api-context` | Enable internal daily LLM API quota tracking / logic in system prompt |
| `/check-api-quota` | Check the current tracked daily quota visually |
| `/set-edit-api-current-quota` | Manually correct the current API usage counter (cannot exceed max limit) |
| `/set-chat-history` | Set how many messages of context the bot receives (default: 30) |
| `/set-temp` | Set model temperature (0.0 – 2.0) |
| `/set-api-endpoint-gemini` | Set the Gemini model endpoint |
| `/set-api-endpoint-gemma` | Set the Gemma model endpoint |
| `/set-api-key-custom` | Set the API key for a custom (non-Google) model |
| `/set-api-endpoint-custom` | Set the endpoint for a custom model (model name or full URL) |
| `/set-sys-instruct` | Set the main system prompt |
| `/show-sys-instruct` | Display the full effective system prompt |
| `/set-model-mode` | Switch between `gemini`, `gemma`, and `custom` |

### 🌐 Multimodal & Search

| Command | Description |
|---|---|
| `/set-multimodal` | Enable Image and Audio analysis for incoming payloads |
| `/set-gemini-web-search` | Enable internal Google Search Grounding for API responses (requires quota) |
| `/set-duck-search` | Enable free DuckDuckGo Python Search capabilities |

### 🧠 Soul Memory

| Command | Description |
|---|---|
| `/set-soul` | Enable/disable the self-updating soul memory |
| `/show-soul` | View current soul memory |
| `/edit-soul-add-entry` | Add/append a new memory entry manually |
| `/edit-soul-overwrite` | Overwrite an existing memory entry manually |
| `/edit-soul-delete-entry` | Delete a given memory entry manually |
| `/wipe-soul` | Wipe all memory entries immediately |
| `/set-soul-channel` | Set the channel to log soul updates + enable/disable |

**💡 Note on Soul Memory:** 
To use the Soul feature effectively, ensure you provide instructions in the main system prompt (via `/set-sys-instruct`) telling the bot *when* and *what* it should remember. The bot interacts with the soul file by outputting these exact tags in its response:
- `<!soul-add-new[id]: text>` to add a completely new memory entry.
- `<!soul-update[id]: text>` to append to an existing memory.
- `<!soul-override[id]: text>` to completely overwrite a memory ID.
- `<!soul-delete[id]>` to remove a memory entirely.

### 📝 Dynamic & Game Prompts

| Command | Description |
|---|---|
| `/set-dynamic-system-prompt` | Set an extra prompt appended after the main prompt + enable/disable |
| `/set-word-game` | Set word game rules (use `{secret-word}` placeholder) + enable/disable |
| `/set-word-game-selector-prompt` | Set the hidden-turn prompt the model uses to pick a word |
| `/set-secret-word` | Trigger a hidden turn to pick a new secret word *(role-gated)* |
| `/set-secret-word-permission` | Grant or revoke a role's access to `/set-secret-word` |

### 🔊 Audio Clip Mode

| Command | Description |
|---|---|
| `/set-audio-endpoint` | Set the TTS model |
| `/set-audio-settings` | Choose the voice (e.g. Aoede, Puck, Charon) |
| `/set-audio-mode` | Enable/disable audio clips globally |

### 📺 Channel Settings

| Command | Description |
|---|---|
| `/set-allowed-channel` | Whitelist or blacklist a channel for the bot |
| `/set-ce` | Enable/disable `[ce]` context cutoff per channel |

### 🧠 Stream of Consciousness (SoC)

| Command | Description |
|---|---|
| `/set-soc` | Set the thoughts output channel + enable/disable |
| `/set-soc-context` | Enable cross-channel thought context + set message count |

Wrap thoughts in `<my-thoughts>` tags in the system prompt — the bot will extract them to the SoC channel. `[ce]` works in the SoC channel too.

### 💬 Auto-Chat Mode

| Command | Description |
|---|---|
| `/set-auto-chat-mode` | Auto-reply in a channel without requiring mentions |
| `/set-auto-idle-message` | Set the message posted when the bot enters idle mode |

The bot checks every N seconds for new messages. After the configured idle timeout with no new user messages, it goes idle and stops checking. A mention or reply to the bot reactivates it.

### 🔁 Chat Revival

| Command | Description |
|---|---|
| `/set-chat-revival` | Configure periodic chat revival + enable/disable |
| `/set-cr-params` | Set active window duration & check interval |
| `/set-cr-leave-msg` | Set the goodbye message after revival expires |

### ⏰ Reminders & Auto-Wake

| Command | Description |
|---|---|
| `/setup-reminders` | Enable/disable reminders and set their output channel |
| `/set-reminder-channel` | Set the channel where fired reminders are posted |
| `/set-reminder-log-channel` | Set the channel where reminder registrations are logged |
| `/add-reminder` | Manually add a named reminder (dd-mm-yy HH:MM) |
| `/delete-reminder` | Manually delete a reminder by name |
| `/show-reminders` | Show all currently scheduled reminders and auto-wake times |

**💡 Note on Reminders:** 
The bot manages its own reminders via XML-style output tags. Instruct it to output:
- `<!add-reminder>` / `<!delete-reminder>`
- `<!add-auto-wake-time>` / `<!delete-auto-wake-time>`

### 🤖 Bot-to-Bot Response

| Command | Description |
|---|---|
| `/set-respond-to-bot` | Enable or disable the bot responding to other bots |
| `/set-respond-bot-limit` | Set a limit (1-9) to stop responding after consecutive bot messages |

### 💓 Heartbeat

| Command | Description |
|---|---|
| `/set-heartbeat` | Configure and enable a periodic heartbeat (fires unconditionally on an interval) |

### 🐣 Tamagotchi Minigame

| Command | Description |
|---|---|
| `/set-tamagochi-rules` | Set accepted food, drink, and entertainment emoji + maximum stat values |
| `/set-tamagochi-mode` | Enable or disable Tamagotchi mode (rules must be configured first) |
| `/set-tamagochi-depletion-rate` | Set how much hunger/thirst/happiness decrease per bot inference |
| `/set-tamagochi-fill-rate` | Set how much stats increase per accepted emoji consumed (default: 1) |
| `/set-tamagochi-max-consumption` | Limit how many emoji the bot can consume from a single input (0 = unlimited) |
| `/show-tamagochi-stats` | Display current stats, accepted emoji, depletion/fill rates, and max consumption |

**How it works:**

1. **Configure rules** with `/set-tamagochi-rules` — pick which emoji count as food 🍔, drink 💧, and entertainment 🎮, plus the maximum value for each stat.
2. **Enable the mode** with `/set-tamagochi-mode true`.
3. **Stats deplete** each time the bot generates a response (any path — mentions, heartbeat, auto-chat, reminders, revival).
4. **Users feed the bot** by including accepted emoji in their messages. Only *user* input is scanned — the bot cannot feed itself.
5. **A stats footer** (e.g. `-# 🍔 5/10 | 💧 3.5/10 | 😊 7/10`) is appended to every visible bot response. If the bot only produces thoughts/commands with no chat-visible text, the footer is silently skipped.
6. **Depletion and fill rates** must have at most 2 decimal places and be ≤ 99. Fill rates default to 1 (one emoji = +1 stat point).
7. The bot's **system prompt** includes current Tamagotchi status so the LLM is aware of its condition, but all stat changes are handled by the script — the LLM cannot cheat.

### 💀 Tamagotchi Hardcore Mode

| Command | Description |
|---|---|
| `/set-hardcore-sickness-stat` | Set the max sickness value (death threshold, max 2 decimals, ≤ 99) |
| `/set-hardcore-tamagochi-medicine` | Set medicine emoji and heal amount per emoji |
| `/set-hardcore-tamagochi-sickness-thresh-hold` | Set stat thresholds below which sickness increases |
| `/set-hardcore-tamagochi-sickness-increase` | Set how much sickness increases per turn per stat below threshold |
| `/set-tamagochi-rip-message` | Set a custom death message (leave empty to use the default) |
| `/set-hardcore-tamagochi-mode` | Enable/disable hardcore mode (all settings above must be configured first) |

**How it works:**

1. **Configure all settings** — max sickness, medicine emoji, thresholds, and sickness increase rates.
2. **Enable hardcore** with `/set-hardcore-tamagochi-mode true` (refuses if anything is missing, and tells you what).
3. **Sickness increases** each turn for every stat that is below its threshold. Multiple stats below threshold stack.
4. **Medicine emoji** in user messages **decrease sickness** by the configured heal amount.
5. **Death** — when sickness reaches max: the soul file (`soul.md`) is wiped clean, all stats reset to max, sickness resets to 0, `[ce]` is sent to **all allowed channels and the SoC channel** (wiping all context), and the death message is posted in chat.
6. **Custom death message** — use `/set-tamagochi-rip-message` to set a custom message. Leave empty to use the default.
7. **Disabling** hardcore mode resets sickness to 0 and removes sickness from the footer.

---

## Model Modes

| Mode | Description |
|---|---|
| `gemini` | Standard Google Gemini — uses `systemInstruction` field |
| `gemma` | Gemma-compatible — system prompt injected into user content |
| `custom` | External / non-Google API — uses a separate API key and endpoint |

For **custom mode**, set your endpoint and key:

```
/set-api-endpoint-custom endpoint:https://your-api.example.com/v1/generateContent
/set-api-key-custom key:your_custom_key
/set-model-mode mode:custom
```

If the custom endpoint starts with `http`, it's used as a full URL. Otherwise, it's treated as a model name under the standard Gemini API base.

---

## Deployment

The bot includes a built-in HTTP health-check server (for platforms like Back4app / Discloud). It listens on the port defined by the `PORT` environment variable (default `8080`).

### Docker

```bash
docker build -t chatbuddy .
docker run -e DISCORD_TOKEN=your_token -e PORT=8080 chatbuddy
```
