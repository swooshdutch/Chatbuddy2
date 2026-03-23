# ChatBuddy v3.1

ChatBuddy is a Discord chatbot powered by Google Gemini, Gemma-compatible endpoints, or custom external models. It supports normal mention/reply chat, auto-chat, heartbeat posting, reminders, revival behavior, audio replies, soul memory, stream-of-consciousness logging, and a fully configurable Tamagotchi system with buttons, sleep, dirtiness, satiation, sickness, energy, and mobile-friendly public stat footers.

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- A Discord bot token from the [Discord Developer Portal](https://discord.com/developers/applications)
- A model/API key for the mode you want to run

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token_here
API_KEY=your_gemini_api_key_here
GEMINI_ENDPOINT=gemini-2.5-flash
AUDIO_ENDPOINT=your_tts_endpoint_here
MAIN_CHAT_CHANNEL=123456789012345678
THOUGHTS_CHANNEL=123456789012345678
SOUL_CHANNEL=123456789012345678
SYS_INSTRUCT=You are a friendly and witty chatbot named ChatBuddy.
BOT_OWNER_ID=123456789012345678
```

### 4. Run the Bot

```bash
python bot.py
```

The bot will come online and sync its slash commands automatically.

---

## Setup Walkthrough

Bot-management commands are restricted to `BOT_OWNER_ID` plus any extra IDs you allow with `/set-command-user`.

### Recommended first-run setup

1. Start the bot.
2. Run `/setup-bot`.
3. Mention the bot or reply to one of its messages in an allowed channel.

`/setup-bot` reads the backend environment variables above and configures:

- API key and Gemini endpoint
- Audio endpoint
- Main chat, SoC, and soul channels
- System prompt
- `BOT_OWNER_ID`
- Soul limit set to `10000`

It does not enable heartbeat or auto-chat.

### Grant helper access

Use `/set-command-user` if you want to let another user manage the bot commands without changing the owner ID.

---

## Command Reference

All bot-management commands are owner-gated through `BOT_OWNER_ID` and the `/set-command-user` allowlist.

### Core Settings

| Command | Description |
|---|---|
| `/setup-bot` | Populate live bot config from backend environment variables |
| `/set-command-user` | Add or remove a user ID allowed to use bot commands |
| `/set-api-key` | Set the Gemini API key |
| `/set-api-context` | Enable internal daily LLM API quota tracking logic |
| `/check-api-quota` | Check the current tracked daily quota |
| `/set-edit-api-current-quota` | Manually correct the tracked API usage counter |
| `/set-chat-history` | Set how many messages of context the bot receives |
| `/set-temp` | Set model temperature |
| `/set-api-endpoint-gemini` | Set the Gemini model endpoint |
| `/set-api-endpoint-gemma` | Set the Gemma model endpoint |
| `/set-api-key-custom` | Set the API key for a custom model |
| `/set-api-endpoint-custom` | Set the endpoint for a custom model |
| `/set-sys-instruct` | Set the main system prompt |
| `/show-sys-instruct` | Display the full effective system prompt |
| `/set-model-mode` | Switch between `gemini`, `gemma`, and `custom` |

### Multimodal & Search

| Command | Description |
|---|---|
| `/set-multimodal` | Enable image and audio analysis for incoming payloads |
| `/set-gemini-web-search` | Enable internal Gemini search grounding |
| `/set-duck-search` | Enable DuckDuckGo Python search |

### Soul Memory

| Command | Description |
|---|---|
| `/set-soul` | Enable or disable the self-updating soul memory |
| `/show-soul` | View current soul memory |
| `/edit-soul-add-entry` | Add or append a soul memory entry manually |
| `/edit-soul-overwrite` | Overwrite an existing soul memory entry manually |
| `/edit-soul-delete-entry` | Delete a soul memory entry manually |
| `/wipe-soul` | Wipe all soul memory entries |
| `/set-soul-channel` | Set the channel used for soul update logs |

The bot can manage soul memory through tagged output such as `<!soul-add-new[id]: text>`, `<!soul-update[id]: text>`, `<!soul-override[id]: text>`, and `<!soul-delete[id]>`.

### Dynamic & Game Prompts

| Command | Description |
|---|---|
| `/set-dynamic-system-prompt` | Set an extra prompt appended after the main prompt |
| `/set-word-game` | Set word game rules and enable/disable the game |
| `/set-word-game-selector-prompt` | Set the hidden-turn selector prompt |
| `/set-secret-word` | Trigger a hidden turn to pick a new secret word |
| `/set-secret-word-permission` | Grant or revoke role access to `/set-secret-word` |

### Audio Clip Mode

| Command | Description |
|---|---|
| `/set-audio-endpoint` | Set the TTS model |
| `/set-audio-settings` | Choose the voice |
| `/set-audio-mode` | Enable or disable audio clips globally |

### Channel Settings

| Command | Description |
|---|---|
| `/set-allowed-channel` | Whitelist or blacklist a channel |
| `/set-ce` | Enable or disable `[ce]` context cutoff per channel |

### Stream of Consciousness

| Command | Description |
|---|---|
| `/set-soc` | Set the thoughts output channel and enable/disable |
| `/set-soc-context` | Enable cross-channel thought context and set message count |

Wrap hidden thoughts in `<my-thoughts>` tags in the system prompt and the bot will extract them into the SoC channel.

### Auto-Chat Mode

| Command | Description |
|---|---|
| `/set-auto-chat-mode` | Auto-reply in a channel without requiring mentions |
| `/set-auto-idle-message` | Set the message posted when the bot enters idle mode |

### Chat Revival

| Command | Description |
|---|---|
| `/set-chat-revival` | Configure periodic chat revival and enable/disable |
| `/set-cr-params` | Set active window duration and check interval |
| `/set-cr-leave-msg` | Set the goodbye message after revival expires |

### Reminders & Auto-Wake

| Command | Description |
|---|---|
| `/setup-reminders` | Enable or disable reminders and set their output channel |
| `/set-reminder-channel` | Set the channel where reminders are posted |
| `/set-reminder-log-channel` | Set the channel where reminder registrations are logged |
| `/add-reminder` | Add a named reminder |
| `/delete-reminder` | Delete a reminder by name |
| `/show-reminders` | Show current reminders and auto-wake times |

### Bot-to-Bot Response

| Command | Description |
|---|---|
| `/set-respond-to-bot` | Enable or disable replying to other bots |
| `/set-respond-bot-limit` | Stop after a configured number of consecutive bot messages |

### Heartbeat

| Command | Description |
|---|---|
| `/set-heartbeat` | Configure and enable periodic heartbeat posting |

### Tamagotchi

The Tamagotchi system is fully script-driven. The LLM is informed of current stats in the system prompt, but it does not directly control stat changes.

#### Stat Configuration

| Command | Description |
|---|---|
| `/set-tama-mode` | Enable or disable Tamagotchi mode |
| `/set-tamagotchi-mode` | Alias for enabling or disabling Tamagotchi mode |
| `/set-tama-hunger` | Set max hunger and depletion per inference |
| `/set-tama-thirst` | Set max thirst and depletion per inference |
| `/set-tama-happiness` | Set max happiness, base depletion, and extra low-need happiness loss |
| `/set-tama-health` | Set max health, sickness threshold, and damage per low stat |
| `/set-tama-satiation` | Set max satiation, timer interval, timer tick-down amount, food/drink satiation gain, and inference depletion |
| `/set-tama-energy` | Set max energy, API/game depletion, idle recharge interval, and idle recharge amount |
| `/set-tama-rest` | Set sleep duration and rest button cooldown |
| `/set-tama-hatch-time` | Set how long the egg takes to hatch |
| `/set-tama-hatch-prompt` | Set the hidden prompt the bot receives when the egg hatches |
| `/set-tama-dirt` | Set max dirt, food threshold for poop timers, poop timer max length, health damage, and damage interval |
| `/set-tama-sickness` | Set health damage per turn while sick and the sickness happiness multiplier |

#### Button Configuration

| Command | Description |
|---|---|
| `/set-tama-feed` | Set hunger restored and cooldown for Feed |
| `/set-tama-drink` | Set thirst restored and cooldown for Drink |
| `/set-tama-play` | Set happiness gain, hunger/thirst loss, satiation loss, and cooldown for Play |
| `/set-tama-medicate` | Set cooldown, HP heal amount, and happiness cost for Medicate |
| `/set-tama-clean` | Set cooldown for Clean |

#### Response Messages

| Command | Description |
|---|---|
| `/set-resp-food` | Message shown when someone feeds the bot |
| `/set-resp-drink` | Message shown when someone gives the bot a drink |
| `/set-resp-play` | Message shown when someone starts a play session |
| `/set-resp-medicate` | Message shown when medication is given |
| `/set-resp-medicate-healthy` | Ephemeral error when medicating a healthy bot |
| `/set-resp-clean` | Message shown when poop is cleaned |
| `/set-resp-clean-none` | Ephemeral error when there is nothing to clean |
| `/set-resp-poop` | Script-only message shown when a poop timer pops |
| `/set-resp-full` | Ephemeral error when the bot is fully satiated |
| `/set-resp-cooldown` | Ephemeral cooldown error. Supports `{time}` |
| `/set-resp-rest` | Message shown when the bot starts resting |
| `/set-resp-sleeping` | Public sleeping reply while rest is active. Supports `{time}` |
| `/set-resp-no-energy` | Ephemeral error when Play is blocked by zero energy |
| `/set-tama-rip-message` | Custom death message |

#### Admin

| Command | Description |
|---|---|
| `/show-tama-stats` | View current stats, config values, and cooldowns |
| `/dev-set-stats` | Directly set the current Tamagotchi stats for testing |
| `/reset-tama-stats` | Reset the Tamagotchi. In Tamagotchi mode this wipes soul, sends `[ce]`, and starts a new egg |

#### Tamagotchi Behavior

1. Enable it with `/set-tama-mode true` or `/set-tamagotchi-mode true`.
2. `setup-bot` starts a fresh egg hatch in the main chat channel, and `/reset-tama-stats` does the same when Tamagotchi mode is enabled.
3. While the egg is hatching, users cannot chat with the bot. The egg message shows a live countdown, and when it reaches zero the bot receives a hidden configurable hatch prompt and sends its first public message.
4. A newly hatched bot starts with full health, but hunger, thirst, and happiness begin at 50% of their configured max values.
5. Public bot messages use the compact quoted stat footer as the visible stat display. Happiness uses a dynamic emoji based on its current percent, and a skull icon appears whenever the bot is sick.
6. Feed, Drink, Play, Medicate, Clean, and Rest buttons are attached to public Tamagotchi messages.
7. Play launches a Rock-Paper-Scissors minigame. Intermediate choices stay private to the player; the final result is public.
8. Feed and Drink increase satiation. When satiation reaches max, feeding and drinking are blocked until the satiation timer ticks it back down.
9. Play also reduces satiation by a configurable amount.
10. Energy decreases on API use and games. When energy reaches `0`, play is blocked and stat loss is doubled until the bot rests.
11. Rest only appears when energy is below `1`. While sleeping, the bot refuses normal chat, auto-chat, heartbeat, and revival, but reminders still fire.
12. If the bot is left alone, passive energy recharge restores energy after a configurable inactivity period.
13. Any interaction resets the passive recharge timer, including mentions, replies, games, feed/drink/clean/medicate/rest, reminders, heartbeat, auto-chat, and revival.
14. Hunger and thirst below the configured low-need threshold each apply extra happiness loss every turn.
15. When the bot is sick, its happiness loss is multiplied by the configured sickness multiplier and sickness also drains HP every turn.
16. Medicine is allowed while the bot is sick or while health is below max. It cures sickness, restores configurable HP, and costs configurable happiness.
17. Dirt no longer appears instantly. After the configured food threshold is reached, one or more hidden poop timers are queued. Each timer picks a random whole-minute delay from `1` up to the configured max and posts a script-only poop message when it pops.
18. Uncleaned dirt damages health on its own timer.
19. Health drops when core stats are below threshold, when sickness is active, and when dirt is left uncleared.
20. If health reaches `0`, the Tamagotchi dies, soul memory is wiped, `[ce]` is broadcast, and a fresh egg starts hatching.
21. Error messages such as cooldown, satiated, healthy/full-health medicine rejection, already clean, and no-energy are ephemeral and only shown to the user who triggered them.
22. The visible public stat footer is stripped from stored chat context before messages are sent back to the LLM, which avoids wasting tokens and prevents hallucinated self-reported stats.

---

## Model Modes

| Mode | Description |
|---|---|
| `gemini` | Standard Google Gemini mode |
| `gemma` | Gemma-compatible mode with system prompt injection |
| `custom` | External or non-Google API mode |

For custom mode:

```text
/set-api-endpoint-custom endpoint:https://your-api.example.com/v1/generateContent
/set-api-key-custom key:your_custom_key
/set-model-mode mode:custom
```

If the custom endpoint starts with `http`, it is used as a full URL. Otherwise it is treated as a model name under the standard Gemini API base.

---

## Deployment

The bot includes a built-in HTTP health-check server for platforms such as Back4App or Discloud. It listens on the `PORT` environment variable, defaulting to `8080`.

### Docker

```bash
docker build -t chatbuddy .
docker run -e DISCORD_TOKEN=your_token -e PORT=8080 chatbuddy
```
