"""Audio sources for Discord playback."""

import asyncio
import logging

import discord

logger = logging.getLogger(__name__)


class PCMArraySource(discord.AudioSource):
    """Wraps a pre-generated PCM bytes buffer for Discord playback.

    Returns 3840-byte chunks (20ms at 48kHz stereo int16).
    Returns b'' when exhausted (signals end of audio).
    """

    FRAME_SIZE = 3840  # 20ms * 48000Hz * 2ch * 2bytes

    def __init__(self, pcm_data: bytes) -> None:
        self._data = pcm_data
        self._offset = 0

    def read(self) -> bytes:
        end = self._offset + self.FRAME_SIZE
        if self._offset >= len(self._data):
            return b""
        chunk = self._data[self._offset:end]
        self._offset = end
        # Pad last chunk with silence if needed
        if len(chunk) < self.FRAME_SIZE:
            chunk += b"\x00" * (self.FRAME_SIZE - len(chunk))
        return chunk

    def is_opus(self) -> bool:
        return False

    def cleanup(self) -> None:
        pass


class StreamingPlaybackSource(discord.AudioSource):
    """Streams audio from an asyncio queue for Discord playback.

    Thread-safe audio source that reads from a queue. Returns silence when
    queue is empty to prevent playback underruns.
    """

    FRAME_SIZE = 3840  # 20ms * 48000Hz * 2ch * 2bytes
    SILENCE = b"\x00" * FRAME_SIZE

    def __init__(self, queue: asyncio.Queue):
        """Initialize source.

        Args:
            queue: Asyncio queue containing 3840-byte PCM frames
        """
        self.queue = queue

    def read(self) -> bytes:
        """Read next audio frame (called from py-cord thread).

        Returns:
            3840 bytes of PCM audio, or silence if queue empty
        """
        try:
            # Non-blocking get: return silence if empty
            return self.queue.get_nowait()
        except asyncio.QueueEmpty:
            return self.SILENCE

    def is_opus(self) -> bool:
        return False

    def cleanup(self) -> None:
        pass
