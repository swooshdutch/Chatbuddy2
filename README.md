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

### 🐣 Tamagotchi

A gamified virtual pet system with Discord button interactions.

#### Stat Configuration

| Command | Description |
|---|---|
| `/set-tama-mode` | Enable or disable Tamagotchi mode |
| `/set-tama-hunger` | Set max hunger and depletion per inference |
| `/set-tama-thirst` | Set max thirst and depletion per inference |
| `/set-tama-happiness` | Set max happiness and depletion per inference |
| `/set-tama-health` | Set max health, damage per stat below threshold, and threshold |
| `/set-tama-satiation` | Set max satiation, cooldown timer, food/drink increase, and depletion |
| `/set-tama-energy` | Set max energy and depletion for API calls / games |
| `/set-tama-dirt` | Set max poop, food threshold for poop, health damage, and damage interval |
| `/set-tama-sickness` | Set health damage per turn while sick |

#### Button Configuration

| Command | Description |
|---|---|
| `/set-tama-feed` | Set hunger restored and cooldown for the Feed button |
| `/set-tama-drink` | Set thirst restored and cooldown for the Drink button |
| `/set-tama-play` | Set happiness gain, hunger/thirst cost, and cooldown for the Play button |
| `/set-tama-medicate` | Set cooldown for the Medicate button |
| `/set-tama-clean` | Set cooldown for the Clean button |

#### Response Messages

| Command | Description |
|---|---|
| `/set-resp-food` | Message shown when someone feeds the bot |
| `/set-resp-drink` | Message shown when someone gives a drink |
| `/set-resp-play` | Message shown when starting a play session |
| `/set-resp-medicate` | Message shown when medication is given |
| `/set-resp-medicate-healthy` | Ephemeral error when medicating a healthy bot |
| `/set-resp-clean` | Message shown when cleaning poop |
| `/set-resp-clean-none` | Ephemeral error when there's nothing to clean |
| `/set-resp-full` | Ephemeral error when the bot is satiated |
| `/set-resp-cooldown` | Cooldown error (use `{time}` placeholder for countdown) |
| `/set-tama-rip-message` | Custom death message (leave empty for default) |

#### Admin

| Command | Description |
|---|---|
| `/show-tama-stats` | View all current stats, config values, and cooldowns |
| `/reset-tama-stats` | Reset all stats to their maximum values |

**How it works:**

1. **Enable** with `/set-tama-mode true` — all defaults are pre-configured, so it works out of the box.
2. **Stats deplete** each time the bot generates a response. Hunger, thirst, happiness, energy, and satiation all decrease per inference.
3. **Users interact via buttons** attached to every bot response:
   - 🍔 **Feed** — restores hunger, increases satiation, counts toward poop
   - 🥤 **Drink** — restores thirst, increases satiation
   - 🎮 **Play** — starts a Rock-Paper-Scissors minigame, costs hunger/thirst/energy, gains happiness
   - 💉 **Medicate** — cures sickness (ephemeral error if not sick)
   - 🚿 **Clean** — removes all poop (ephemeral error if already clean)
4. **Satiation** — when the bot is fully satiated, a cooldown timer starts and feeding/drinking is blocked until it expires.
5. **Poop** — accumulates after a configurable number of feeds. Uncleaned poop drains health on a background timer.
6. **Sickness** — a boolean flag that causes health damage each turn. Cure with the Medicate button.
7. **Health** — decreases when stats are below threshold, when sick, or from uncleaned poop. At 0 health → **death**.
8. **Death** — wipes `soul.md`, resets all stats, sends `[ce]` to all allowed channels and SoC channel.
9. **Error messages** (cooldown, satiated, not sick, already clean) are **ephemeral** — only visible to the user who clicked.
10. All **cooldowns are global** (not per-user) and configurable per button.
11. The bot's **system prompt** includes current stats so the LLM is aware of its condition, but all stat changes are handled by script — the LLM cannot cheat.

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
