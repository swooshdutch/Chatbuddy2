"""Help command."""

from ..common import *
# ---------------------------------------------------------------------------
# Slash commands â€” Help
# ---------------------------------------------------------------------------

@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="ChatBuddy - Command Reference",
        description=(
            "Bot-management commands are restricted to `BOT_OWNER_ID` and any extra IDs "
            "granted with `/set-command-user`. `/help` itself is available to everyone."
        ),
        color=discord.Color.blurple(),
    )

    embed.add_field(
        name="Core Settings",
        value=(
            "`/setup-bot` - Load config from backend environment variables\n"
            "`/setup-bot-gemma` - Load config from backend environment variables in Gemma mode\n"
            "`/set-command-user` - Add or remove a user ID allowed to manage the bot\n"
            "`/set-api-key` - Set the Gemini API key\n"
            "`/set-api-context` - Track daily API quota in system prompt\n"
            "`/check-api-quota` - Check the current tracked daily quota\n"
            "`/set-chat-history [limit]` - Set the maximum messages to remember\n"
            "`/set-temp` - Set model temperature\n"
            "`/set-api-endpoint-gemini` - Set the Gemini model endpoint\n"
            "`/set-api-endpoint-gemma` - Set the Gemma model endpoint\n"
            "`/set-api-key-custom` - Set the API key for a custom model\n"
            "`/set-api-endpoint-custom` - Set the endpoint for a custom model\n"
            "`/set-sys-instruct` - Set the main system prompt\n"
            "`/show-sys-instruct` - Display the full effective system prompt\n"
            "`/set-botname` - Set the value used for `<!BOTNAME!>`\n"
            "`/set-bot-personality` - Set the value used for `<!BOTPERSONALITY!>`\n"
            "`/set-model-mode` - Switch between `gemini`, `gemma`, and `custom`"
        ),
        inline=False,
    )

    embed.add_field(
        name="Multimodal & Search",
        value=(
            "`/set-multimodal [true/false]` - Enable image and audio analysis\n"
            "`/set-gemini-web-search [true/false]` - Enable internal Gemini Search\n"
            "`/set-duck-search [true/false]` - Enable DuckDuckGo search"
        ),
        inline=False,
    )

    embed.add_field(
        name="Soul Memory",
        value=(
            "`/set-soul` - Enable or disable the self-updating soul memory\n"
            "`/show-soul` - View current soul memory\n"
            "`/edit-soul-add-entry` - Add or append a new memory entry manually\n"
            "`/edit-soul-overwrite` - Overwrite an existing memory entry manually\n"
            "`/edit-soul-delete-entry` - Delete a given memory entry manually\n"
            "`/wipe-soul` - Wipe all memory entries immediately\n"
            "`/set-soul-channel` - Set the channel to log soul updates\n"
            "*The bot can emit `<!soul-add-new[id]: text!>`, `<!soul-update[id]: text!>`, "
            "`<!soul-override[id]: text!>`, and `<!soul-delete[id]!>` tags.*"
        ),
        inline=False,
    )

    embed.add_field(
        name="Dynamic Prompt",
        value="`/set-dynamic-system-prompt` - Set an extra prompt after the main prompt",
        inline=False,
    )

    embed.add_field(
        name="Audio Clip Mode",
        value=(
            "`/set-audio-endpoint` - Set the TTS model\n"
            "`/set-audio-settings` - Choose the voice\n"
            "`/set-audio-mode` - Enable or disable audio clips globally"
        ),
        inline=False,
    )

    embed.add_field(
        name="Channel Settings",
        value=(
            "`/set-allowed-channel` - Whitelist or blacklist a channel\n"
            "`/set-ce` - Enable or disable `[ce]` context cutoff per channel"
        ),
        inline=False,
    )

    embed.add_field(
        name="Stream of Consciousness",
        value=(
            "`/set-soc` - Set thoughts output channel and enable or disable it\n"
            "`/set-soc-context` - Enable cross-channel thought context and set message count\n\n"
            "Extracts `<my-thoughts>` blocks to a dedicated channel. `[ce]` works there too."
        ),
        inline=False,
    )

    embed.add_field(
        name="Auto-Chat Mode",
        value=(
            "`/set-auto-chat-mode` - Auto-reply in a channel without needing mentions\n"
            "`/set-auto-idle-message` - Set the message posted when entering idle\n\n"
            "A mention or reply reactivates the bot after idle."
        ),
        inline=False,
    )

    embed.add_field(
        name="Chat Revival",
        value=(
            "`/set-chat-revival` - Configure periodic chat revival and enable or disable it\n"
            "`/set-cr-params` - Set active window duration and check interval\n"
            "`/set-cr-leave-msg` - Set the goodbye message after revival expires"
        ),
        inline=False,
    )

    embed.add_field(
        name="Reminders & Auto-Wake",
        value=(
            "`/setup-reminders` - Enable or disable reminders\n"
            "`/set-reminder-channel` - Set the channel where reminders fire\n"
            "`/set-reminder-log-channel` - Set a log channel for reminder registrations\n"
            "`/add-reminder` - Add a named reminder\n"
            "`/delete-reminder` - Delete a reminder by name\n"
            "`/show-reminders` - Show scheduled reminders and wake-times\n\n"
            "The bot can also self-manage with `<!add-reminder ... !>`, `<!delete-reminder ... !>`, "
            "`<!add-auto-wake-time ... !>`, and `<!delete-auto-wake-time ... !>` tags."
        ),
        inline=False,
    )

    embed.add_field(
        name="Bot-to-Bot Response",
        value=(
            "`/set-respond-to-bot` - Enable or disable replying to other bots\n"
            "`/set-respond-bot-limit` - Stop after N consecutive bot messages\n\n"
            "Only affects direct mention or reply behavior."
        ),
        inline=False,
    )

    embed.add_field(
        name="Heartbeat",
        value=(
            "`/set-heartbeat` - Configure periodic heartbeat posting\n"
            "`/set-heartbeat-rest` - Configure daily heartbeat quiet hours\n\n"
            "Separate from auto-chat and unaffected by idle timers."
        ),
        inline=False,
    )

    embed.add_field(
        name="Tamagotchi",
        value=(
            "**Stats:** `/set-tama-hunger` `/set-tama-thirst` `/set-tama-happiness` "
            "`/set-tama-health` `/set-tama-energy` `/set-tama-dirt` "
            "`/set-tama-sickness` `/set-tama-rest` `/set-tama-low-energy-mood` `/set-tama-hatch-time` "
            "`/set-tama-hatch-prompt` `/set-tama-wake-prompt` `/set-tama-chatter` `/set-tama-chatter-prompt`\n"
            "**Buttons:** `/set-tama-feed` `/set-tama-drink` `/set-tama-play` `/set-rps-rewards` `/set-rps-cooldown` "
            "`/set-tama-lucky-gift` `/set-tama-medicate` `/set-tama-clean`\n"
            "**Inventory:** `/add-tama-item` `/show-tama-items` `/remove-tama-item`\n"
            "**Responses:** `/set-resp-food` `/set-resp-drink` `/set-resp-play` "
            "`/set-resp-medicate` `/set-resp-medicate-healthy` `/set-resp-clean` "
            "`/set-resp-clean-none` `/set-resp-poop` `/set-resp-cooldown` "
            "`/set-resp-rest` `/set-resp-sleeping` `/set-resp-no-energy`"
        ),
        inline=False,
    )

    embed.add_field(
        name="Tamagotchi Notes",
        value=(
            "`/set-tama-rip-message` - Custom death message\n"
            "`/set-tama-mode` and `/set-tamagotchi-mode` - Enable or disable\n"
            "`/show-tama-stats` - View all stats and config\n"
            "`/show-tama-items` - View current item list and stock\n"
            "`/dev-set-stats` - Set current stats directly for testing\n"
            "`/reset-tama-stats` - Reset the pet / start a new egg\n\n"
            "Setup, reset, and death can start a new egg hatch. While hatching, chat is blocked. "
            "Hunger and thirst now drain from energy use instead of per turn, happiness drains only from loneliness, "
            "critically low energy can also drain happiness on LLM turns, medicine and clean only appear when relevant, "
            "Lucky Gift can award inventory items and happiness changes, inventory food can queue randomized poop timers, "
            "the chatter button can trigger an autonomous chat turn, and hitting 0 energy now puts the bot to sleep automatically."
        ),
        inline=False,
    )

    embed.add_field(
        name="API Quota Edit",
        value=(
            "`/set-edit-api-current-quota` - Manually correct the current API usage counter\n"
            "Cannot exceed the max quota limit. Requires API context tracking to be enabled."
        ),
        inline=False,
    )

    embed.set_footer(text="Mention me or reply to my messages to chat!")
    await interaction.response.send_message(embed=embed)



