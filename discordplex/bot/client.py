"""Discord bot with auto-join voice channel logic."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands
from discord.sinks import MP3Sink

from discordplex.audio.ode_to_joy import generate_ode_to_joy
from discordplex.audio.source import PCMArraySource

log = logging.getLogger(__name__)

RECORDINGS_DIR = Path("./recordings")


async def _recording_finished(sink: MP3Sink, *args) -> None:
    """Save per-user MP3 files when recording stops."""
    RECORDINGS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for user_id, audio_data in sink.audio_data.items():
        # Try to resolve the username from the channel members
        username = str(user_id)
        if sink.vc and sink.vc.channel:
            member = sink.vc.channel.guild.get_member(user_id)
            if member:
                username = member.name

        filename = RECORDINGS_DIR / f"{timestamp}_{username}.mp3"
        with open(filename, "wb") as f:
            f.write(audio_data.file.getvalue())
        log.info("Saved recording: %s (%d bytes)", filename, audio_data.file.tell())


def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    # Per-user settings: {user_id: {"text_prompt": str, "voice_prompt": str}}
    bot.user_settings: dict[int, dict] = {}

    # Current active voice session (None = free) — used in Phase 2
    bot.active_session = None

    @bot.event
    async def on_ready() -> None:
        log.info("DiscordPlex bot ready as %s", bot.user)

    @bot.event
    async def on_voice_state_update(
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        # Ignore bot's own voice state changes
        if member.id == bot.user.id:
            return

        guild = member.guild

        # User joined or moved to a voice channel
        if after.channel and (not before.channel or before.channel != after.channel):
            # Only join if bot isn't already in a voice channel in this guild
            if guild.voice_client is None:
                try:
                    vc = await after.channel.connect()
                    log.info("Joined voice channel: %s", after.channel.name)
                    await asyncio.sleep(0.5)
                    _play_greeting(vc)
                except Exception:
                    log.exception("Failed to join voice channel")

        # User left or moved away from a voice channel
        if before.channel and (not after.channel or before.channel != after.channel):
            vc = guild.voice_client
            if vc and vc.channel == before.channel:
                # Check if any non-bot members remain
                non_bot_members = [m for m in before.channel.members if not m.bot]
                if not non_bot_members:
                    log.info("All users left %s, disconnecting", before.channel.name)
                    if vc.recording:
                        vc.stop_recording()
                        # Give recv_audio thread time to run the callback
                        await asyncio.sleep(1)
                    await vc.disconnect()

    return bot


def _play_greeting(vc: discord.VoiceClient) -> None:
    """Play Ode to Joy as a greeting, then start recording."""
    pcm_data = generate_ode_to_joy()
    source = PCMArraySource(pcm_data)

    def _after_playback(error: Exception | None) -> None:
        if error:
            log.error("Playback error: %s", error)
            return
        # after callback runs in a thread — schedule recording on the event loop
        try:
            vc.start_recording(MP3Sink(), _recording_finished)
            log.info("Recording started")
        except Exception:
            log.exception("Failed to start recording")

    vc.play(source, after=_after_playback)
