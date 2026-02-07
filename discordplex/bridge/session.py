"""Voice session orchestrator for bidirectional audio bridge."""

import asyncio
import logging
from typing import Optional

import discord
import numpy as np

from ..audio.converter import AudioConverter, DISCORD_FRAME_SAMPLES, DISCORD_CHANNELS
from ..audio.sink import StreamingSink
from ..audio.source import StreamingPlaybackSource
from ..personaplex.client import PersonaPlexClient

logger = logging.getLogger(__name__)

# 20ms silence frame for Discord (3840 bytes)
SILENCE_FRAME = np.zeros(DISCORD_FRAME_SAMPLES * DISCORD_CHANNELS, dtype=np.int16).tobytes()


class VoiceSession:
    """Manages a single-user voice session with PersonaPlex.

    Orchestrates:
    - Discord voice input/output
    - Audio format conversion
    - PersonaPlex WebSocket connection
    - Text message display in Discord
    """

    def __init__(
        self,
        voice_client: discord.VoiceClient,
        text_channel: discord.TextChannel,
        personaplex_url: str,
        text_prompt: str,
        voice_prompt: str,
    ):
        """Initialize session.

        Args:
            voice_client: Connected Discord voice client
            text_channel: Discord text channel for AI text output
            personaplex_url: PersonaPlex WebSocket URL
            text_prompt: Text prompt for the AI
            voice_prompt: Voice prompt filename
        """
        self.voice_client = voice_client
        self.text_channel = text_channel
        self.personaplex_url = personaplex_url
        self.text_prompt = text_prompt
        self.voice_prompt = voice_prompt

        # Audio queues (thread-safe)
        self.input_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
        self.output_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)

        # Components
        self.personaplex: Optional[PersonaPlexClient] = None
        self.converter: Optional[AudioConverter] = None
        self.sink: Optional[StreamingSink] = None
        self.source: Optional[StreamingPlaybackSource] = None

        # Tasks
        self._send_task: Optional[asyncio.Task] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._text_task: Optional[asyncio.Task] = None

        # State
        self._text_buffer = ""

    async def start(self) -> None:
        """Start the voice session.

        Raises:
            RuntimeError: If PersonaPlex connection fails
        """
        try:
            # Initialize PersonaPlex client
            self.personaplex = PersonaPlexClient(self.personaplex_url)
            await self.personaplex.connect(self.text_prompt, self.voice_prompt)

            # Initialize audio converter
            self.converter = AudioConverter()

            # Start Discord recording
            self.sink = StreamingSink(self.input_queue)
            self.voice_client.start_recording(
                self.sink, lambda *_: None, lambda *_: None
            )

            # Start Discord playback
            self.source = StreamingPlaybackSource(self.output_queue)
            self.voice_client.play(self.source)

            # Start processing loops
            self._send_task = asyncio.create_task(self._send_loop())
            self._recv_task = asyncio.create_task(self._recv_loop())
            self._text_task = asyncio.create_task(self._text_loop())

            await self.text_channel.send("🎙️ Voice session started!")
            logger.info("Voice session started")

        except Exception as e:
            logger.error(f"Failed to start session: {e}")
            await self.stop()
            await self.text_channel.send(f"❌ Failed to start session: {e}")
            raise

    async def stop(self) -> None:
        """Stop the voice session and clean up resources."""
        logger.info("Stopping voice session")

        # Cancel tasks
        tasks = [self._send_task, self._recv_task, self._text_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()

        # Wait for tasks to finish
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Stop Discord recording
        if self.voice_client.recording:
            self.voice_client.stop_recording()

        # Stop Discord playback
        if self.voice_client.is_playing():
            self.voice_client.stop()

        # Close PersonaPlex connection
        if self.personaplex:
            await self.personaplex.close()

        logger.info("Voice session stopped")

    async def _send_loop(self) -> None:
        """Send loop: Discord input → PersonaPlex.

        Continuously sends audio to PersonaPlex, including silence when no user audio.
        """
        try:
            last_opus = None

            while True:
                # Get audio from Discord (with 20ms timeout)
                try:
                    pcm_bytes = await asyncio.wait_for(
                        self.input_queue.get(), timeout=0.02
                    )
                except asyncio.TimeoutError:
                    # No user audio, send silence
                    pcm_bytes = SILENCE_FRAME

                # Convert to PersonaPlex format
                opus_bytes = self.converter.discord_to_personaplex(pcm_bytes)

                # Send to PersonaPlex (handle encoder buffering)
                if opus_bytes:
                    await self.personaplex.send_audio(opus_bytes)
                    last_opus = opus_bytes
                elif last_opus:
                    # Encoder buffering, resend last frame
                    await self.personaplex.send_audio(last_opus)

        except asyncio.CancelledError:
            logger.info("Send loop cancelled")
        except Exception as e:
            logger.error(f"Send loop error: {e}")
            await self.text_channel.send(f"❌ Audio send error: {e}")

    async def _recv_loop(self) -> None:
        """Receive loop: PersonaPlex audio → Discord output."""
        try:
            while True:
                # Get audio from PersonaPlex (with 100ms timeout)
                try:
                    opus_bytes = await asyncio.wait_for(
                        self.personaplex.audio_queue.get(), timeout=0.1
                    )
                except asyncio.TimeoutError:
                    continue

                # Convert to Discord format
                pcm_chunks = self.converter.personaplex_to_discord(opus_bytes)

                # Queue for playback
                for chunk in pcm_chunks:
                    try:
                        self.output_queue.put_nowait(chunk)
                    except asyncio.QueueFull:
                        # Drop oldest frame
                        try:
                            self.output_queue.get_nowait()
                            self.output_queue.put_nowait(chunk)
                            logger.warning("Audio output queue full, dropped frame")
                        except (asyncio.QueueEmpty, asyncio.QueueFull):
                            pass

        except asyncio.CancelledError:
            logger.info("Receive loop cancelled")
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
            await self.text_channel.send(f"❌ Audio receive error: {e}")

    async def _text_loop(self) -> None:
        """Text loop: PersonaPlex text → Discord text channel.

        Buffers text and sends on whitespace or 50-character limit.
        """
        try:
            while True:
                # Get text from PersonaPlex
                text = await self.personaplex.text_queue.get()

                # Add to buffer
                self._text_buffer += text

                # Send on whitespace or length limit
                if text.isspace() or len(self._text_buffer) >= 50:
                    if self._text_buffer.strip():
                        await self.text_channel.send(f"🤖 AI: {self._text_buffer.strip()}")
                    self._text_buffer = ""

        except asyncio.CancelledError:
            # Flush remaining text
            if self._text_buffer.strip():
                await self.text_channel.send(f"🤖 AI: {self._text_buffer.strip()}")
            logger.info("Text loop cancelled")
        except Exception as e:
            logger.error(f"Text loop error: {e}")
