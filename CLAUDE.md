# CLAUDE.md

## Project Overview

DiscordPlex is a Python Discord voice bot that bridges users in Discord voice channels to a PersonaPlex (Moshi-based) AI speech-to-speech server. Currently in Phase 1 (completed), with Phase 2 (bidirectional audio bridge) and Phase 3 (multi-user mixing) planned.

## Tech Stack

- **Language**: Python 3.10+
- **Discord Library**: py-cord[voice] >= 2.6.0
- **Audio**: sphn (Opus codec), scipy (resampling), numpy
- **Networking**: aiohttp (WebSocket), PyNaCl (voice encryption)
- **Config**: python-dotenv for environment variables

## Project Structure

```
discordplex/              # Main package
├── __main__.py           # Entry point - loads env, inits Opus, runs bot
├── config.py             # Environment config (DISCORD_TOKEN, PERSONAPLEX_URL, etc.)
├── audio/
│   ├── ode_to_joy.py     # Greeting melody generator (48kHz stereo PCM)
│   └── source.py         # PCMArraySource for Discord playback
├── bot/
│   ├── client.py         # Bot setup, auto-join/leave voice channels, recording
│   └── commands.py       # Prefix commands cog (!prompt, !voice, !voice-list)
├── bridge/               # Phase 2 placeholder - voice session bridge
└── personaplex/          # Phase 2 placeholder - PersonaPlex WebSocket client
docs/
└── discordplex-plan.md   # Full implementation roadmap (Phases 1-3)
```

## Common Commands

```bash
# Install dependencies
pip install -e .
pip install -r requirements.txt

# Run the bot
python -m discordplex
```

## Environment Variables

Required in `.env` (see `.env.example`):
- `DISCORD_TOKEN` - Discord bot token (required)
- `PERSONAPLEX_URL` - WebSocket endpoint (default: `wss://localhost:8998/api/chat`)
- `VOICE_PROMPT_DIR` - Path to voice prompt .pt files

## System Dependencies

- `ffmpeg` - Audio format conversion
- `libopus-dev` - Opus codec
- `libsodium-dev` - Encryption for Discord voice

## Testing & Linting

No testing or linting infrastructure is configured yet. There are no test directories, pytest config, or linter configurations.

## Architecture Notes

- Bot uses async patterns throughout (py-cord is asyncio-based)
- Audio is 48kHz stereo int16 PCM for Discord, needs conversion to 24kHz mono for PersonaPlex
- Per-user settings stored in `bot.user_settings` dict (in-memory, not persisted)
- Voice recordings saved to `./recordings/` as MP3 files
- 18 available voices in 4 categories: NATF, NATM, VARF, VARM

## Implementation Status

- **Phase 1** (complete): Auto-join voice, Ode to Joy greeting, prefix commands, voice recording
- **Phase 2** (not started): Bidirectional audio bridge to PersonaPlex via WebSocket
- **Phase 3** (not started): Multi-user audio mixing
