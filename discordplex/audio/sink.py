"""Streaming audio sink for Discord voice input."""

import asyncio
import logging

from discord.sinks import Sink

logger = logging.getLogger(__name__)


class StreamingSink(Sink):
    """Discord sink that streams audio to an asyncio queue.

    Thread-safe sink that writes Discord voice data to a queue for async processing.
    Uses drop-oldest-if-full strategy to prevent blocking the py-cord thread.
    """

    def __init__(self, queue: asyncio.Queue):
        """Initialize sink.

        Args:
            queue: Asyncio queue to receive PCM audio frames (3840 bytes each)
        """
        super().__init__()
        self.queue = queue

    def write(self, data: bytes, user):
        """Write audio data to queue (called from py-cord thread).

        Args:
            data: 3840 bytes of 48kHz stereo int16 PCM (20ms frame)
            user: Discord user who produced the audio
        """
        try:
            # Non-blocking put: drop oldest frame if queue full
            self.queue.put_nowait(data)
        except asyncio.QueueFull:
            # Drop oldest frame to make room
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(data)
                logger.warning("Audio input queue full, dropped oldest frame")
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                # Race condition, ignore
                pass
